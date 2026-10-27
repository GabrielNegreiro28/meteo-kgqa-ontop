"""Apresentação DETERMINÍSTICA (documento da arquitetura, §12, sintetizador): o texto é montado das linhas já verificadas, com número,
unidade, estação e período; nada é calculado nem lembrado por um LLM, então não há número inventado nem associado à estação errada.

A resposta diz também COMO a pergunta foi entendida (o usuário pode discordar), o que foi decidido por regra e as ressalvas.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from ..domain import CanonicalQuery, Executed
from ..execution import rows
from ..knowledge import DomainCatalog

AGG = {"avg": "média", "max": "máxima", "min": "mínima", "sum": "total", "count": "contagem"}
OPS = {">": "acima de", ">=": "de pelo menos", "<": "abaixo de", "<=": "de no máximo", "=": "igual a"}
COUNTED = {"readings": "leituras", "hours": "horas distintas", "reports": "boletins", "days": "dias"}
DIMS = {"station": "estação", "year": "ano", "month": "mês", "day": "dia", "value": "valor medido"}
LOCAL = timezone(timedelta(hours=-3))
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


def _where(q: CanonicalQuery) -> str:
    return "em " + ", ".join(s["iri"].rsplit("/", 1)[-1] for s in q.stations) if q.stations else "em todas as estações"


def _cond(q: CanonicalQuery, catalog: DomainCatalog) -> str:
    m = catalog.measure(q.measure)
    parts = []
    for c in q.conditions:
        unit = catalog.symbol(UNIT_NS + c["unit"].split(":")[-1]) if c.get("unit") else m.symbol
        parts.append(f"{m.label} {OPS.get(c['op'], c['op'])} {num(c['value'])} {unit}".strip())
    return (", com " + " e ".join(parts)) if parts else ""


def _local(t: str) -> str:
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(LOCAL).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return t


def _keys(r: dict[str, Any], q: CanonicalQuery) -> str:
    out = []
    for d in q.group_by:
        if d == "station":
            out.append(str(r.get("station", "?")))
        elif d == "year":
            out.append(num(r.get("year")))
        elif d == "month":
            out.append(f"{int(r['month']):02d}/{int(r['year'])}" if r.get("month") is not None else "?")
        elif d == "day":
            day = str(r.get("day", "?"))
            out.append(f"{day[8:10]}/{day[5:7]}/{day[:4]}" if len(day) >= 10 else day)
        elif d == "value":
            out.append(num(r.get("measured")))
        else:
            out.append(str(next((v for k, v in r.items() if k not in ("value", "n")), "?")))
    return " · ".join(out)


def _one(e: Executed, catalog: DomainCatalog) -> list[str]:
    q, m = e.part.query, catalog.measure(e.part.query.measure)
    rs, sym = rows(e.results), m.symbol
    head = f"{m.label} {_where(q)}, {q.scope.describe()}{_cond(q, catalog)}"
    if not rs or (q.aggregation != "count" and all(r.get("value") is None for r in rs) and q.intent in ("value", "comparison")):
        return [f"Não há registros de {head}."]
    if q.intent in ("value", "comparison") and q.aggregation != "count":
        r = rs[0]
        return [f"{AGG[q.aggregation].capitalize()} de {head}: {num(r.get('value'))} {sym} (sobre {num(r.get('n'))} leituras).".replace(" )", ")")]
    if q.intent in ("count", "comparison"):
        r = rs[0]
        if q.daily:
            d = q.daily
            return [f"{num(r.get('value'))} dias {_where(q)}, {q.scope.describe()}, em que a {AGG[d['agg']]} diária de {m.label} ficou "
                    f"{OPS[d['op']]} {num(d['value'])} {sym} (de {num(r.get('n'))} dias com dados)."]
        return [f"{num(r.get('n'))} {COUNTED.get(q.count_of or 'readings')} de {head}."]
    if q.intent == "instant":
        return [f"{m.label.capitalize()} {_where(q)} {q.scope.describe()}:"] + \
               [f"- {num(r.get('value'))} {sym} (leitura de {_local(str(r.get('t', '')))})" for r in rs]
    if q.intent == "extreme_with_attribute":
        attrs = [a.rsplit("#", 1)[-1] for a in q.attributes]
        return [f"{AGG[q.aggregation].capitalize()} de {head}:"] + \
               [f"- {num(r.get('value'))} {sym} em {_local(str(r.get('t', '')))} ("
                + ", ".join(f"{a}: {next((v for k, v in r.items() if k not in ('value', 't', 'n')), '?')}" for a in attrs) + ")" for r in rs]
    calc = "número de leituras" if q.aggregation == "count" else AGG[q.aggregation]
    lines = [f"{calc.capitalize()} de {head}, por {', '.join(DIMS.get(d, d.rsplit('#', 1)[-1]) for d in q.group_by)}"
             + (f" ({'maiores' if q.order['direction'] == 'desc' else 'menores'} {q.order['limit']})" if q.order else "") + ":"]
    for r in rs:
        value = num(r.get("n")) if q.aggregation == "count" else f"{num(r.get('value'))} {sym} (n = {num(r.get('n'))})"
        lines.append(f"- {_keys(r, q)}: {value}")
    return lines


def _compare(done: list[Executed], catalog: DomainCatalog) -> list[str]:
    lines = []
    vals = []
    for e in done:
        rs = rows(e.results)
        q = e.part.query
        v = (rs[0].get("n") if q.aggregation == "count" else rs[0].get("value")) if rs else None
        vals.append((e.part.label, v))
        lines += [f"- {e.part.label}: " + _one(e, catalog)[0]]
    (la, a), (lb, b) = vals
    m = catalog.measure(done[0].part.query.measure)
    if a is None or b is None:
        lines.append("Não dá para comparar: um dos períodos não tem registros.")
    elif a == b:
        lines.append("Os dois períodos têm o mesmo valor.")
    else:
        big, small = ((la, a), (lb, b)) if a > b else ((lb, b), (la, a))
        lines.append(f"Maior em {big[0]}: {num(big[1])} contra {num(small[1])} (diferença de {num(abs(a - b))} {m.symbol}).".replace(" )", ")"))
    return lines


def render(done: list[Executed], combine: str, catalog: DomainCatalog, caveats: list[str]) -> str:
    lines = _compare(done, catalog) if combine == "compare" else _one(done[0], catalog)
    q = done[0].part.query
    if q.scope.start is not None or q.scope.instant is not None:
        q.assumptions.append("dias e horas em UTC−3 (horário de Brasília), hipótese ainda não confirmada para todas as estações")
    notes = list(dict.fromkeys(a for e in done for a in e.part.query.assumptions))
    if notes:
        lines.append("Como entendi: " + "; ".join(notes) + ".")
    if caveats:
        lines.append("Ressalvas: " + " ".join(c if c.endswith(".") else c + "." for c in caveats))
    return "\n".join(lines)


def units_of(q: CanonicalQuery, catalog: DomainCatalog) -> dict[str, str]:
    m = catalog.measure(q.measure)
    if not m or not m.unit or q.aggregation == "count":
        return {}
    return {"value": m.unit, **({"measured": m.unit} if "value" in q.group_by else {})}
