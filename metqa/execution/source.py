"""Executor atrás da porta `SparqlSource` (documento da arquitetura, §10: adaptador de fonte).

Adaptadores: `kgqa/store.py::OntopBackend` (grafo real: Ontop sobre PostgreSQL) e `LocalRdflibBackend` (grafo sintético, testes).
Proteção em camadas, já existente: política somente-leitura (`check_policy`: só SELECT/ASK, sem SERVICE/FROM/caminhos), papel de banco
`kgqa_reader` somente-leitura com `statement_timeout`, Ontop só no loopback.

Defesa em profundidade: mesmo montada por código, a consulta passa pelas regras de consulta (`validate_query`) e pela checagem prévia do
próprio motor (`/ontop/reformulate`), que também devolve o SQL gerado para a procedência.
"""
from __future__ import annotations

from typing import Any, Protocol

from kgqa.contract import Diagnostic, Status
from kgqa.store import PREFIXES, ExecResult
from pipeline.validators import validate_query

from ..domain import CompiledQuery, Executed, ResultShape, Stop, SubQuery
from ..knowledge import DomainCatalog
from ..planning import to_interp


class SparqlSource(Protocol):
    source_id: str

    def select(self, query: str, timeout_s: float = ..., max_rows: int = ...) -> ExecResult: ...


def result_status(results: dict[str, Any] | None, shape: ResultShape) -> Status:
    """Vazio de verdade pelo papel declarado das colunas: sem linhas, ou base (`n`) zero em todas as linhas. Uma contagem 0 com base > 0 é
    uma resposta ("nenhuma leitura cumpre"), não ausência de dados; um SUM sobre conjunto vazio (0 pela SPARQL 1.1) tem base 0."""
    rs = rows(results)
    if not rs:
        return Status.NO_RESULTS
    if shape.n and all(not r.get(shape.n) for r in rs):
        return Status.NO_RESULTS
    return Status.ANSWERED


def execute(part: SubQuery, compiled: CompiledQuery, catalog: DomainCatalog, source: SparqlSource, *, timeout_s: float, max_rows: int,
            log=lambda *a, **k: None) -> Executed | Stop:
    sparql = compiled.sparql
    _, findings = validate_query(sparql, to_interp(part.query), catalog.index, True)
    log("validate_query", findings=[f.diag.code for f in findings], sparql=sparql)
    if findings:                                   # consulta montada por código que não passa nas regras: defeito do sistema, nunca resposta
        return Stop(Status.REJECTED, [f.diag for f in findings])
    engine_sql = None
    reform = getattr(source, "reformulate", None)
    if reform is not None:
        r = reform(PREFIXES + sparql)
        log("engine_check", status=r.status, findings=[])
        if r.status == "empty":
            return Stop.of(Status.REJECTED, "EMPTY_BY_CONSTRUCTION", "O motor provou que esta consulta nunca devolve linhas.", "error")
        if r.status == "rejected":
            return Stop.of(Status.REJECTED, "ENGINE_REJECTED", f"O motor recusou a consulta: {(r.detail or '')[:200]}", "error")
        engine_sql = r.sql if r.status == "ok" else None
    ex = source.select(PREFIXES + sparql, timeout_s=timeout_s, max_rows=max_rows)
    log("execute", ok=ex.ok, kind=ex.error_kind, detail=str(ex.error or "")[:300])
    if not ex.ok:                                  # detalhe interno (URL, pilha) fica na trilha, não na resposta
        msg = "A fonte não respondeu dentro do limite de tempo." if ex.error_kind == "timeout" else "Falha ao executar a consulta na fonte."
        return Stop(Status.EXECUTION_ERROR, [Diagnostic((ex.error_kind or "runtime").upper(), "error", msg)])
    return Executed(part, sparql, ex.results, ex.truncated, result_status(ex.results, compiled.shape), engine_sql, compiled.shape)


def rows(results: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Linhas como dicionários de valores Python (números como float, IRIs pelo nome local)."""
    out = []
    for b in (results or {}).get("results", {}).get("bindings", []):
        row = {}
        for k, t in b.items():
            v = t.get("value")
            if t.get("type") == "uri":
                row[k] = v.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
            elif t.get("datatype", "").rsplit("#", 1)[-1] in {"integer", "decimal", "double", "float", "int", "long"}:
                row[k] = float(v)
            else:
                row[k] = v
        out.append(row)
    return out
