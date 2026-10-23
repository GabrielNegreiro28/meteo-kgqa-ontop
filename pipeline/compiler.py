"""Compilador determinístico: interpretação validada -> SPARQL, sem LLM, a partir da camada estrutural da ontologia.

Por que existe: se a ontologia já diz o caminho de cada grandeza (relações, classe de observação, forma do tempo), a
etapa 2 pode ser montagem em vez de geração livre. Aqui ela é usada como rede de segurança: quando o SPARQL do LLM é
recusado pelas regras mesmo após o reparo, a consulta compilada (que passa pelas MESMAS regras) substitui a recusa.

Cobre apenas onde a FORMA DA RESPOSTA é determinada: agregação de uma grandeza com uma estação (um valor e ?n) ou
"por estação" (um valor por estação). Superlativo ("qual estação…"), lista de leituras, ranking, comparação e série por
dia dependem de uma intenção que a interpretação não registra: a consulta montada seria coerente com a interpretação e
responderia OUTRA pergunta (medido: 6 dos 23 casos de referência). Nesses casos devolve None e a recusa se mantém.
"""
from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal

from . import vocab
from .validators import PipelineInterpretation, parse_period
from .vocab import OntologyIndex, expand

_SHORT = vocab._short
PER_STATION = re.compile(r"\bpor (estacao|estacoes|aerodromo|aerodromos)\b|\bde cada (estacao|aerodromo)\b")


SERIES_OR_RANKING = re.compile(r"\b(cada|por) (dia|hora|mes|semana|ano)\b|\bdiari[ao]s?\b|\bcronolog|\bordem\b|\bmaiores\b|\bmenores\b|\btop\b|"
                               r"\bmensa(?:l|is)\b|\banua(?:l|is)\b|\bmes a mes\b|\bano a ano\b|\bdia a dia\b|\bfrequen|\bmoda\b")
# mensal/anual/mês a mês/ano a ano e frequência/moda: medido no grafo real (RG13 e RG14 do v4), o compilador de reserva respondia o TOTAL
# no lugar da série quando a consulta do LLM era recusada, porque só conhecia "por dia/ano" e "diário".


def _dt(d, tz: str) -> str:
    return f'"{d.isoformat()}T00:00:00{tz}"^^xsd:dateTime'


def compile_query(interp: PipelineInterpretation, index: OntologyIndex, question: str = "") -> str | None:
    if interp.record_kind != "observation" or len(interp.properties) != 1 or not interp.aggregation or interp.filters:
        return None                                   # filtro + agregação ('média diária acima de X') agrupa por dia: não determinado
    if SERIES_OR_RANKING.search(vocab.fold(question)):
        return None                                   # série por dia/hora, ordenação ou ranking: o agrupamento não está na interpretação
    ents = [expand(e["iri"]) for e in interp.entities]
    single = len(ents) == 1                          # uma estação: sem GROUP BY, para que 'sem dados' devolva a linha com ?n = 0 (D-10)
    if not single and not PER_STATION.search(vocab.fold(question)):
        return None                                   # sem uma estação e sem "por estação", a forma da resposta não é determinada
    prop = expand(interp.properties[0])
    info = index.properties.get(prop)
    if info is None or not info.kind or (index.properties_with_data and prop not in index.properties_with_data):
        return None
    shape = index.time_shape(prop)
    paths = index.time_paths(shape) if shape else []
    if not paths or not (vocab.SOSA + "hosts" in index.domain and vocab.SOSA + "madeBySensor" in index.domain):
        return None

    if single:
        where = [f"<{ents[0]}> sosa:hosts ?sensor ."]
    else:
        where = ["?station sosa:hosts ?sensor ."]
        if ents:
            where.insert(0, "VALUES ?station { " + " ".join(f"<{e}>" for e in ents) + " }")
    where.append(f"?obs a {_SHORT(info.kind)} ; sosa:madeBySensor ?sensor ; sosa:observedProperty {_SHORT(prop)} ;")
    where.append("   sosa:hasResult/qudt:numericValue ?v .")
    cond = []
    if interp.period is not None:
        start, end, tz, inclusive = parse_period(interp.period)
        end_excl = end + timedelta(days=1) if inclusive else end
        if _SHORT(shape) == "time:Instant":
            where.append(f"?obs sosa:phenomenonTime/{paths[0]} ?t .")
            cond += [f"?t >= {_dt(start, tz)}", f"?t < {_dt(end_excl, tz)}"]
        else:
            names = [p.split("/")[0].split(":")[-1] for p in paths]
            where.append("?obs sosa:phenomenonTime ?iv . ?iv " + " ; ".join(f"{p} ?{n}" for p, n in zip(paths, names)) + " .")
            begin = next((n for n in names if "Begin" in n), None)
            finish = next((n for n in names if "End" in n), None)
            if not (begin and finish):
                return None
            cond += [f"?{begin} >= {_dt(start, tz)}", f"?{finish} <= {_dt(end_excl, tz)}"]
    if cond:
        where.append("FILTER(" + " && ".join(cond) + ")")

    st = "" if single else "?station "
    head = f"SELECT {st}({interp.aggregation.upper()}(?v) AS ?value) (COUNT(?v) AS ?n)"
    tail = "" if single else " GROUP BY ?station"
    return f"{head} WHERE {{\n  " + "\n  ".join(where) + f"\n}}{tail}"


