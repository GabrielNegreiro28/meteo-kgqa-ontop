"""Planejador (documento da arquitetura, §12, reduzido a uma fonte): uma consulta canônica vira 1 subconsulta; uma comparação vira de 2 a
MAX_PARTS subconsultas com a MESMA forma, combinadas em código (plano, D5):
- de 2 a 4 períodos, para uma estação;
- de 2 a 4 estações, para um período, quando a forma não sai numa consulta só agrupada por estação (dias que cumprem uma condição, horas
  distintas, boletins). As outras formas com várias estações viram uma série por estação, numa consulta.
Cada parte dá UM valor (agregação simples ou contagem, inclusive `daily`). Plano maior que isso é `unsupported`, dito."""
from __future__ import annotations

from dataclasses import replace

from metqa.domain.contract import Status

from ..domain import CanonicalQuery, Plan, Stop, SubQuery

COMPARABLE = ("value", "count", "comparison")
MAX_PARTS = 4


def _one_value(cq: CanonicalQuery) -> bool:
    return not (cq.group_by or cq.order or cq.attributes) and cq.aggregation is not None and cq.scope.instant is None


def _per_station(cq: CanonicalQuery) -> bool:
    """Formas que o compilador só monta para UMA estação: viram uma parte por estação."""
    return bool(cq.daily) or cq.count_of in ("hours", "reports")


def _normalize(cq: CanonicalQuery) -> CanonicalQuery:
    """Duas ou mais estações citadas sem pedir agrupamento ("SBNT ou SBSG teve a maior média?"): um valor por estação, dito."""
    if len(cq.stations) > 1 and "station" not in cq.group_by and cq.intent in COMPARABLE:
        cq.group_by = ["station", *cq.group_by]
        cq.intent = "series"
        cq.assumptions.append("a pergunta cita várias estações: mostro um valor para cada uma")
    return cq


def plan(parts: list[tuple[str, CanonicalQuery]]) -> Plan | Stop:
    shape_msg = (f"Comparo de 2 a {MAX_PARTS} períodos (para uma estação) ou de 2 a {MAX_PARTS} estações (para um período), "
                 "com um valor em cada (ex.: a média de cada um).")
    if len(parts) == 1:
        cq = parts[0][1]
        if len(cq.stations) > 1 and _per_station(cq) and _one_value(cq):
            if len(cq.stations) > MAX_PARTS:
                return Stop.of(Status.UNSUPPORTED, "PLAN_TOO_LARGE", shape_msg)
            subs = [SubQuery(s["iri"].rsplit("/", 1)[-1], replace(cq, stations=[s], intent="comparison", assumptions=list(cq.assumptions)))
                    for s in cq.stations]
            return Plan(subs, combine="compare")
        return Plan([SubQuery("", _normalize(cq))])
    if len(parts) > MAX_PARTS:
        return Stop.of(Status.UNSUPPORTED, "PLAN_TOO_LARGE", shape_msg)
    for _, cq in parts:
        if not _one_value(cq) or len(cq.stations) > 1:
            return Stop.of(Status.UNSUPPORTED, "COMPARISON_SHAPE", shape_msg)
    return Plan([SubQuery(label, cq) for label, cq in parts], combine="compare")
