"""Orquestrador do MVP: entendimento verificado por concordância e pelo usuário, depois uma sequência LINEAR de estágios determinísticos.

    memória -> duas leituras do LLM (com reparo) -> validação no mundo fechado -> concordância -> política de risco -> [usuário]
            -> planejar -> compilar -> executar -> verificar -> apresentar -> registrar (trilha + exemplo verificado)

Não há gramática de regex no caminho: a linguagem é do LLM; a dúvida é detectada por mecanismos genéricos (as leituras divergem, evidência
fora da pergunta, número ignorado) e resolvida pelo usuário — ou, sem usuário, devolvida como pedido de esclarecimento, nunca adivinhada.
Toda dependência externa entra pelo construtor (portas): LLM, fonte SPARQL, léxico, memória, canal do usuário.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
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
from ..understanding.evidence import needs_reread, time_key
from ..verification import verify_post, verify_pre
from .settings import Settings

SYSTEM = "metqa-mvp"
UNSUPPORTED_CODES = {"UNKNOWN_PROPERTY", "UNKNOWN_ENTITY", "UNKNOWN_DIMENSION", "UNKNOWN_ATTRIBUTE", "UNIT_DIMENSION_MISMATCH"}
User = Callable[[str], str]


@dataclass
class Result:
    """Resposta (contrato 0.3.0) + trilha. Mesma forma do `PipelineResult` legado: avaliação e evolução leem os dois."""
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

    def capabilities(self) -> dict[str, Any]:
        """O que este módulo responde, para o roteador do sistema decidir se manda a pergunta para cá (plano, D10). Sem LLM e sem consulta."""
        from ..planning.planner import MAX_PARTS
        cov = self.catalog.coverage
        return {
            "module": SYSTEM, "contract": CONTRACT_VERSION, "language": "pt-BR", "source": self.source.source_id,
            "ontology": self.catalog.index.fingerprint, "lexicon": self.lexicon.version,
            "coverage": {"start": cov[0].isoformat(), "end": cov[1].isoformat()} if cov else None,
            "timezone": "UTC-03:00 (horário de Brasília, fixo)",
            "stations": len(self.catalog.index.entities),
            "measures": [{"iri": m.iri, "label": m.label, "unit": m.unit, "symbol": m.symbol, "aggregations": sorted(m.aggregations),
                          "attributes": list(m.attributes), "accumulated": m.accumulated}
                         for m in self.catalog.measures.values() if m.has_data],
            "question_forms": ["value", "count", "series", "ranking", "extreme_with_attribute", "instant", "comparison"],
            "time_filters": ["date_ranges", "local_hours", "weekdays", "instant"],
            "limits": {"comparison_parts": MAX_PARTS, "max_rows": self.settings.max_rows, "timeout_s": self.settings.timeout_s,
                       "question_chars": self.settings.max_question_chars},
            "not_supported": ["previsões", "dados fora da cobertura", "cidade, estado ou coordenadas", "grandezas fora do catálogo"],
        }

    def confirmation_token(self, question: str, interpretation: dict) -> str:
        """Assina uma opção devolvida ao cliente (pergunta + interpretação + versão do catálogo): só ela pode voltar como `confirmed`."""
        body = json.dumps({"q": question.strip(), "ir": interpretation, "catalog": self.catalog.index.fingerprint}, sort_keys=True,
                          ensure_ascii=False)
        return hmac.new(self.settings.secret, body.encode(), hashlib.sha256).hexdigest()

    def ask(self, question: str, user: User | None = None, confirmed: dict | None = None, confirmation: str | None = None) -> Result:
        """`user`: canal com o usuário (prompt -> resposta); None = sem usuário (API, lote).
        `confirmed` + `confirmation`: a interpretação que o usuário escolheu entre as opções de um CONFIRMATION_REQUIRED, com o token
        assinado que veio junto dela; executa sem chamar o LLM. Sem o token certo é recusada (senão qualquer cliente gravaria qualquer
        interpretação como verificada)."""
        res = Result(QueryResponse(request_id=f"req-{uuid.uuid4().hex[:12]}", status=Status.EXECUTION_ERROR, question=question,
                                   provenance=Provenance(source_id=self.source.source_id)))
        t0, started = time.perf_counter(), datetime.now(timezone.utc)
        try:
            self._run(question, user, confirmed, confirmation, res, t0)
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
            framings = ("A", "B")[:max(1, self.settings.readings)]
            with ThreadPoolExecutor(len(framings)) as pool:                 # leituras independentes, em paralelo
                readings = list(pool.map(lambda f: self._reading(q, hit, f, exemplars, corrections, previous, log), framings))
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
            elif b is not None and len(ok) == 1 and all(r.parsed is not None for r in readings):
                differ = ["status"]                                       # uma leitura respondeu, a outra disse que não dá: divergem
            options = ok if differ else ok[:1]
            base = options[0].parsed if options else a.parsed
            risk = assess(q if not corrections else " ".join([q, *corrections]), base, b.parsed if b else None, differ, bool(exemplars),
                          frozenset(hit.measures), conservation=self.settings.conservation)
            if b is not None and len(ok) == 1 and not differ:
                risk.weak.append("só uma das duas leituras foi válida (a outra falhou no LLM)")
            if options and not differ and self.settings.reread and self.settings.conservation and needs_reread(base.evidence, [x for _, x in base.parts]):
                risk.strong += self._reread(base, log)
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
                details = {"options": [{"paraphrase": p, "interpretation": o.parsed.raw,
                                        "confirmation_token": self.confirmation_token(q, o.parsed.raw)} for p, o in zip(paras, options)],
                           "reasons": risk.strong, "alternatives": a.parsed.alternatives}
                res.response.answer_text = msg
                self._end(res, Stop(Status.NEEDS_CLARIFICATION, [Diagnostic("CONFIRMATION_REQUIRED", "info", msg, details)]), t0)
                return None, False
            kind, value = self._reply(user, msg, len(paras), corrections)
            log("dialogue", round=rnd, kind=kind, reply=str(value)[:200])
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
    def _reply(user: User, msg: str, n_options: int, corrections: list[str]) -> tuple[str, str]:
        """A resposta do usuário já classificada. Repergunta SEM chamar o LLM quando ela não decide nada: "sim" diante de opções,
        "não" sem dizer o quê, ou a mesma correção já aplicada."""
        reply = user(msg)
        for _ in range(3):
            kind, value = classify(reply, n_options)
            if kind == "confirm" and n_options > 1:
                reply = user(f"Qual delas? Responda com o número (1 a {n_options}), \"cancelar\", ou diga o que você quer.")
            elif kind == "deny":
                reply = user("O que devo corrigir? (ex.: o período, a estação, a grandeza ou o cálculo)")
            elif kind == "correct" and value in corrections:
                reply = user("Essa correção já foi aplicada. Diga o que ainda está diferente do que você quer, \"sim\" ou \"cancelar\".")
            else:
                return kind, value
        return "cancel", ""

    def _reread(self, p: Parsed, log) -> list[str]:
        """Releitura ISOLADA do trecho de tempo (sem a pergunta, sem exemplos): contexto diferente, erro menos correlacionado (plano, D1b)."""
        span = " ".join(x for x in (p.evidence.get("time"), p.evidence.get("period")) if x)
        try:
            raw = self.interpreter.reread_time(span)
        except LLMError as e:
            log("reread_time", ok=False, kind=e.kind)
            return []
        other = parse({**p.raw, "status": "ok", "time": raw})
        same = not other.errors and time_key([x for _, x in other.parts]) == time_key([x for _, x in p.parts])
        log("reread_time", ok=True, span=span, same=same, time=raw)
        return [] if same else [f"o trecho de tempo ('{span}'), relido sozinho, dá outro período"]

    @staticmethod
    def _weak_notes(p: Parsed, risk) -> None:
        notes = [w for w in risk.weak if not w.startswith("nenhuma pergunta parecida")]
        for _, cq in p.parts:
            cq.assumptions += [n for n in notes if n not in cq.assumptions]

    # ------------------------------------------------------------------------------------------------
    def _run(self, question: str, user: User | None, confirmed: dict | None, confirmation: str | None, res: Result, t0: float) -> None:
        log = self._log(res, t0)
        q = clean(question, self.settings.max_question_chars + 1).strip()
        res.response.question = q
        if not q:
            return self._end(res, Stop.of(Status.REJECTED, "EMPTY_QUESTION", "Pergunta vazia.", "error"), t0)
        if len(question) > self.settings.max_question_chars:
            return self._end(res, Stop.of(Status.REJECTED, "QUESTION_TOO_LONG",
                                          f"Pergunta longa demais (limite {self.settings.max_question_chars} caracteres).", "error"), t0)
        if confirmed is not None:                                    # o usuário escolheu entre as opções devolvidas antes: sem LLM
            if not confirmation or not hmac.compare_digest(confirmation, self.confirmation_token(q, confirmed)):
                return self._end(res, Stop.of(Status.REJECTED, "CONFIRMATION_TOKEN_INVALID",
                                              "A interpretação confirmada não veio com o token da opção devolvida para esta pergunta.", "error"), t0)
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
            compiled = compile_query(part.query, self.catalog)
            log("compile_structured", sparql=compiled.sparql if compiled else None, part=part.label, intent=part.query.intent,
                shape=compiled.shape.__dict__ if compiled else None)
            if not compiled:
                return self._end(res, Stop.of(Status.UNSUPPORTED, "UNSUPPORTED_SHAPE",
                                              "Não sei montar com segurança a consulta para esta forma de pergunta."), t0)
            r = execute(part, compiled, self.catalog, self.source, timeout_s=self.settings.timeout_s, max_rows=self.settings.max_rows, log=log)
            if isinstance(r, Stop):
                res.response.sparql = compiled.sparql
                return self._end(res, r, t0)
            done.append(r)

        status, caveats = verify_post(done, self.catalog)
        resp = res.response
        resp.sparql = "\n# ---\n".join(e.sparql for e in done)
        resp.results = done[0].results if len(done) == 1 else {"parts": [{"label": e.part.label, "results": e.results} for e in done]}
        resp.truncated = any(e.truncated for e in done)
        resp.units = units_of(done[0], self.catalog)
        resp.result_shape = [{**e.shape.__dict__, "keys": list(e.shape.keys), "attributes": [list(a) for a in e.shape.attributes],
                              "label": e.part.label} for e in done]
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
