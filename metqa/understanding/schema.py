"""Esquema da interpretação normalizada e conversão para a consulta canônica.

Confere TIPOS e VALORES (datas válidas, início <= fim, horas 0–23, dias 0–6, operadores, agregações), nunca a forma de escrever: a linguagem
é do LLM; aqui só se garante que o que ele devolveu é uma consulta bem-formada. Erro de forma volta ao LLM numa rodada de reparo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from metqa.verification.rules import AGGREGATIONS, MAX_LIMIT
from metqa.knowledge.index import expand

from ..domain import CanonicalQuery, TimeScope
from ..domain.types import COUNT_OF

OPS = {">", ">=", "<", "<=", "="}
DAILY_AGGS = {"max", "min", "avg", "sum"}


@dataclass
class Parsed:
    status: str = "ok"
    parts: list[tuple[str, CanonicalQuery]] = field(default_factory=list)   # (rótulo, consulta); 2 a 4 partes = comparação de períodos
    errors: list[str] = field(default_factory=list)
    reason: str = ""
    alternatives: list[str] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    paraphrase: str = ""
    raw: dict[str, Any] = field(default_factory=dict)        # a interpretação como o LLM devolveu (vai para a memória se for verificada)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _date(v: Any, what: str, errors: list[str]) -> date | None:
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        errors.append(f"{what}: data inválida {v!r} (use AAAA-MM-DD)")
        return None


def _int_set(v: Any, lo: int, hi: int, what: str, errors: list[str]) -> tuple[int, ...] | None:
    if v is None:
        return None
    if not isinstance(v, list) or not v or not all(isinstance(x, int) and not isinstance(x, bool) and lo <= x <= hi for x in v):
        errors.append(f"{what} deve ser null ou lista de inteiros de {lo} a {hi}")
        return None
    return tuple(sorted(set(v)))


def _condition(c: Any, what: str, errors: list[str], daily: bool = False) -> dict | None:
    if not isinstance(c, dict) or c.get("op") not in OPS or not _is_num(c.get("value")) or (daily and c.get("agg") not in DAILY_AGGS):
        errors.append(f"{what} inválida: {c!r}")
        return None
    out = {"op": c["op"], "value": c["value"]}
    if daily:
        out["agg"] = c["agg"]
    if c.get("unit"):
        out["unit"] = str(c["unit"]) if str(c["unit"]).startswith("unit:") else f"unit:{c['unit']}"
    return out


def _constant(dim: str, cq: CanonicalQuery) -> bool:
    """Agrupar por uma dimensão que só tem um valor no recorte não muda o resultado (ano dentro de uma janela de um ano, estação com uma
    estação só): normalizado fora, para que duas leituras que diferem só nisso concordem (E112 do novo_b)."""
    s = cq.scope
    if dim == "station":
        return len(cq.stations) == 1 and not cq.order
    if s.start is None or cq.order:
        return False
    return {"year": s.start.year == s.end.year, "month": (s.start.year, s.start.month) == (s.end.year, s.end.month),
            "day": s.start == s.end}.get(dim, False)


def intent_of(cq: CanonicalQuery, compare: bool) -> str:
    if compare:
        return "comparison"
    if cq.scope.instant is not None:
        return "instant"
    if cq.attributes:
        return "extreme_with_attribute"
    if cq.order:
        return "ranking"
    if cq.group_by:
        return "series"
    return "count" if cq.aggregation == "count" else "value"


def parse(raw: dict[str, Any]) -> Parsed:
    p = Parsed(status=raw.get("status", "ok") if raw.get("status") in ("ok", "needs_clarification", "unsupported") else "ok",
               reason=str(raw.get("reason") or ""), paraphrase=str(raw.get("paraphrase") or ""),
               raw={k: v for k, v in raw.items() if k != "paraphrase"})
    p.alternatives = [str(a) for a in raw.get("alternatives") or [] if str(a).strip()] if isinstance(raw.get("alternatives"), list) else []
    p.evidence = {str(k): str(v) for k, v in (raw.get("evidence") or {}).items() if isinstance(v, str) and v.strip()} \
        if isinstance(raw.get("evidence"), dict) else {}
    p.assumptions = [str(a) for a in raw.get("assumptions") or [] if str(a).strip()] if isinstance(raw.get("assumptions"), list) else []
    if p.status != "ok":
        return p
    e = p.errors
    measure = raw.get("measure")
    if not isinstance(measure, str) or not measure:
        e.append("'measure' deve ser o IRI de UMA grandeza do cardápio (ex.: \"met:AirTemperature\")")
    stations = raw.get("stations") or []
    if not isinstance(stations, list) or not all(isinstance(s, str) for s in stations):
        e.append("'stations' deve ser lista de IRIs de estação (ex.: [\"st:SBGL\"])")
        stations = []
    time = raw.get("time") or {}
    calc = raw.get("calc") or {}
    shape = raw.get("shape") or {}
    for name, obj in (("time", time), ("calc", calc), ("shape", shape)):
        if not isinstance(obj, dict):
            e.append(f"'{name}' deve ser um objeto")
    if e:
        return p

    ranges = []
    for i, r in enumerate(time.get("ranges") or []):
        if not isinstance(r, dict):
            e.append(f"time.ranges[{i}] deve ser {{\"start\", \"end\"}}")
            continue
        s, t = _date(r.get("start"), f"time.ranges[{i}].start", e), _date(r.get("end"), f"time.ranges[{i}].end", e)
        if s and t and s > t:
            e.append(f"time.ranges[{i}]: início {s} depois do fim {t}")
        elif s and t:
            ranges.append((s, t))
    if len(ranges) > 4:
        e.append("no máximo quatro janelas de tempo (uma, ou uma por período numa comparação)")
    hours = _int_set(time.get("local_hours"), 0, 23, "time.local_hours", e)
    weekdays = _int_set(time.get("weekdays"), 0, 6, "time.weekdays", e)
    instant = None
    if time.get("instant"):
        try:
            instant = datetime.fromisoformat(str(time["instant"]))
            if instant.tzinfo is None:
                raise ValueError
        except ValueError:
            e.append("time.instant deve ser AAAA-MM-DDThh:mm:00-03:00 (com fuso)")
        if ranges:
            e.append("time.instant e time.ranges juntos: um horário de um dia usa só 'instant'")

    agg = calc.get("aggregation")
    if agg is not None and agg not in AGGREGATIONS:
        e.append(f"calc.aggregation inválida: {agg!r}")
    count_of = calc.get("count_of")
    if count_of is not None and count_of not in COUNT_OF:
        e.append(f"calc.count_of inválido: {count_of!r}")
    daily = _condition(calc["daily"], "calc.daily", e, daily=True) if calc.get("daily") else None
    conditions = [c for c in (_condition(c, f"conditions[{i}]", e) for i, c in enumerate(raw.get("conditions") or [])) if c]
    group_by = shape.get("group_by") or []
    attributes = shape.get("attributes") or []
    if not isinstance(group_by, list) or not all(isinstance(g, str) for g in group_by):
        e.append("shape.group_by deve ser lista de textos")
        group_by = []
    if not isinstance(attributes, list) or not all(isinstance(a, str) for a in attributes):
        e.append("shape.attributes deve ser lista de textos")
        attributes = []
    order = shape.get("order")
    if order is not None:
        if not (isinstance(order, dict) and order.get("direction") in ("asc", "desc") and isinstance(order.get("limit"), int)
                and 1 <= order["limit"] <= MAX_LIMIT):
            e.append(f"shape.order deve ser null ou {{\"direction\": \"asc\"|\"desc\", \"limit\": 1 a {MAX_LIMIT}}}")
            order = None
        else:
            order = {"by": "aggregate", "direction": order["direction"], "limit": order["limit"]}
    if e:
        return p

    windows = ranges or [(None, None)]
    for s, t in windows:
        label = "" if len(windows) == 1 else (f"{s:%d/%m/%Y}" if s == t else f"{s:%d/%m/%Y} a {t:%d/%m/%Y}")
        cq = CanonicalQuery(intent="value", measure=expand(measure),
                            stations=[{"iri": expand(x), "text": x.split(":")[-1]} for x in stations],
                            scope=TimeScope(s, t, hours, weekdays, instant), aggregation=agg, count_of=count_of,
                            conditions=list(conditions), daily=dict(daily) if daily else None, group_by=list(group_by),
                            attributes=list(attributes), order=order, spans=dict(p.evidence), assumptions=list(p.assumptions))
        cq.group_by = [g for g in cq.group_by if not _constant(g, cq)]
        if agg == "count" and cq.count_of is None:
            cq.count_of = "days" if daily else "readings"
            cq.assumptions.append("contei leituras" if not daily else "contei dias")
        cq.intent = intent_of(cq, len(windows) > 1)
        p.parts.append((label, cq))
    return p


def canonical_form(parts: list[tuple[str, CanonicalQuery]], to_canonical) -> list[dict[str, Any]]:
    """Forma comparável de uma interpretação (para a concordância entre leituras): listas ordenadas, limiares na unidade canônica da grandeza,
    sem os campos de texto (evidência, suposições), que podem variar sem mudar a consulta."""
    out = []
    for _, cq in parts:
        def canon(c: dict) -> tuple:
            v = to_canonical(c["value"], c.get("unit"), cq.measure)
            return (c.get("agg") or "", c["op"], f"{float(v):g}" if v is not None else f"?{c['value']}:{c.get('unit')}")
        s = cq.scope
        out.append({"measure": cq.measure, "stations": sorted(x["iri"] for x in cq.stations),
                    "range": (s.start.isoformat() if s.start else None, s.end.isoformat() if s.end else None),
                    "hours": s.hours, "weekdays": s.weekdays, "instant": s.instant.isoformat() if s.instant else None,
                    "aggregation": cq.aggregation, "count_of": cq.count_of, "conditions": sorted(canon(c) for c in cq.conditions),
                    "daily": canon(cq.daily) if cq.daily else None, "group_by": sorted(cq.group_by), "attributes": sorted(cq.attributes),
                    "order": (cq.order["direction"], cq.order["limit"]) if cq.order else None})
    return out
