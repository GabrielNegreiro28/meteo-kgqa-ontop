"""Apresentação DETERMINÍSTICA (documento da arquitetura, §12, sintetizador): o texto é montado das linhas já verificadas, com número,
unidade, estação e período; nada é calculado nem lembrado por um LLM, então não há número inventado nem associado à estação errada.

O papel de cada coluna vem do `ResultShape` declarado pelo compilador (qual é o valor, qual é a base, se é contagem, quais são as chaves e os
atributos): o texto não adivinha pelo nome da variável. A resposta diz também COMO a pergunta foi entendida, o que foi decidido por regra e as
ressalvas.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from kgqa.contract import Status

from ..domain import CanonicalQuery, Executed, ResultShape
from ..execution import rows
from ..knowledge import DomainCatalog

AGG = {"avg": "média", "max": "máxima", "min": "mínima", "sum": "total", "count": "contagem"}
AGG_ART = {"avg": "a média", "max": "a máxima", "min": "a mínima", "sum": "o total", "count": "a contagem"}
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


def _where(q: CanonicalQuery) -> str:
    return "em " + ", ".join(s["iri"].rsplit("/", 1)[-1] for s in q.stations) if q.stations else "em todas as estações"


def _cond(q: CanonicalQuery, catalog: DomainCatalog) -> str:
    m = catalog.measure(q.measure)
    parts = [f"{m.label} {OPS.get(c['op'], c['op'])} {num(c['value'])} {unit_of(c, q, catalog)}".strip() for c in q.conditions]
    return (", com " + " e ".join(parts)) if parts else ""


def _local(t: str) -> str:
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(LOCAL).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return t


def _int(v: Any) -> str:
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return "?"


def _keys(r: dict[str, Any], q: CanonicalQuery, sh: ResultShape) -> str:
    out = []
    for d in q.group_by:
        if d == "station":
            out.append(str(r.get("station", "?")))
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
    rs, sym = rows(e.results), m.symbol
    head = f"{m.label} {_where(q)}, {q.scope.describe()}{_cond(q, catalog)}"
    if e.status == Status.NO_RESULTS or not rs:
        return [f"Não há registros de {head}."]
    if q.intent == "instant":
        return [f"{m.label.capitalize()} {_where(q)} {q.scope.describe()}:"] + \
               [f"- {num(r.get(sh.value))} {sym} (leitura de {_local(str(r.get(sh.time, '')))})" for r in rs]
    if sh.attributes:
        return [f"{AGG[q.aggregation].capitalize()} de {head}:"] + \
               [f"- {num(r.get(sh.value))} {sym} em {_local(str(r.get(sh.time, '')))} ("
                + ", ".join(f"{iri.rsplit('#', 1)[-1].split(':')[-1]}: {r.get(col, '?')}" for iri, col in sh.attributes) + ")" for r in rs]
    if q.daily:
        r, d = rs[0], q.daily
        return [f"{num(r.get(sh.value))} dias {_where(q)}, {q.scope.describe()}, em que a {AGG[d['agg']]} diária de {m.label} ficou "
                f"{OPS[d['op']]} {num(d['value'])} {unit_of(d, q, catalog)} (de {num(r.get(sh.n))} dias com dados)."]
    if not sh.keys:
        r = rs[0]
        if sh.is_count:
            counted = COUNTED.get(q.count_of or "readings")
            base = f" (de {num(r.get(sh.n))} {counted} no recorte)" if sh.n and sh.n != sh.value else ""
            return [f"{num(r.get(sh.value))} {counted} de {head}{base}."]
        return [f"{AGG[q.aggregation].capitalize()} de {head}: {num(r.get(sh.value))} {sym} (sobre {num(r.get(sh.n))} leituras)."]
    calc = "número de leituras" if sh.is_count else AGG[q.aggregation]
    lines = [f"{calc.capitalize()} de {head}, por {', '.join(DIMS.get(d, d.rsplit('#', 1)[-1].split(':')[-1]) for d in q.group_by)}"
             + (f" ({top(q.order)})" if q.order else "") + ":"]
    for r in rs:
        value = num(r.get(sh.value)) if sh.is_count else f"{num(r.get(sh.value))} {sym} (n = {num(r.get(sh.n))})"
        lines.append(f"- {_keys(r, q, sh)}: {value}")
    return lines


def _compare(done: list[Executed], catalog: DomainCatalog) -> list[str]:
    lines, vals = [], []
    for e in done:
        rs = rows(e.results)
        vals.append((e.part.label, rs[0].get(e.shape.value) if rs and e.status == Status.ANSWERED else None))
        lines.append(f"- {e.part.label}: " + _one(e, catalog)[0])
    (la, a), (lb, b) = vals[0], vals[1]
    unit = "" if done[0].shape.is_count else f" {catalog.measure(done[0].part.query.measure).symbol}"
    if a is None or b is None:
        lines.append("Não dá para comparar: um dos períodos não tem registros.")
    elif a == b:
        lines.append("Os dois períodos têm o mesmo valor.")
    else:
        big, small = ((la, a), (lb, b)) if a > b else ((lb, b), (la, a))
        lines.append(f"Maior em {big[0]}: {num(big[1])} contra {num(small[1])} (diferença de {num(abs(a - b))}{unit}).")
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


def units_of(e: Executed, catalog: DomainCatalog) -> dict[str, str]:
    m = catalog.measure(e.part.query.measure)
    if not m or not m.unit or e.shape.is_count:
        return {}
    return {e.shape.value: m.unit, **({"measured": m.unit} if "value" in e.part.query.group_by else {})}