# ---------------------------------------------------------------------------------------------------------------------------
# Forma do resultado (prompt v6): agrupamento, atributo no superlativo e ordenação com limite.
#
# Aqui o compilador é o CAMINHO, não a rede de segurança: com group_by/attributes/order na interpretação, a consulta é montada por
# código e nunca escrita pelo LLM. É fiel à interpretação por construção (o que a pergunta pede foi conferido em L4), e custa uma
# chamada a menos. Só usa `met:localDate` para o período (equivalência medida no grafo real: docs/EQUIVALENCIA_LOCALDATE.md).
#
# Convenção dos nomes de coluna: station, year, month, day, measured (o valor medido, ao agrupar por valor), o atributo pelo nome
# curto (runway, condition), value (a agregação), n (quantas leituras), t (instante, no superlativo).
# ---------------------------------------------------------------------------------------------------------------------------
ATTRIBUTE_VAR = {"runwayDesignator": "runway", "windCondition": "condition"}


def _attr_var(iri: str) -> str:
    local = iri.rsplit("#", 1)[-1]
    return ATTRIBUTE_VAR.get(local, re.sub(r"\W", "", local.lower()))


def canonical_filters(interp: PipelineInterpretation, index: OntologyIndex) -> list[tuple[str, Decimal]] | None:
    """Filtros da interpretação na unidade canônica da grandeza; None se algum não se converte (o chamador recusa em vez de chutar a escala)."""
    info = index.properties.get(expand(interp.properties[0])) if len(interp.properties) == 1 else None
    out = []
    for f in interp.filters:
        v = vocab.convert_filter_value(f["value"], f.get("unit"), info.unit if info else None)
        if v is None:
            return None
        out.append((f["op"], v))
    return out


