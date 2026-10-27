"""Conciliação da interpretação ancorada em trechos (arquitetura v8; substitui `validators._ground_in_question` no prompt v8).

No v8 o LLM NÃO escreve datas, números nem unidades. Ele decide só o que é linguístico (qual grandeza, qual estação, qual cálculo, qual
forma do resultado) e, para cada decisão, CITA o trecho da pergunta que a justifica. O resto vem da leitura determinística
(pipeline/spans.py):

  - o tempo (período, instante, parte do dia, dias da semana) vem SÓ da leitura; não há período do LLM para conferir;
  - o valor e a unidade de um filtro vêm do analisador lendo o trecho que o LLM citou ("acima de 1000 metros" -> > 1000 M);
  - o que a contagem conta (`count_of`: leituras, horas, dias, boletins) vem das palavras da pergunta, e é dito na resposta;
  - "horas/dias com chuva" vira a condição "> 0" por construção (o filtro que o v7 deixava cair, E15).

O que a conciliação confere, de forma genérica (uma regra por MECANISMO, não por jeito de escrever):
  1. todo trecho citado existe na pergunta e corresponde ao que foi decidido (estação citada pelo código ou rótulo);
  2. nenhum número da pergunta fica sem dono (limiar descartado em silêncio);
  3. a unidade que a pergunta cita é da mesma dimensão da grandeza ("minutos de chuva" não é precipitação em mm) e pede uma medida, não
     uma contagem ("quantos mm" não é contar leituras);
  4. a pergunta tem o mínimo para virar UMA consulta: um cálculo, e um alcance (estação, período ou "toda a rede"); se não, esclarecimento.
Achados com código `*` em REPAIRABLE voltam ao LLM numa rodada de reparo; os demais encerram com esclarecimento ou `unsupported`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from .spans import UNIT_DIMENSION, Reading, parse_quantities, read
from .validators import AGGREGATIONS, GROUP_DIMS, L3, L4, Finding, PipelineInterpretation, _err
from .vocab import OntologyIndex, expand, fold

OPS = {">", ">=", "<", "<=", "="}
COUNT_OF = ("readings", "hours", "days", "reports")
_COUNT_UNIT = re.compile(r"\bquant[oa]s\s+(horas|dias|vezes|boletins|leituras|observacoes|registros|medicoes|medidas)\b")
_COUNT_MAP = {"horas": "hours", "dias": "days", "boletins": "reports"}            # o resto (vezes, leituras...) conta leituras
# "horas/dias com chuva", "dias sem chuva": presença ou ausência da grandeza acumulada, sem número na pergunta
_PRESENCE = re.compile(r"\b(horas|dias|vezes|boletins|leituras)\s+(com|sem)\s+(chuva|precipitacao|garoa)\b")
_PRESENCE_PROP = "Precipitation"
# a pergunta diz explicitamente que quer TODAS as estações ou TODO o histórico: sem estação e sem período não é ambiguidade
_SCOPE = re.compile(r"\b(?:rede|todas as estacoes|todos os aerodromos|ja registrad\w*|historic\w*|de todos os tempos|no brasil|"
                    r"qual (?:estacao|aerodromo)|quais (?:estacoes|aerodromos)|em qual (?:estacao|aerodromo))\b")
# palavra de período que a leitura não converteu em janela ("em toda a semana", "nesse período"): sem datas, seria todo o histórico em silêncio
_VAGUE_TIME = re.compile(r"\b(?:tod[ao]s?\s+(?:a|o)\s+)?(?:semana|quinzena|bimestre|periodo|epoca|temporada)\b")
REPAIRABLE = {"SPAN_NOT_IN_QUESTION", "ENTITY_SPAN_MISMATCH", "ENTITY_OMITTED", "FILTER_SPAN_UNREADABLE", "NUMBER_UNUSED",
              "UNIT_PROPERTY_MISMATCH", "MEASURE_NOT_COUNT", "DAILY_NEEDED", "BAD_FIELD"}


@dataclass
class Reconciled:
    interp: PipelineInterpretation | None
    findings: list[Finding] = field(default_factory=list)
    clarify: str | None = None              # pedido de esclarecimento (encerra como needs_clarification)
    unsupported: str | None = None          # a pergunta é entendida mas o sistema não sabe montar (encerra como unsupported)
    notes: list[str] = field(default_factory=list)       # o que foi decidido por regra e deve ser dito ao usuário
    reading: Reading | None = None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", fold(str(s))).strip()


def _span_ok(span: Any, q: str) -> bool:
    return isinstance(span, str) and bool(_norm(span)) and _norm(span) in q


def _unit_short(iri: str | None) -> str | None:
    return iri.rsplit("/", 1)[-1] if iri else None


def reconcile(raw: dict[str, Any], question: str, index: OntologyIndex, reading: Reading | None = None) -> Reconciled:
    r = reading or read(question)
    q = _norm(r.text)
    out = Reconciled(None, reading=r)
    bad = lambda code, msg, **kw: out.findings.append(_err(L4, code, msg, **kw))

    def span_of(item: Any, what: str) -> str | None:
        span = item.get("span") if isinstance(item, dict) else None
        if not _span_ok(span, q):
            bad("SPAN_NOT_IN_QUESTION", f"O trecho citado para {what} ({span!r}) não está na pergunta: copie o trecho literal")
            return None
        return _norm(span)

    # ---------------- forma do JSON ----------------
    def as_list(key: str) -> list:
        v = raw.get(key) or []
        if not isinstance(v, list) or not all(isinstance(x, dict) for x in v):
            bad("BAD_FIELD", f"'{key}' deve ser lista de objetos com 'span'")
            return []
        return v

    props_raw, ents_raw, filters_raw = as_list("properties"), as_list("entities"), as_list("filters")
    group_raw, attrs_raw = as_list("group_by"), as_list("attributes")
    agg_raw, order_raw, daily_raw = raw.get("aggregation"), raw.get("order"), raw.get("daily")
    owned: list[str] = []                                   # trechos com dono (para os números sem dono)

    # ---------------- grandezas e estações: decisão do LLM, ancorada no trecho ----------------
    properties = []
    for p in props_raw:
        s = span_of(p, "a grandeza")
        if isinstance(p.get("iri"), str):
            properties.append(p["iri"])
            owned += [s] if s else []
    entities = []
    for e in ents_raw:
        s = span_of(e, "a estação")
        iri = e.get("iri")
        if not isinstance(iri, str):
            bad("BAD_FIELD", "cada estação precisa de 'iri'")
            continue
        if s and expand(iri) not in index.link_entities(s):
            bad("ENTITY_SPAN_MISMATCH", f"O trecho {s!r} não é o código nem um rótulo de {iri}: não há nome de cidade nos dados; estação "
                                        "fora da lista é status \"unsupported\"", entity=e)
        entities.append({"text": s or "", "iri": iri})
        owned += [s] if s else []
    for iri, name in index.link_entities(r.text).items():
        if iri not in {expand(e["iri"]) for e in entities}:
            bad("ENTITY_OMITTED", f"A pergunta cita '{name}' e a interpretação não tem essa estação", iri=iri)

    # ---------------- cálculo e forma do resultado ----------------
    aggregation = None
    if agg_raw is not None:
        if not (isinstance(agg_raw, dict) and agg_raw.get("value") in AGGREGATIONS):
            bad("BAD_FIELD", f"'aggregation' deve ser null ou {{\"value\": {sorted(AGGREGATIONS)}, \"span\"}}")
        else:
            aggregation = agg_raw["value"]
            s = span_of(agg_raw, "o cálculo")
            owned += [s] if s else []
    group_by = []
    for g in group_raw:
        s = span_of(g, "o agrupamento")
        dim = g.get("dim")
        if isinstance(dim, str):
            group_by.append(dim)
            owned += [s] if s else []
    attributes = [a["iri"] for a in attrs_raw if isinstance(a.get("iri"), str) and span_of(a, "o atributo")]
    order = None
    if order_raw is not None:
        if not (isinstance(order_raw, dict) and order_raw.get("direction") in ("asc", "desc") and isinstance(order_raw.get("limit"), int)):
            bad("BAD_FIELD", "'order' deve ser null ou {\"direction\": \"asc\"|\"desc\", \"limit\": N, \"span\"}")
        else:
            order = {"by": "aggregate", "direction": order_raw["direction"], "limit": order_raw["limit"]}
            s = span_of(order_raw, "a ordenação")
            owned += [s] if s else []

    prop_unit = None
    if len(properties) == 1 and expand(properties[0]) in index.properties:
        prop_unit = _unit_short(index.properties[expand(properties[0])].unit)

    # ---------------- filtros: o LLM diz o operador e cita o trecho; o número e a unidade são lidos do trecho ----------------
    def read_threshold(item: dict, what: str) -> tuple[Decimal, str | None] | None:
        s = span_of(item, what)
        if s is None:
            return None
        nums = [x for x in parse_quantities(s) if x.value is not None]
        if len(nums) != 1:
            bad("FILTER_SPAN_UNREADABLE", f"O trecho de {what} ({s!r}) precisa conter exatamente um número com sua unidade, como na pergunta")
            return None
        owned.append(s)
        return nums[0].value, nums[0].unit

    filters = []
    for f in filters_raw:
        if f.get("op") not in OPS:
            bad("BAD_FIELD", f"operador de filtro inválido: {f.get('op')!r}")
            continue
        got = read_threshold(f, "o filtro")
        if got:
            filters.append({"op": f["op"], "value": float(got[0]), **({"unit": f"unit:{got[1]}"} if got[1] else {})})
    daily = None
    if daily_raw is not None:
        if not (isinstance(daily_raw, dict) and daily_raw.get("agg") in ("max", "min", "avg", "sum") and daily_raw.get("op") in OPS):
            bad("BAD_FIELD", "'daily' deve ser null ou {\"agg\": \"max\"|\"min\"|\"avg\"|\"sum\", \"op\", \"span\"}")
        else:
            got = read_threshold(daily_raw, "a condição do dia")
            if got:
                daily = {"agg": daily_raw["agg"], "op": daily_raw["op"], "value": float(got[0]), **({"unit": f"unit:{got[1]}"} if got[1] else {})}

    # presença ("horas com chuva"): a condição > 0 vem da pergunta, não do LLM
    pres = _PRESENCE.search(q)
    if pres and properties and expand(properties[0]).endswith("#" + _PRESENCE_PROP) and not filters and not daily:
        op = ">" if pres[2] == "com" else "="
        if pres[1] == "dias":
            daily = {"agg": "sum", "op": op, "value": 0.0}
        else:
            filters.append({"op": op, "value": 0.0})
        out.notes.append(f"'{pres.group(0)}' = {'precipitação acima de zero' if op == '>' else 'precipitação igual a zero'}"
                         f"{' no dia (soma do dia)' if pres[1] == 'dias' else ''}")
        owned.append(pres.group(0))

    # ---------------- números sem dono: um limiar que a interpretação deixou cair ----------------
    for x in r.quantities:
        if x.value is None or any(x.span in s for s in owned):
            continue
        if x.unit is None and not re.search(r"\d", x.span):
            continue                                            # "as duas médias": número por extenso sem unidade não é limiar
        if order and x.value == order["limit"]:
            continue                                            # "as 5 estações": é o limite da ordenação
        bad("NUMBER_UNUSED", f"O número '{x.span}' da pergunta não está em nenhum campo: se é um limiar, crie o filtro citando o trecho")

    # ---------------- unidade citada x grandeza e cálculo ----------------
    if prop_unit:
        dim = UNIT_DIMENSION.get(prop_unit)
        for x in r.quantities:
            if x.dimension and dim and x.dimension != dim and not (x.dimension == "length" and dim == "length"):
                bad("UNIT_PROPERTY_MISMATCH", f"A pergunta fala em '{x.span}' ({x.dimension}) e a grandeza {properties[0]} é medida em {prop_unit} "
                                              f"({dim}): escolha a grandeza medida nessa unidade, ou status \"unsupported\"")
        if aggregation == "count" and not daily and any(x.value is None and x.dimension == dim for x in r.quantities):
            bad("MEASURE_NOT_COUNT", f"A pergunta pede uma medida em {prop_unit} ('quantos mm', 'quantos minutos'), não quantas leituras: "
                                     "use a soma (ou a estatística pedida), não a contagem")

    # ---------------- o que a contagem conta ----------------
    count_of = None
    m = _COUNT_UNIT.search(q)
    if aggregation == "count":
        count_of = _COUNT_MAP.get(m[1], "readings") if m else "readings"
        if pres and pres[1] == "dias":
            count_of = "days"
        if count_of == "days" and not daily:
            bad("DAILY_NEEDED", "A pergunta conta DIAS que cumprem uma condição: use \"daily\" com a estatística do dia (máxima, mínima, média "
                                "ou soma) e o trecho da condição, em vez de \"filters\"")
        if count_of in ("hours", "reports") and (group_by or attributes or order):
            out.unsupported = "Contar horas ou boletins junto de agrupamento ainda não é suportado."
        out.notes.append({"readings": "contei leituras", "hours": "contei horas distintas (cada hora uma vez, mesmo com várias leituras)",
                          "days": "contei dias", "reports": "contei boletins distintos"}[count_of])

    # ---------------- tempo: SÓ da leitura determinística ----------------
    period = instant = None
    inst = next((f for f in r.time if f.kind == "instant"), None)
    if inst:
        instant = f"{inst.start.isoformat()}T{inst.hour[0]:02d}:{inst.hour[1]:02d}:00-03:00"
    elif any(f.kind == "month_any" for f in r.time) and not r.windows:
        out.clarify = "A pergunta cita um mês sem o ano: de qual ano? (ou diga 'todos os anos', se for a média histórica desse mês)"
    elif not r.windows and (vague := next((m for m in _VAGUE_TIME.finditer(r.text)
                                            if not any(a <= m.start() < b for a, b in r.covered())), None)):
        out.clarify = f"Não sei a que período '{vague.group(0)}' se refere: informe as datas (ex.: de 01/03/2024 a 07/03/2024)"
    elif len(r.windows) > 1:
        out.unsupported = "Comparar dois períodos numa só consulta ainda não é suportado; pergunte um período de cada vez."
    elif r.windows:
        s, e = r.windows[0]
        period = {"start": s.isoformat(), "end": e.isoformat(), "tz": "-03:00", "inclusive_end": True}

    # ---------------- mínimo para virar UMA consulta (senão é esclarecimento, não chute) ----------------
    if not out.findings and out.clarify is None and out.unsupported is None:
        if aggregation is None and not group_by and not attributes and instant is None:
            out.clarify = "Que cálculo você quer: média, máxima, mínima, total ou contagem?"
        elif not entities and period is None and instant is None and not group_by and not attributes and not order and not _SCOPE.search(q):
            out.clarify = "De qual estação e de qual período? (ou diga 'todas as estações' / 'todo o histórico')"

    out.interp = PipelineInterpretation(properties=properties, entities=entities, filters=filters, period=period, aggregation=aggregation,
                                        record_kind=raw.get("record_kind") if isinstance(raw.get("record_kind"), str) else "observation",
                                        instant=instant, group_by=group_by, attributes=attributes, order=order, daily=daily,
                                        hours=r.hours, weekdays=sorted(r.weekdays) if r.weekdays else None, count_of=count_of)
    return out
