"""Apresentação DETERMINÍSTICA (documento da arquitetura, §12, sintetizador): o texto é montado das linhas já verificadas, com número,
unidade, estação e período; nada é calculado nem lembrado por um LLM, então não há número inventado nem associado à estação errada.

O papel de cada coluna vem do `ResultShape` declarado pelo compilador (qual é o valor, qual é a base, se é contagem, quais são as chaves e os
atributos): o texto não adivinha pelo nome da variável. A resposta diz também COMO a pergunta foi entendida, o que foi decidido por regra e as
ressalvas.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from metqa.domain.contract import Status

from ..domain import CanonicalQuery, Executed, ResultShape
from ..execution import rows
from ..knowledge import DomainCatalog

AGG = {"avg": "média", "max": "máxima", "min": "mínima", "sum": "total", "count": "contagem"}
AGG_ART = {"avg": "a média", "max": "a máxima", "min": "a mínima", "sum": "o total", "count": "a contagem"}
OPS = {">": "acima de", ">=": "de pelo menos", "<": "abaixo de", "<=": "de no máximo", "=": "igual a"}
COUNTED = {"readings": "leituras", "hours": "horas distintas", "reports": "boletins", "days": "dias"}
DIMS = {"station": "estação", "year": "ano", "month": "mês", "day": "dia", "value": "valor medido"}
STATION_NS = "https://example.org/kgqa-met/data/station/"
UNIT_NS = "http://qudt.org/vocab/unit/"


def num(v: Any, places: int = 2) -> str:
    """Número em português: 1.234,5 (sem zeros à direita)."""
    if v is None:
        return "n/d"
    d = Decimal(str(v)).quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP)       # 0,125 -> 0,13 (o float binário daria 0,12)
    if d == d.to_integral_value():
        return f"{int(d):,}".replace(",", ".")
    s = f"{d:,.{places}f}".rstrip("0").rstrip(".")
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def top(order: dict) -> str:
    """{"direction": "desc", "limit": 1} -> "só o maior"; limit 3 -> "só os 3 maiores"."""
    big = order["direction"] == "desc"
    if order["limit"] == 1:
        return "só o maior" if big else "só o menor"
    return f"só os {order['limit']} {'maiores' if big else 'menores'}"


def unit_of(c: dict, q: CanonicalQuery, catalog: DomainCatalog) -> str:
    """O símbolo da unidade em que a condição foi DITA (5 km continua 5 km no texto; a consulta usa a unidade canônica)."""
    if c.get("unit"):
        return catalog.symbol(UNIT_NS + c["unit"].split(":")[-1])
    m = catalog.measure(q.measure)
    return m.symbol if m else ""


def shown(q: CanonicalQuery, catalog: DomainCatalog):
    """(conversor, símbolo) do valor da medida na unidade pedida pela pergunta ("em km"); sem pedido, a canônica (E156 do novo_c)."""
    m = catalog.measure(q.measure)
    if not q.unit or not m:
        return (lambda v: v), (m.symbol if m else "")
    return (lambda v: catalog.from_canonical(v, q.unit, q.measure)), catalog.symbol(UNIT_NS + q.unit.split(":")[-1])


def _where(q: CanonicalQuery, catalog: DomainCatalog) -> str:
    return "em " + ", ".join(catalog.station_label(s["iri"]) for s in q.stations) if q.stations else "em todas as estações"


def _zone(q: CanonicalQuery, r: dict[str, Any], catalog: DomainCatalog) -> str:
    """Zona da hora civil em que o instante é mostrado: a da estação da linha, ou a única estação da pergunta."""
    code = r.get("station") or (q.stations[0]["iri"].rsplit("/", 1)[-1] if len(q.stations) == 1 else None)
    return catalog.index.station_zone(STATION_NS + str(code)) if code else "America/Sao_Paulo"


def _cond(q: CanonicalQuery, catalog: DomainCatalog) -> str:
    m = catalog.measure(q.measure)
    parts = [f"{m.label} {OPS.get(c['op'], c['op'])} {num(c['value'])} {unit_of(c, q, catalog)}".strip() for c in q.conditions]
    return (", com " + " e ".join(parts)) if parts else ""


def _local(t: str, zone: str) -> str:
    """Instante UTC do grafo na hora civil da estação."""
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(ZoneInfo(zone)).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return t


def _int(v: Any) -> str:
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return "?"


def _keys(r: dict[str, Any], q: CanonicalQuery, sh: ResultShape, catalog: DomainCatalog) -> str:
    out = []
    for d in q.group_by:
        if d == "station":
            out.append(catalog.station_label(STATION_NS + str(r.get("station", "?"))))
        elif d == "year":
            out.append(_int(r.get("year")))
        elif d == "month":
            out.append(f"{_int(r.get('month')).zfill(2)}/{_int(r.get('year'))}")
        elif d == "day":
            day = str(r.get("day", "?"))
            out.append(f"{day[8:10]}/{day[5:7]}/{day[:4]}" if len(day) >= 10 else day)
        elif d == "value":
            out.append(num(r.get("measured")))
    taken = {"station", "year", "month", "day", "measured"}
    out += [str(r.get(k, "?")) for k in sh.keys if k not in taken]          # atributos usados como dimensão (cabeceira...)
    return " · ".join(out)


def _amount(v: Any, sh: ResultShape, sym: str) -> str:
    return num(v) if sh.is_count else f"{num(v)} {sym}".strip()


def _one(e: Executed, catalog: DomainCatalog) -> list[str]:
    q, m, sh = e.part.query, catalog.measure(e.part.query.measure), e.shape
    rs, (cv, sym) = rows(e.results), shown(q, catalog)
    head = f"{m.label} {_where(q, catalog)}, {q.scope.describe()}{_cond(q, catalog)}"
    if e.status == Status.NO_RESULTS or not rs:
        return [f"Não há registros de {head}."]
    if q.intent == "instant":
        return [f"{m.label.capitalize()} {_where(q, catalog)} {q.scope.describe()}:"] + \
               [f"- {num(cv(r.get(sh.value)))} {sym} (leitura de {_local(str(r.get(sh.time, '')), _zone(q, r, catalog))})" for r in rs]
    if sh.attributes:
        return [f"{AGG[q.aggregation].capitalize()} de {head}:"] + \
               [f"- {num(cv(r.get(sh.value)))} {sym} em {_local(str(r.get(sh.time, '')), _zone(q, r, catalog))} ("
                + ", ".join(f"{iri.rsplit('#', 1)[-1].split(':')[-1]}: {r.get(col, '?')}" for iri, col in sh.attributes) + ")" for r in rs]
    if q.daily:
        r, d = rs[0], q.daily
        return [f"{num(r.get(sh.value))} dias {_where(q, catalog)}, {q.scope.describe()}, em que a {AGG[d['agg']]} diária de {m.label} ficou "
                f"{OPS[d['op']]} {num(d['value'])} {unit_of(d, q, catalog)} (de {num(r.get(sh.n))} dias com dados)."]
    if not sh.keys:
        r = rs[0]
        if sh.is_count:
            counted = COUNTED.get(q.count_of or "readings")
            base = f" (de {num(r.get(sh.n))} {counted} no recorte)" if sh.n and sh.n != sh.value else ""
            return [f"{num(r.get(sh.value))} {counted} de {head}{base}."]
        return [f"{AGG[q.aggregation].capitalize()} de {head}: {num(cv(r.get(sh.value)))} {sym} (sobre {num(r.get(sh.n))} leituras)."]
    tie = ""
    if q.order:                                       # a consulta traz uma linha a mais: ela só aparece se empata com a última pedida
        k = q.order["limit"]
        if len(rs) > k and rs[k].get(sh.value) == rs[k - 1].get(sh.value):
            tie = " — empate no limite: há outros empatados; a lista pode não incluir todos"
            rs = [r for r in rs if r.get(sh.value) != rs[k - 1].get(sh.value)][:k - 1] + [r for r in rs if r.get(sh.value) == rs[k - 1].get(sh.value)]
        else:
            rs = rs[:k]
    calc = "número de leituras" if sh.is_count else AGG[q.aggregation]
    lines = [f"{calc.capitalize()} de {head}, por {', '.join(DIMS.get(d, d.rsplit('#', 1)[-1].split(':')[-1]) for d in q.group_by)}"
             + (f" ({top(q.order)}{tie})" if q.order else "") + ":"]
    for r in rs:
        value = num(r.get(sh.value)) if sh.is_count else f"{num(cv(r.get(sh.value)))} {sym} (n = {num(r.get(sh.n))})"
        lines.append(f"- {_keys(r, q, sh, catalog)}: {value}")
    if "station" in q.group_by and q.stations and not q.order:     # estação citada que não voltou: dito, não omitido (E205 do novo_c)
        seen = {str(r.get("station")) for r in rs}
        lines += [f"- {catalog.station_label(s['iri'])}: sem registros" for s in q.stations if s["iri"].rsplit("/", 1)[-1] not in seen]
    return lines


def _compare(done: list[Executed], catalog: DomainCatalog) -> list[str]:
    lines, vals = [], []
    for e in done:
        rs = rows(e.results)
        cv = (lambda v: v) if e.shape.is_count else shown(e.part.query, catalog)[0]
        vals.append((e.part.label, cv(rs[0].get(e.shape.value)) if rs and e.status == Status.ANSWERED else None))
        lines.append(f"- {e.part.label}: " + _one(e, catalog)[0])
    unit = "" if done[0].shape.is_count else f" {shown(done[0].part.query, catalog)[1]}"
    what = "estações" if len({e.part.query.stations[0]["iri"] for e in done if e.part.query.stations}) > 1 else "períodos"
    if any(e.truncated for e in done):
        lines.append("Não dá para declarar vencedor: há resultados parciais.")
    elif any(v is None for _, v in vals):
        lines.append(f"Não dá para comparar: há {what} sem registros.")
    elif len({v for _, v in vals}) == 1:
        lines.append(f"{'Os' if what == 'períodos' else 'As'} {len(vals)} {what} têm o mesmo valor.")
    else:
        ranked = sorted(vals, key=lambda x: -x[1])
        (lb, b), (ls, s) = ranked[0], ranked[-1]
        lb = ", ".join(label for label, value in ranked if value == b)
        rest = f" contra {num(s)}" if len(vals) == 2 else f"; menor em {ls}: {num(s)}"
        lines.append(f"Maior em {lb}: {num(b)}{rest} (diferença de {num(b - s)}{unit}).")
    return lines


def render(done: list[Executed], combine: str, catalog: DomainCatalog, caveats: list[str]) -> str:
    lines = _compare(done, catalog) if combine == "compare" else _one(done[0], catalog)
    q = done[0].part.query
    if q.scope.start is not None or q.scope.instant is not None:
        q.assumptions.append("dias e horas na hora local de cada estação")
    notes = list(dict.fromkeys(a for e in done for a in e.part.query.assumptions))
    if notes:
        lines.append("Como entendi: " + "; ".join(notes) + ".")
    if caveats:
        lines.append("Ressalvas: " + " ".join(c if c.endswith(".") else c + "." for c in caveats))
    return "\n".join(lines)


def units_of(e: Executed, catalog: DomainCatalog) -> dict[str, str]:
    m = catalog.measure(e.part.query.measure)
    if not m or not m.unit:
        return {}
    return {**({e.shape.value: m.unit} if not e.shape.is_count else {}),
            **({"measured": m.unit} if "value" in e.part.query.group_by else {})}


def presentation_of(e: Executed, catalog: DomainCatalog) -> dict:
    """Converted values are separate from unmodified SPARQL bindings."""
    from copy import deepcopy
    from ..execution.source import typed_rows
    values = deepcopy(typed_rows(e.results))
    cv, symbol = shown(e.part.query, catalog)
    if not e.shape.is_count:
        for row in values:
            if row.get(e.shape.value) is not None:
                row[e.shape.value] = cv(row[e.shape.value])
    units = units_of(e, catalog)
    if e.part.query.unit and not e.shape.is_count:
        units[e.shape.value] = UNIT_NS + e.part.query.unit.split(":")[-1]
    return {"label": e.part.label, "rows": [{k: str(v) if isinstance(v, Decimal) else v for k,v in r.items()} for r in values],
            "units": units, "decimal_encoding": "string", "display_places": 2, "truncated": e.truncated}