def compile_structured(interp: PipelineInterpretation, index: OntologyIndex, force: bool = False) -> str | None:
    """SPARQL da forma pedida, ou None se esta interpretação não tem montagem determinística (a pipeline então responde `unsupported`).
    `force=True` (prompt v7): também monta a agregação simples e a contagem com limiar, sem group_by/attributes/order."""
    from .validators import GROUP_DIMS, TIME_DIMS
    if not (interp.structured or force) or interp.record_kind != "observation" or len(interp.properties) != 1 or interp.instant is not None:
        return None
    if interp.filters and (interp.group_by or interp.attributes or interp.order):
        return None                                   # filtro das leituras ou dos grupos? ambíguo (GROUPED_FILTER_AMBIGUOUS)
    filters = canonical_filters(interp, index) if interp.filters else []
    if filters is None:
        return None
    prop = expand(interp.properties[0])
    info = index.properties.get(prop)
    if info is None or not info.kind or (index.properties_with_data and prop not in index.properties_with_data):
        return None
    day_form = vocab.MET + "localDate" in index.data_predicates
    if (interp.period is not None or any(d in TIME_DIMS for d in interp.group_by)) and not day_form:
        return None                                   # sem met:localDate não há como dizer o dia local de forma fiel
    dims = [d if d in GROUP_DIMS else expand(d) for d in interp.group_by]
    ents = [expand(e["iri"]) for e in interp.entities]
    by_station = "station" in dims
    if len(ents) > 1 and not by_station:
        return None                                   # várias estações sem agrupar por estação misturariam os valores
    agg = interp.aggregation
    if agg is None:
        return None

    def period_filter(d: str) -> list[str]:
        if interp.period is None:
            return []
        start, end, tz, inclusive = parse_period(interp.period)
        if tz != "-03:00":
            raise ValueError("fuso")
        last = end if inclusive else end - timedelta(days=1)
        return [f'FILTER({d} >= "{start.isoformat()}"^^xsd:date && {d} <= "{last.isoformat()}"^^xsd:date)']

    def base(sfx: str = "", need_day: bool = False) -> list[str]:
        """Estação -> sensor -> observação da grandeza (+ dia local quando há período ou dimensão de tempo)."""
        v, sensor, obs, d = f"?v{sfx}", f"?sensor{sfx}", f"?obs{sfx}", f"?d{sfx}"
        if len(ents) == 1 and not by_station:
            where = [f"<{ents[0]}> sosa:hosts {sensor} ."]
        else:
            where = [f"?station{sfx} sosa:hosts {sensor} ."]
            if ents and by_station:
                where.insert(0, "VALUES ?station { " + " ".join(f"<{e}>" for e in ents) + " }")
        where.append(f"{obs} a {_SHORT(info.kind)} ; sosa:madeBySensor {sensor} ; sosa:observedProperty {_SHORT(prop)} ;")
        where.append(f"   sosa:hasResult/qudt:numericValue {v} .")
        if interp.period is not None or need_day:
            where.append(f"{obs} met:localDate {d} .")
        for op, val in filters:
            where.append(f"FILTER({v} {op} {format(val.normalize(), 'f')})")
        return where + period_filter(d)

    try:
        # ---- dias que cumprem uma condição: agrega cada dia (daily.agg) e conta os dias; value = dias que cumprem, n = dias com dados ----
        if interp.daily:
            dv = vocab.convert_filter_value(interp.daily["value"], interp.daily.get("unit"), info.unit)
            if dv is None or len(ents) != 1 or agg != "count":
                return None
            hit = "\n      ".join(base("1", need_day=True))
            seen = "\n      ".join(base("0", need_day=True))
            cond = f"{interp.daily['agg'].upper()}(?v1) {interp.daily['op']} {format(dv.normalize(), 'f')}"
            # dois subselects independentes: os dias que cumprem (value) e os dias com dados (n); sem cálculo sobre o argumento de agregação
            return (f"SELECT ?value ?n WHERE {{\n"
                    f"  {{ SELECT (COUNT(?d1) AS ?value) WHERE {{ SELECT ?d1 WHERE {{\n      {hit}\n    }} GROUP BY ?d1 HAVING ({cond}) }} }}\n"
                    f"  {{ SELECT (COUNT(?d0) AS ?n) WHERE {{ SELECT ?d0 WHERE {{\n      {seen}\n    }} GROUP BY ?d0 }} }}\n}}")

        # ---- superlativo com atributo: a(s) leitura(s) que atingem o máximo/mínimo, com o atributo e o instante ----
        if interp.attributes:
            fn = agg.upper()
            outer = base()
            outer[outer.index(next(x for x in outer if x.startswith("   sosa:hasResult")))] = "   sosa:hasResult/qudt:numericValue ?value ."
            opt = [f"OPTIONAL {{ ?obs {_SHORT(expand(a))} ?{_attr_var(expand(a))} . }}" for a in interp.attributes]
            inner = "\n    ".join(base("0"))
            attrs = " ".join(f"?{_attr_var(expand(a))}" for a in interp.attributes)
            return (f"SELECT {attrs} ?value ?t ?n WHERE {{\n  {{ SELECT ({fn}(?v0) AS ?value) (COUNT(?v0) AS ?n) WHERE {{\n    {inner}\n  }} }}\n  "
                    + "\n  ".join(outer) + "\n  ?obs sosa:resultTime ?t .\n  " + "\n  ".join(opt) + "\n}")

        # ---- agrupamento ----
        where = base(need_day=any(d in TIME_DIMS for d in dims))
        keys: list[str] = []          # variáveis do GROUP BY, na ordem das dimensões
        group_exprs: list[str] = []   # o que vai no GROUP BY (variável ou (expr AS ?alias))
        for d in dims:
            if d == "station":
                keys.append("?station")
                group_exprs.append("?station")
            elif d == "year":
                keys.append("?year")
                group_exprs.append("(YEAR(?d) AS ?year)")
            elif d == "month":
                keys += ["?year", "?month"]
                group_exprs += ["(YEAR(?d) AS ?year)", "(MONTH(?d) AS ?month)"]
            elif d == "day":
                where.append("BIND(?d AS ?day)")
                keys.append("?day")
                group_exprs.append("?day")
            elif d == "value":
                where.append("BIND(?v AS ?measured)")
                keys.append("?measured")
                group_exprs.append("?measured")
            else:
                var = _attr_var(d)
                where.append(f"?obs {_SHORT(d)} ?{var} .")
                keys.append(f"?{var}")
                group_exprs.append(f"?{var}")
        select_keys = [k for k in keys]
        aggregate = "(COUNT(?obs) AS ?n)" if agg == "count" else f"({agg.upper()}(?v) AS ?value) (COUNT(?v) AS ?n)"
        head = "SELECT " + " ".join([*select_keys, aggregate])
        order_keys = " ".join(f"ASC({k})" for k in keys)
        if interp.order:
            main = "?n" if agg == "count" else "?value"
            sense = "DESC" if interp.order["direction"] == "desc" else "ASC"
            order = f"ORDER BY {sense}({main}) {order_keys}".strip() + f" LIMIT {int(interp.order['limit'])}"
        else:
            order = f"ORDER BY {order_keys}"
        group = f" GROUP BY {' '.join(group_exprs)} {order}" if group_exprs else ""     # sem dimensões: um único valor, sem GROUP BY
        return f"{head} WHERE {{\n  " + "\n  ".join(where) + f"\n}}{group}"
    except (KeyError, ValueError):
        return None
