"""Orquestrador do MVP: entendimento verificado por concordância e pelo usuário, depois uma sequência LINEAR de estágios determinísticos.

    memória -> duas leituras do LLM (com reparo) -> validação no mundo fechado -> concordância -> política de risco -> [usuário]
            -> planejar -> compilar -> executar -> verificar -> apresentar -> registrar (trilha + exemplo verificado)

Não há gramática de regex no caminho: a linguagem é do LLM; a dúvida é detectada por mecanismos genéricos (as leituras divergem, evidência
fora da pergunta, número ignorado) e resolvida pelo usuário — ou, sem usuário, devolvida como pedido de esclarecimento, nunca adivinhada.
Toda dependência externa entra pelo construtor (portas): LLM, fonte SPARQL, léxico, memória, canal do usuário.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from kgqa.contract import CONTRACT_VERSION, Diagnostic, Provenance, QueryResponse, Status
from pipeline.llm import LLMClient, LLMError
from pipeline.provenance import artifact_versions, llm_model_of, prov_turtle
from pipeline.textsafe import clean
from pipeline.validators import Finding

from ..dialogue import assess, choice_message, classify, confirm_message, paraphrase_parts
from ..domain import Executed, Stop
from ..execution import SparqlSource, execute
from ..knowledge import DomainCatalog, ExemplarStore, Lexicon
from ..planning import compile_query, plan, to_interp
from ..presentation import render, units_of
from ..understanding import Interpreter, Parsed, canonical_form, describe_diff, diff, parse
from ..verification import verify_post, verify_pre
from .settings import Settings

SYSTEM = "metqa-mvp"
UNSUPPORTED_CODES = {"UNKNOWN_PROPERTY", "UNKNOWN_ENTITY", "UNKNOWN_DIMENSION", "UNKNOWN_ATTRIBUTE", "UNIT_DIMENSION_MISMATCH"}
User = Callable[[str], str]


@dataclass
class Result:
    """Resposta (contrato 0.2.1) + trilha. Mesma forma do `PipelineResult` legado: avaliação e evolução leem os dois."""
    response: QueryResponse
    trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Reading:
    parsed: Parsed | None = None
    stop: Stop | None = None                      # capacidade (sem dados, fora da cobertura) ou falha do LLM


def _feedback(problems: list[str]) -> str:
    return ("Sua resposta anterior foi recusada pelas regras:\n" + "\n".join(f"- {p}" for p in problems)
            + "\nCorrija e responda de novo no mesmo formato.")


class MetQA:
    def __init__(self, catalog: DomainCatalog, lexicon: Lexicon, llm: LLMClient, source: SparqlSource, settings: Settings | None = None,
                 exemplars: ExemplarStore | None = None):
        self.catalog, self.lexicon, self.llm, self.source = catalog, lexicon, llm, source
        self.settings = settings or Settings()
        self.interpreter = Interpreter(llm, catalog)
        self.exemplars = exemplars if exemplars is not None else ExemplarStore(None)

    def ask(self, question: str, user: User | None = None, confirmed: dict | None = None) -> Result:
        """`user`: canal com o usuário (prompt -> resposta); None = sem usuário (API, lote).
        `confirmed`: interpretação que o usuário já escolheu (devolvida antes num CONFIRMATION_REQUIRED): executa sem chamar o LLM."""
        res = Result(QueryResponse(request_id=f"req-{uuid.uuid4().hex[:12]}", status=Status.EXECUTION_ERROR, question=question,
                                   provenance=Provenance(source_id=self.source.source_id)))
        t0, started = time.perf_counter(), datetime.now(timezone.utc)
        try:
            self._run(question, user, confirmed, res, t0)
        except Exception as e:                                        # noqa: BLE001 — falha fechada
            res.trace.append({"event": "internal_error", "kind": type(e).__name__})
            self._end(res, Stop.of(Status.EXECUTION_ERROR, "INTERNAL_ERROR", "Erro interno; a pergunta não foi respondida.", "error"), t0)
        self._provenance(res, started)
        if self.settings.record_trajectories:
            from ..evolution import record
            record(self.settings.workspace, res)
        return res

    # ------------------------------------------------------------------------------------------------
    def _log(self, res: Result, t0: float):
        return lambda event, **kw: res.trace.append({"t_ms": round((time.perf_counter() - t0) * 1000, 1), "event": event, **kw})

    def _reading(self, q: str, hit, framing: str, exemplars, corrections, previous, log) -> Reading:
        """Uma leitura do LLM, validada no mundo fechado (esquema + catálogo), com uma rodada de reparo."""
        feedback = ""
        for attempt in range(self.settings.max_repairs + 1):
            try:
                prop = self.interpreter.read(q, hit, framing, exemplars=exemplars, feedback=feedback, corrections=tuple(corrections),
                                             previous=previous)
                log("llm", stage=f"interpret_{framing}", finish=prop.finish, cost=prop.cost_usd)
            except LLMError as e:
                log("llm_error", stage=f"interpret_{framing}", kind=e.kind, attempt=attempt)
                if e.kind == "invalid_output" and attempt < self.settings.max_repairs:
                    feedback = f"Sua resposta anterior era inválida ({e}). Responda só com o JSON pedido."
                    continue
                return Reading(stop=Stop.of(Status.EXECUTION_ERROR, e.kind.upper(), str(e), "error"))
            p = parse(prop.raw)
            problems, findings, stop = list(p.errors), [], None
            if p.status == "ok" and not problems:
                for _, cq in p.parts:
                    f, stop = verify_pre(cq, self.catalog)
                    findings += f
                    if stop:
                        break
                problems += [f"[{x.diag.code}] {x.diag.message}" for x in findings]
            log("validate_interpretation", framing=framing, status=p.status, findings=[x.diag.code for x in findings] + p.errors[:3],
                interpretation={"properties": [p.parts[0][1].measure] if p.parts else [], "raw": p.raw})
            if not problems:
                return Reading(p, stop)
            if attempt == self.settings.max_repairs:
                codes = {x.diag.code for x in findings}
                status = Status.UNSUPPORTED if codes and codes <= UNSUPPORTED_CODES else Status.REJECTED
                return Reading(p, Stop(status, [x.diag for x in findings] or [Diagnostic("BAD_INTERPRETATION", "error", "; ".join(problems))]))
            feedback = _feedback(problems)
        return Reading(stop=Stop.of(Status.EXECUTION_ERROR, "NO_INTERPRETATION", "sem interpretação", "error"))

    def _understand(self, q: str, user: User | None, res: Result, t0: float) -> tuple[Parsed | None, bool]:
        """(interpretação escolhida, verificada pelo usuário?) ou (None, _) se a pergunta já foi encerrada."""
        log = self._log(res, t0)
        hit = self.lexicon.lookup(q)
        log("semantics", **hit.info)
        corrections: list[str] = []
        previous = None
        for rnd in range(self.settings.max_rounds + 1):
            exemplars = self.exemplars.search(" ".join([q, *corrections])) if self.settings.exemplars else []
            log("exemplars", found=[e["question"] for e in exemplars])
            readings = [self._reading(q, hit, f, exemplars, corrections, previous, log) for f in ("A", "B")[:max(1, self.settings.readings)]]
            a = readings[0]
            if a.parsed is None:
                self._end(res, a.stop, t0)
                return None, False
            b = readings[1] if len(readings) > 1 else None
            ok = [r for r in readings if r.parsed and r.parsed.status == "ok" and r.stop is None]
            statuses = {r.parsed.status for r in readings if r.parsed}

            # o próprio LLM diz que não dá (todas as leituras): encerra dizendo por quê
            if statuses == {"unsupported"}:
                self._end(res, Stop.of(Status.UNSUPPORTED, "UNSUPPORTED_BY_MODEL", a.parsed.reason or "Fora do que os dados cobrem."), t0)
                return None, False
            if not ok and a.stop is not None:                         # capacidade (sem dados, fora da cobertura) ou erro estrutural
                if b is None or (b.parsed and b.stop is not None and b.stop.status == a.stop.status):
                    self._end(res, a.stop, t0)
                    return None, False

            # concordância e risco
            differ: list[str] = []
            if b is not None and len(ok) == 2:
                differ = diff(canonical_form(a.parsed.parts, self.catalog.to_canonical),
                              canonical_form(b.parsed.parts, self.catalog.to_canonical))
            elif b is not None and len(ok) == 1:
                differ = ["status"]
            options = ok if differ else ok[:1]
            base = options[0].parsed if options else a.parsed
            risk = assess(q if not corrections else " ".join([q, *corrections]), base, b.parsed if b else None, differ, bool(exemplars))
            if "needs_clarification" in statuses and not ok:
                risk.strong.append(a.parsed.reason or "a pergunta admite mais de uma leitura")
            log("crosscheck", differ=differ, strong=risk.strong, weak=risk.weak)
            if options and not risk.must_ask(self.settings.confirm):
                self._weak_notes(base, risk)
                return base, False

            # perguntar ao usuário (ou, sem usuário, devolver as opções)
            paras = [paraphrase_parts(o.parsed.parts, self.catalog) for o in options]
            if len(paras) > 1:
                msg = choice_message(paras, describe_diff(differ))
            elif paras:
                msg = confirm_message(paras[0], risk.strong + (risk.weak if self.settings.confirm == "always" else []))
            else:
                alts = [str(x) for x in a.parsed.alternatives][:5]
                msg = "Preciso de um esclarecimento: " + (a.parsed.reason or "a pergunta admite mais de uma leitura") + \
                      ("\n" + "\n".join(f"  {i}. {x}" for i, x in enumerate(alts, 1)) if alts else "") + "\nDiga o que você quer."
            if user is None:
                details = {"options": [{"paraphrase": p, "interpretation": o.parsed.raw} for p, o in zip(paras, options)],
                           "reasons": risk.strong, "alternatives": a.parsed.alternatives}
                res.response.answer_text = msg
                self._end(res, Stop(Status.NEEDS_CLARIFICATION, [Diagnostic("CONFIRMATION_REQUIRED", "info", msg, details)]), t0)
                return None, False
            reply = user(msg)
            kind, value = classify(reply, len(paras))
            if kind == "deny":
                reply = user("O que devo corrigir? (ex.: o período, a estação, a grandeza ou o cálculo)")
                kind, value = classify(reply, len(paras))
                kind = "cancel" if kind == "deny" else kind
            log("dialogue", round=rnd, kind=kind, reply=str(reply)[:200])
            if kind == "cancel":
                self._end(res, Stop.of(Status.NEEDS_CLARIFICATION, "USER_CANCELLED", "Pergunta cancelada pelo usuário."), t0)
                return None, False
            if kind == "choose":
                return options[int(value) - 1].parsed, True
            if kind == "confirm" and len(options) == 1:
                return base, True
            if kind == "correct" and value:
                corrections.append(value)
                previous = base.raw
                continue
        self._end(res, Stop.of(Status.NEEDS_CLARIFICATION, "CONFIRMATION_LIMIT", "Não convergimos na interpretação; reformule a pergunta."), t0)
        return None, False

    @staticmethod
    def _weak_notes(p: Parsed, risk) -> None:
        notes = [w for w in risk.weak if not w.startswith("nenhuma pergunta parecida")]
        for _, cq in p.parts:
            cq.assumptions += [n for n in notes if n not in cq.assumptions]

    # ------------------------------------------------------------------------------------------------
    def _run(self, question: str, user: User | None, confirmed: dict | None, res: Result, t0: float) -> None:
        log = self._log(res, t0)
        q = clean(question, self.settings.max_question_chars + 1).strip()
        res.response.question = q
        if not q:
            return self._end(res, Stop.of(Status.REJECTED, "EMPTY_QUESTION", "Pergunta vazia.", "error"), t0)
        if len(question) > self.settings.max_question_chars:
            return self._end(res, Stop.of(Status.REJECTED, "QUESTION_TOO_LONG",
                                          f"Pergunta longa demais (limite {self.settings.max_question_chars} caracteres).", "error"), t0)
        if confirmed is not None:                                    # o usuário escolheu entre as opções devolvidas antes: sem LLM
            chosen, by_user = parse(confirmed), True
            problems = list(chosen.errors)
            for _, cq in chosen.parts:
                f, stop = verify_pre(cq, self.catalog)
                if stop:
                    return self._end(res, stop, t0)
                problems += [x.diag.message for x in f]
            if problems or chosen.status != "ok":
                return self._end(res, Stop.of(Status.REJECTED, "BAD_CONFIRMED_INTERPRETATION", "; ".join(problems) or chosen.reason, "error"), t0)
            log("dialogue", round=0, kind="confirmed_by_client")
        else:
            chosen, by_user = self._understand(q, user, res, t0)
            if chosen is None:
                return

        p = plan(chosen.parts)
        if isinstance(p, Stop):
            return self._end(res, p, t0)
        res.response.interpretation = to_interp(p.parts[0].query)
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

        status, caveats = verify_post(done, self.catalog)
        resp = res.response
        resp.sparql = "\n# ---\n".join(e.sparql for e in done)
        resp.results = done[0].results if len(done) == 1 else {"parts": [{"label": e.part.label, "results": e.results} for e in done]}
        resp.truncated = any(e.truncated for e in done)
        resp.units = units_of(done[0].part.query, self.catalog)
        resp.answer_text = (render(done, p.combine, self.catalog, caveats) + "\nEntendi assim: " + paraphrase_parts(chosen.parts, self.catalog)
                            + (". Se não for isso, diga o que corrigir." if not by_user else " (confirmado por você)."))
        sql = [e.engine_sql for e in done if e.engine_sql]
        if sql:
            resp.provenance.generated_sql, resp.provenance.engine = "\n-- ---\n".join(sql), "ontop-reformulate"
        resp.provenance.executed_sparql = resp.sparql
        if by_user and self.settings.exemplars and status == Status.ANSWERED:
            added = self.exemplars.add(q, chosen.raw, "user")
            log("exemplar_recorded", added=added)
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
                                             "contract": CONTRACT_VERSION, "readings": self.settings.readings,
                                             "confirm": self.settings.confirm}.items() if v is not None}
            p.prov_turtle = prov_turtle(res.response, started)
        except Exception as e:                                        # noqa: BLE001
            p.complete = False
            res.response.diagnostics.append(Diagnostic("PROVENANCE_INCOMPLETE", "info", f"Procedência incompleta ({type(e).__name__})."))
