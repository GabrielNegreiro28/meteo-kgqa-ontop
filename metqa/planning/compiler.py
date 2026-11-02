"""Compilador: consulta canônica -> SPARQL + o papel de cada coluna (`ResultShape`). O ÚNICO caminho para SPARQL no MVP; o que ele não sabe
montar é `unsupported`, nunca SPARQL escrito por LLM (documento da arquitetura, §4: "agentes não escrevem a consulta de conceitos governados").

Reaproveita `pipeline/compiler.py::compile_structured` (agregação, agrupamento, top-N, superlativo com atributo, dias com condição, parte do
dia, dias da semana, horas distintas, boletins), conferido contra pandas e no grafo real. Acrescenta a intenção `instant` e, na contagem com
condição, a base (quantas leituras havia no recorte), para distinguir "nenhuma cumpre" de "não há dados".
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timezone

from .sparql import _attr_var, compile_structured
from metqa.verification.rules import PipelineInterpretation
from metqa.knowledge.index import _short, expand

from ..domain import CanonicalQuery, CompiledQuery, ResultShape
from ..knowledge import DomainCatalog

KEY_COLUMNS = {"station": ("station",), "year": ("year",), "month": ("year", "month"), "day": ("day",), "value": ("measured",)}


def to_interp(cq: CanonicalQuery) -> PipelineInterpretation:
    """A consulta canônica na forma que o compilador e as regras de consulta já existentes entendem (adaptador da migração)."""
    s = cq.scope
    period = None if s.start is None else {"start": s.start.isoformat(), "end": s.end.isoformat(), "tz": "-03:00", "inclusive_end": True}
    return PipelineInterpretation(properties=[cq.measure], entities=[{"text": e.get("text", ""), "iri": e["iri"]} for e in cq.stations],
                                  filters=list(cq.conditions), period=period, aggregation=cq.aggregation, record_kind="observation",
                                  instant=s.instant.isoformat() if s.instant else None, group_by=list(cq.group_by),
                                  attributes=list(cq.attributes), order=cq.order, daily=cq.daily,
                                  local_hours=sorted(s.hours) if s.hours else None,
                                  weekdays=list(s.weekdays) if s.weekdays else None, count_of=cq.count_of)


def _instant(cq: CanonicalQuery, catalog: DomainCatalog) -> CompiledQuery | None:
    """O valor lido num horário ("às 12h"): a leitura cujo instante (UTC no grafo) é o pedido."""
    info = catalog.index.properties.get(cq.measure)
    if info is None or not info.kind or len(cq.stations) != 1 or cq.conditions or cq.group_by:
        return None
    t = cq.scope.instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sparql = (f"SELECT ?value ?t WHERE {{\n  <{cq.stations[0]['iri']}> sosa:hosts ?sensor .\n"
              f"  ?obs a {_short(info.kind)} ; sosa:madeBySensor ?sensor ; sosa:observedProperty {_short(cq.measure)} ;\n"
              f"     sosa:hasResult/qudt:numericValue ?value .\n  ?obs sosa:resultTime ?t .\n"
              f'  FILTER(?t = "{t}"^^xsd:dateTime)\n}} ORDER BY ?value')
    return CompiledQuery(sparql, ResultShape("value", time="t"))


def _shape(cq: CanonicalQuery) -> ResultShape:
    count = cq.aggregation == "count"
    if cq.daily:
        return ResultShape("value", "n", "days", is_count=True)
    keys = tuple(dict.fromkeys(c for d in cq.group_by for c in KEY_COLUMNS.get(d, (_attr_var(expand(d)),))))
    attrs = tuple((a, _attr_var(expand(a))) for a in cq.attributes)
    return ResultShape("n" if count else "value", "n", is_count=count, keys=keys, attributes=attrs, time="t" if attrs else None)


def compile_query(cq: CanonicalQuery, catalog: DomainCatalog) -> CompiledQuery | None:
    if cq.intent == "instant" or cq.scope.instant is not None:
        return _instant(cq, catalog)
    # ranking: uma linha a mais, para o texto dizer o empate em vez de escolher um dos empatados (E208 do novo_c)
    wide = replace(cq, order={**cq.order, "limit": cq.order["limit"] + 1}) if cq.order else cq
    sparql = compile_structured(to_interp(wide), catalog.index, force=True)
    if not sparql:
        return None
    if cq.aggregation == "count" and cq.conditions and not (cq.daily or cq.group_by or cq.order or cq.attributes):
        # contagem com condição: o que cumpre (value) e a base sem a condição (n); n = 0 é "sem dados", value = 0 com n > 0 é uma resposta
        base = compile_structured(to_interp(replace(cq, conditions=[])), catalog.index, force=True)
        if not base:
            return None
        hit = sparql.replace("AS ?n)", "AS ?value)", 1)
        sparql = f"SELECT ?value ?n WHERE {{\n  {{ {hit} }}\n  {{ {base} }}\n}}"
        return CompiledQuery(sparql, ResultShape("value", "n", is_count=True))
    return CompiledQuery(sparql, _shape(cq))
