"""Compilador: consulta canônica -> SPARQL. O ÚNICO caminho para SPARQL no MVP; o que ele não sabe montar é `unsupported`, nunca SPARQL
escrito por LLM (documento da arquitetura, §4: "agentes não escrevem a consulta de conceitos governados").

Reaproveita `pipeline/compiler.py::compile_structured` (agregação, agrupamento, top-N, superlativo com atributo, dias com condição, parte do
dia, dias da semana, horas distintas, boletins), conferido contra pandas e no grafo real. Acrescenta a intenção `instant`.
"""
from __future__ import annotations

from datetime import timezone

from pipeline.compiler import compile_structured
from pipeline.validators import PipelineInterpretation
from pipeline.vocab import _short

from ..domain import CanonicalQuery
from ..knowledge import DomainCatalog


def to_interp(cq: CanonicalQuery) -> PipelineInterpretation:
    """A consulta canônica na forma que o compilador e as regras de consulta já existentes entendem (adaptador da migração)."""
    s = cq.scope
    period = None if s.start is None else {"start": s.start.isoformat(), "end": s.end.isoformat(), "tz": "-03:00", "inclusive_end": True}
    return PipelineInterpretation(properties=[cq.measure], entities=[{"text": e.get("text", ""), "iri": e["iri"]} for e in cq.stations],
                                  filters=list(cq.conditions), period=period, aggregation=cq.aggregation, record_kind="observation",
                                  instant=s.instant.isoformat() if s.instant else None, group_by=list(cq.group_by),
                                  attributes=list(cq.attributes), order=cq.order, daily=cq.daily,
                                  hours=s.hours, weekdays=list(s.weekdays) if s.weekdays else None, count_of=cq.count_of)


def _instant(cq: CanonicalQuery, catalog: DomainCatalog) -> str | None:
    """O valor lido num horário ("às 12h"): a leitura cujo instante (UTC no grafo) é o pedido."""
    info = catalog.index.properties.get(cq.measure)
    if info is None or not info.kind or len(cq.stations) != 1 or cq.conditions or cq.group_by:
        return None
    t = cq.scope.instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (f"SELECT ?value ?t WHERE {{\n  <{cq.stations[0]['iri']}> sosa:hosts ?sensor .\n"
            f"  ?obs a {_short(info.kind)} ; sosa:madeBySensor ?sensor ; sosa:observedProperty {_short(cq.measure)} ;\n"
            f"     sosa:hasResult/qudt:numericValue ?value .\n  ?obs sosa:resultTime ?t .\n"
            f'  FILTER(?t = "{t}"^^xsd:dateTime)\n}} ORDER BY ?value')


def compile_query(cq: CanonicalQuery, catalog: DomainCatalog) -> str | None:
    if cq.intent == "instant" or cq.scope.instant is not None:
        return _instant(cq, catalog)
    return compile_structured(to_interp(cq), catalog.index, force=True)

