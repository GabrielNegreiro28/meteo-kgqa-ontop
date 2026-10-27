"""Orquestrador do MVP: uma sequência LINEAR de estágios, sem flags de versão.

    ler -> interpretar (LLM, com reparo) -> entender + verificar -> planejar -> compilar -> executar -> verificar -> apresentar -> registrar

Cada estágio devolve o próximo tipo ou um `Stop` (status + motivo), que encerra a pergunta dizendo por quê. Toda dependência externa entra
pelo construtor (portas): `LLMClient`, `SparqlSource`, `Lexicon`. Falha inesperada vira EXECUTION_ERROR genérico (falha FECHADA): nunca
resposta parcial, nunca detalhe interno ao usuário; o tipo da exceção fica na trilha.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from kgqa.contract import CONTRACT_VERSION, Diagnostic, Provenance, QueryResponse, Status
from pipeline.llm import LLMClient, LLMError
from pipeline.provenance import artifact_versions, llm_model_of, prov_turtle
from pipeline.textsafe import clean
from pipeline.validators import Finding

from ..domain import Executed, Stop
from ..execution import SparqlSource, execute
from ..knowledge import DomainCatalog, Lexicon
from ..planning import compile_query, plan, to_interp
from ..presentation import render, units_of
from ..understanding import Interpreter, read_question, understand
from ..verification import verify_post, verify_pre
from .settings import Settings

SYSTEM = "metqa-mvp"
UNSUPPORTED_CODES = {"UNKNOWN_PROPERTY", "UNKNOWN_ENTITY", "ENTITY_SPAN_MISMATCH", "UNIT_PROPERTY_MISMATCH", "UNKNOWN_DIMENSION",
                     "UNKNOWN_ATTRIBUTE"}


@dataclass
class Result:
    """Resposta (contrato 0.2.1) + trilha. Mesma forma do `PipelineResult` legado: avaliação e evolução leem os dois."""
    response: QueryResponse
    trace: list[dict[str, Any]] = field(default_factory=list)


def _feedback(findings: list[Finding]) -> str:
    return ("Sua resposta anterior foi recusada pelas regras:\n" + "\n".join(f"- [{f.diag.code}] {f.diag.message}" for f in findings)
            + "\nCorrija e responda de novo no mesmo formato.")


class MetQA:
    def __init__(self, catalog: DomainCatalog, lexicon: Lexicon, llm: LLMClient, source: SparqlSource, settings: Settings | None = None):
        self.catalog, self.lexicon, self.llm, self.source = catalog, lexicon, llm, source
        self.settings = settings or Settings()
        self.interpreter = Interpreter(llm, catalog)

    def ask(self, question: str, corrections: tuple[str, ...] = ()) -> Result:
        res = Result(QueryResponse(request_id=f"req-{uuid.uuid4().hex[:12]}", status=Status.EXECUTION_ERROR, question=question,
                                   provenance=Provenance(source_id=self.source.source_id)))
        t0, started = time.perf_counter(), datetime.now(timezone.utc)
        try:
            self._run(question, corrections, res, t0)
        except Exception as e:                                        # noqa: BLE001 — falha fechada
            res.trace.append({"event": "internal_error", "kind": type(e).__name__})
            self._end(res, Stop.of(Status.EXECUTION_ERROR, "INTERNAL_ERROR", "Erro interno; a pergunta não foi respondida.", "error"), t0)
        self._provenance(res, started)
        if self.settings.record_trajectories:
            from ..evolution import record
            record(self.settings.workspace, res)
        return res

    # ------------------------------------------------------------------------------------------------
    def _run(self, question: str, corrections: tuple[str, ...], res: Result, t0: float) -> None:
        trace = res.trace
        log = lambda event, **kw: trace.append({"t_ms": round((time.perf_counter() - t0) * 1000, 1), "event": event, **kw})
        q = clean(question, self.settings.max_question_chars + 1).strip()
        res.response.question = q
        if not q:
            return self._end(res, Stop.of(Status.REJECTED, "EMPTY_QUESTION", "Pergunta vazia.", "error"), t0)
        if len(question) > self.settings.max_question_chars:
            return self._end(res, Stop.of(Status.REJECTED, "QUESTION_TOO_LONG",
                                          f"Pergunta longa demais (limite {self.settings.max_question_chars} caracteres).", "error"), t0)

        # [1] leitura determinística; data relativa não tem como ser resolvida sem relógio: pede a data, sem gastar LLM
        reading = read_question(q, corrections)
        if reading.relative:
            return self._end(res, Stop.of(Status.NEEDS_CLARIFICATION, "RELATIVE_DATE",
                                          "A pergunta usa data relativa (hoje, ontem, semana passada…); informe a data exata (ex.: 03/03/2024)."), t0)
        hit = self.lexicon.lookup(" ".join([q, *corrections]))
        log("semantics", **hit.info)

        # [2]+[3] interpretação com uma rodada de reparo; conciliação e verificação-pré
        feedback, understood = "", None
        for attempt in range(self.settings.max_repairs + 1):
            try:
                prop = self.interpreter.propose(q, hit, feedback, tuple(corrections))
                log("llm", stage="interpret", finish=prop.finish, cost=prop.cost_usd)
            except LLMError as e:
                log("llm_error", stage="interpret", kind=e.kind, attempt=attempt)
                if e.kind == "invalid_output" and attempt < self.settings.max_repairs:
                    feedback = f"Sua resposta anterior era inválida ({e}). Responda só com o JSON pedido."
                    continue
                return self._end(res, Stop.of(Status.EXECUTION_ERROR, e.kind.upper(), str(e), "error"), t0)
            if prop.raw.get("record_kind") == "forecast":
                return self._end(res, Stop.of(Status.UNSUPPORTED, "NO_FORECASTS", "Esta fonte não tem previsões, só observações."), t0)
            understood = understand(q, prop.raw, reading, self.catalog)
            findings = list(understood.findings)
            if not findings and understood.stop is None:
                for _, cq in understood.parts:
                    pre, stop = verify_pre(cq, self.catalog)
                    findings += pre
                    if stop:
                        understood.stop = stop
                        break
            log("validate_interpretation", findings=[f.diag.code for f in findings],
                interpretation=_interp_dict(understood), stop=understood.stop.status.value if understood.stop else None)
            if understood.stop is not None:
                if understood.parts or understood.interpretations:
                    res.response.interpretation = understood.interpretations[0] if understood.interpretations else None
                return self._end(res, understood.stop, t0)
            if not findings:
                break
            if attempt == self.settings.max_repairs:
                codes = {f.diag.code for f in findings}
                status = Status.UNSUPPORTED if codes <= UNSUPPORTED_CODES else Status.REJECTED
                return self._end(res, Stop(status, [f.diag for f in findings]), t0)
            feedback = _feedback(findings)

        # [4] plano
        p = plan(understood.parts)
        if isinstance(p, Stop):
            return self._end(res, p, t0)
        res.response.interpretation = to_interp(p.parts[0].query)

        # [5]+[6] compilar e executar cada parte
        done: list[Executed] = []
        for part in p.parts:
            sparql = compile_query(part.query, self.catalog)
            log("compile_structured", sparql=sparql, part=part.label, intent=part.query.intent)
            if not sparql:
                return self._end(res, Stop.of(Status.UNSUPPORTED, "UNSUPPORTED_SHAPE",
                                              "Não sei montar com segurança a consulta para esta forma de pergunta."), t0)
            r = execute(part, sparql, self.catalog, self.source, timeout_s=self.settings.timeout_s, max_rows=self.settings.max_rows, log=log)
            if isinstance(r, Stop):
                res.response.sparql = sparql
                return self._end(res, r, t0)
            done.append(r)

        # [7]+[8] verificar e apresentar
        status, caveats = verify_post(done, self.catalog)
        resp = res.response
        resp.sparql = "\n# ---\n".join(e.sparql for e in done)
        resp.results = done[0].results if len(done) == 1 else {"parts": [{"label": e.part.label, "results": e.results} for e in done]}
        resp.truncated = any(e.truncated for e in done)
        resp.units = units_of(done[0].part.query, self.catalog)
        resp.answer_text = render(done, p.combine, self.catalog, caveats)
        sql = [e.engine_sql for e in done if e.engine_sql]
        if sql:
            resp.provenance.generated_sql, resp.provenance.engine = "\n-- ---\n".join(sql), "ontop-reformulate"
        resp.provenance.executed_sparql = resp.sparql
        self._end(res, Stop(status, []), t0)

    # ------------------------------------------------------------------------------------------------
    def _end(self, res: Result, stop: Stop, t0: float) -> None:
        resp = res.response
        resp.status, resp.diagnostics = stop.status, resp.diagnostics + stop.diagnostics
        if resp.answer_text is None and stop.status != Status.ANSWERED:
            resp.answer_text = "; ".join(d.message for d in stop.diagnostics) or None
        resp.timings_ms["total"] = round((time.perf_counter() - t0) * 1000, 1)
        res.trace.append({"event": "end", "status": stop.status.value, "prompts": SYSTEM, "semantic_layer": self.lexicon.version,
                          "ontology": self.catalog.index.fingerprint})

    def _provenance(self, res: Result, started: datetime) -> None:
        """Procedência (PROV-O, versões, SQL do motor). Registro apenas: uma falha aqui nunca derruba a resposta, mas é dita."""
        p = res.response.provenance
        try:
            p.versions = {k: v for k, v in {**artifact_versions(), "system": SYSTEM, "lexicon": self.lexicon.version,
                                             "ontology": self.catalog.index.fingerprint, "model": llm_model_of(self.llm),
                                             "contract": CONTRACT_VERSION}.items() if v is not None}
            p.prov_turtle = prov_turtle(res.response, started)
        except Exception as e:                                        # noqa: BLE001
            p.complete = False
            res.response.diagnostics.append(Diagnostic("PROVENANCE_INCOMPLETE", "info", f"Procedência incompleta ({type(e).__name__})."))


def _interp_dict(u) -> dict[str, Any] | None:
    i = u.interpretations[0] if u and u.interpretations else None
    if i is None:
        return None
    return {"properties": i.properties, "entities": i.entities, "aggregation": i.aggregation, "period": i.period, "filters": i.filters,
            "group_by": i.group_by, "count_of": i.count_of}
