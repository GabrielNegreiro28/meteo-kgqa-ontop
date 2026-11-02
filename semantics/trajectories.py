"""Trilha da pipeline -> trajetória do EvoOntology (documento da arquitetura, §7.3 "Use" e §13 "Sinais").

O ciclo de evolução precisa de insumo: o agente de evolução lê trajetórias, procura problemas recorrentes e propõe um Candidate. Até aqui a
pipeline escrevia uma trilha própria que ninguém lia. Este módulo a converte no formato do EvoOntology (task_id, question, semantic_calls,
native_tool_calls, final_answer, task_status, errors) e acrescenta `signals`, os sinais que o §13 lista: reparos, achados do verificador,
abstenções, esclarecimentos, caídas para a reserva, divergência entre a camada semântica e a interpretação, e as palavras da pergunta
que nenhum Termo cobriu (candidatas a sinônimo: é assim que "choveu" apareceria).

Só entra o que é observável (entradas e resultados de cada etapa). Nada de texto de raciocínio, de chave ou de prompt. A pergunta e o
SPARQL ficam em `<workspace>/trajectories/`, que não é versionado (`.gitignore`): a pergunta do usuário pode ser sensível.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from evoontology.trajectory.trajectory import TrajectoryStore, truncate_result

from metqa.domain.contract import Status

COMPLETED = {Status.ANSWERED, Status.NO_RESULTS, Status.UNSUPPORTED, Status.NEEDS_CLARIFICATION, Status.REJECTED}
ABSTENTIONS = {Status.UNSUPPORTED, Status.NEEDS_CLARIFICATION, Status.REJECTED}


def _call(tool: str, input_: dict[str, Any], result: Any) -> dict[str, Any]:
    return {"tool": tool, "input": input_, **truncate_result(result)}


def to_trajectory(result, *, task_id: str | None = None, split: str = "", ontology_version: str = "",
                  extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """`result` é um PipelineResult (response + trace). `extra` guarda o que só uma avaliação sabe (ex.: se o resultado conferiu)."""
    resp, trace = result.response, result.trace
    end = next((t for t in reversed(trace) if t["event"] == "end"), {})
    semantic_calls, native = [], []
    findings: list[str] = []
    llm_calls: Counter = Counter()
    sem_info: dict[str, Any] = {}
    agreement = None
    corrections = 0
    engine_status = None
    choices: list[str] = []
    crosscheck: dict[str, Any] = {}
    reread = None
    verified_by_user = False
    shapes: list[Any] = []

    for t in trace:
        ev = t["event"]
        if ev == "llm":
            llm_calls[t["stage"]] += 1
        elif ev == "semantics":
            sem_info = t
            semantic_calls.append({"tool": "resolve_semantics",
                                   "input": {"mentions": [r["phrase"] for r in t.get("resolved", [])] + [a["phrase"] for a in t.get("ambiguous", [])]},
                                   "result": {k: t.get(k) for k in ("layer", "resolved", "ambiguous", "unbound", "uncovered")}})
        elif ev == "semantics_check":
            agreement = t.get("agreement")
        elif ev == "validate_interpretation":
            findings += t["findings"]
            native.append(_call("interpret", {"question": resp.question}, {"interpretation": t.get("interpretation"), "findings": t["findings"]}))
        elif ev == "validate_query":
            findings += t["findings"]
            native.append(_call("validate_query", {"sparql": t.get("sparql")}, {"findings": t["findings"]}))
        elif ev == "compile_structured":
            shapes.append(t.get("shape"))
            native.append(_call("compile_structured", {}, {"sparql": t.get("sparql"), "shape": t.get("shape")}))
        elif ev == "crosscheck":                              # metqa: concordância entre as leituras e sinais de risco
            crosscheck = {"differ": t.get("differ", []), "strong": t.get("strong", []), "weak": t.get("weak", [])}
            agreement = not t.get("differ")
        elif ev == "reread_time":
            reread = t.get("same") if t.get("ok") else None
        elif ev == "exemplar_recorded":
            verified_by_user = bool(t.get("added")) or verified_by_user
        elif ev == "engine_check":
            findings += t.get("findings", [])
            engine_status = t.get("status")
            native.append(_call("engine_check", {}, {"status": t.get("status"), "findings": t.get("findings", [])}))
        elif ev == "compiled_fallback":
            findings += t["findings"]
            native.append(_call("compiled_fallback", {"sparql": t.get("sparql")}, {"findings": t["findings"]}))
        elif ev == "execute":
            native.append(_call("execute_sparql", {"sparql": resp.sparql}, {"ok": t.get("ok"), "kind": t.get("kind"), "status": resp.status.value,
                                                                           "rows": len((resp.results or {}).get("results", {}).get("bindings", []))}))
        elif ev == "check_answer":
            findings += t["findings"]
            native.append(_call("check_answer", {}, {"findings": t["findings"]}))
        elif ev == "dialogue":
            corrections += t.get("kind") == "correct"
            choices.append(t.get("kind"))
            native.append(_call("confirm_with_user", {"round": t.get("round")}, {"kind": t.get("kind")}))

    codes = [d.code for d in resp.diagnostics]
    signals = {
        "repairs": {stage: max(0, n - 1) for stage, n in llm_calls.items()},
        "verifier_findings": sorted(set(findings)),
        "abstention": ({"status": resp.status.value, "codes": codes} if resp.status in ABSTENTIONS else None),
        "clarification": resp.status == Status.NEEDS_CLARIFICATION,
        "fallbacks": {"compiled_query": "COMPILED_QUERY" in codes, "answer_fallback": "ANSWER_FALLBACK" in codes},
        "engine": engine_status,
        "semantics": {"agreement": agreement, "uncovered": sem_info.get("uncovered", []), "unbound": sem_info.get("unbound", [])},
        "user_corrections": corrections,
        "user_dialogue": choices,                             # confirm | choose | correct | cancel, em ordem
        "verified_by_user": verified_by_user,                 # a interpretação final virou exemplo verificado
        "crosscheck": crosscheck or None,
        "reread_time_same": reread,
        "result_shapes": shapes,
        "cost_usd": round(sum(t.get("cost", 0) or 0 for t in trace if t["event"] == "llm"), 5),
        "prompts": end.get("prompts"),
    }
    out = {
        "task_id": task_id or resp.request_id,
        "question": resp.question,
        "ontology_version": ontology_version or str(end.get("semantic_layer") or ""),
        "split": split,
        "semantic_calls": semantic_calls,
        "native_tool_calls": native,
        "final_answer": resp.answer_text or "",
        "task_status": "completed" if resp.status in COMPLETED else "failed",
        "errors": [{"code": d.code, "message": d.message[:200]} for d in resp.diagnostics if d.severity == "error"],
        "pipeline_status": resp.status.value,
        "signals": signals,
    }
    if extra:
        out["evaluation"] = extra
    return out


def record_trajectory(workspace, result, **kw) -> str:
    """Grava a trajetória em `<workspace>/trajectories/<task_id>.json`. Devolve o task_id."""
    return TrajectoryStore(workspace).append(to_trajectory(result, **kw))


def pending(workspace) -> int:
    """Quantas trajetórias já se acumularam (o gatilho de evolução do EvoOntology conta a partir do último checkpoint)."""
    return TrajectoryStore(workspace).count_since(None)
