"""Planejador mínimo (documento da arquitetura, §12, reduzido a uma fonte): uma consulta canônica vira 1 subconsulta; uma comparação de dois
períodos vira 2 subconsultas com a MESMA forma, combinadas em código. Plano maior que isso é `unsupported`, dito."""
from __future__ import annotations

from kgqa.contract import Status

from ..domain import CanonicalQuery, Plan, Stop, SubQuery

COMPARABLE = ("value", "count")


def _normalize(cq: CanonicalQuery) -> CanonicalQuery:
    """Duas ou mais estações citadas sem pedir agrupamento ("SBNT ou SBSG teve a maior média?"): um valor por estação, dito."""
    if len(cq.stations) > 1 and "station" not in cq.group_by and cq.intent in COMPARABLE:
        cq.group_by = ["station", *cq.group_by]
        cq.intent = "series"
        cq.assumptions.append("a pergunta cita várias estações: mostro um valor para cada uma")
    return cq


def plan(parts: list[tuple[str, CanonicalQuery]]) -> Plan | Stop:
    if len(parts) == 1:
        return Plan([SubQuery("", _normalize(parts[0][1]))])
    if len(parts) == 2:
        for _, cq in parts:
            if cq.group_by or cq.order or cq.attributes or cq.aggregation is None or len(cq.stations) > 1:
                return Stop.of(Status.UNSUPPORTED, "COMPARISON_SHAPE",
                               "Comparo dois períodos só com um valor por período (ex.: a média de cada um), para uma estação.")
        return Plan([SubQuery(label, cq) for label, cq in parts], combine="compare")
    return Stop.of(Status.UNSUPPORTED, "PLAN_TOO_LARGE", "Pergunte no máximo dois períodos por vez.")
