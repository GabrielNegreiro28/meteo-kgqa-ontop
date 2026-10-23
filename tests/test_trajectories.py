"""Trilha da pipeline -> trajetória do EvoOntology, com os sinais do §13 (insumo do ciclo de evolução).

Sem LLM. Os sinais são o que o agente de evolução leria para decidir o que melhorar: reparos, achados do verificador, abstenções,
esclarecimentos, caídas para a reserva, divergência da camada semântica e palavras que nenhum Termo cobriu.
"""
import json

import pytest
from evoontology.trigger.trigger import EvolutionTrigger

from kgqa.contract import Status
from pipeline.llm import ScriptedLLM
from pipeline.orchestrator import run_pipeline
from semantics.build import build_v0
from semantics.facade import GroundedLayer
from semantics.ground import SemanticGrounder
from semantics.trajectories import pending, record_trajectory, to_trajectory
from tests.test_pipeline import BACKEND, D04_INTERP, D04_Q, INDEX, QS, J, good_answer_d04


@pytest.fixture(scope="module")
def ws(tmp_path_factory):
    path = tmp_path_factory.mktemp("evo")
    build_v0(path)
    return path


def script(interp=D04_INTERP, sparqls=None):
    return {"interpret": [json.dumps(interp)], "generate": [J(sparql=q) for q in (sparqls or [QS["D04"]["sparql"]])],
            "answer": [J(answer=good_answer_d04())]}


def test_a_normal_run_becomes_a_trajectory_in_the_evoontology_schema():
    res = run_pipeline(D04_Q, ScriptedLLM(script()), BACKEND, INDEX, timeout_s=20)
    t = to_trajectory(res, split="dev")
    assert {"task_id", "question", "ontology_version", "split", "semantic_calls", "native_tool_calls", "final_answer", "task_status", "errors"} <= set(t)
    assert t["task_status"] == "completed" and t["pipeline_status"] == "answered" and t["question"] == D04_Q
    tools = [c["tool"] for c in t["native_tool_calls"]]
    assert tools[0] == "interpret" and "validate_query" in tools and tools.index("validate_query") < tools.index("execute_sparql")
    json.dumps(t)                                                                       # serializável como está


def test_signals_count_repairs_and_collect_the_verifier_findings():
    bad = QS["D04"]["sparql"].replace("met:AirTemperature", "met:Temperature")
    res = run_pipeline(D04_Q, ScriptedLLM(script(sparqls=[bad, QS["D04"]["sparql"]])), BACKEND, INDEX, timeout_s=20)
    s = to_trajectory(res)["signals"]
    assert s["repairs"]["generate"] == 1 and "UNKNOWN_IRI" in s["verifier_findings"]
    assert s["abstention"] is None and s["fallbacks"] == {"compiled_query": False, "answer_fallback": False} and s["cost_usd"] == 0


def test_an_abstention_is_a_signal_with_its_reason():
    unsupported = {"status": "unsupported", "reason": "fora da ontologia"}
    res = run_pipeline(D04_Q, ScriptedLLM({"interpret": [json.dumps(unsupported)]}), BACKEND, INDEX, timeout_s=20)
    t = to_trajectory(res)
    assert t["signals"]["abstention"]["status"] == "unsupported" and t["task_status"] == "completed"


def test_a_clarification_is_flagged():
    ask = {"status": "needs_clarification", "reason": "ambíguo", "alternatives": ["a", "b"]}
    res = run_pipeline(D04_Q, ScriptedLLM({"interpret": [json.dumps(ask)]}), BACKEND, INDEX, timeout_s=20)
    assert to_trajectory(res)["signals"]["clarification"] is True


def test_an_infrastructure_failure_is_a_failed_task_not_a_wrong_answer():
    res = run_pipeline(D04_Q, ScriptedLLM({}), BACKEND, INDEX, timeout_s=20)             # roteiro vazio: o LLM falha
    t = to_trajectory(res)
    assert res.response.status == Status.EXECUTION_ERROR and t["task_status"] == "failed" and t["errors"]


def test_nothing_secret_or_free_text_reasoning_is_persisted():
    res = run_pipeline(D04_Q, ScriptedLLM(script()), BACKEND, INDEX, timeout_s=20)
    blob = json.dumps(to_trajectory(res)).lower()
    assert "api_key" not in blob and "bearer" not in blob and "sk-" not in blob and "reasoning" not in blob


def test_the_layer_words_nobody_covered_become_a_signal_for_the_evolution(ws):
    """É assim que 'choveu' (7 perguntas medidas) chegaria ao agente de evolução como candidato a sinônimo de precipitação."""
    grounder = SemanticGrounder(GroundedLayer.open(ws))
    block, info = grounder.block("Quanto choveu em SBGR em 2019?")
    assert block == "" and info["uncovered"] == ["choveu"]                              # código de estação, 'quanto' e o ano não entram
    block, info = grounder.block("Qual foi a temperatura média de SBGR em 2019?")
    assert info["uncovered"] == [] and info["resolved"]


def test_the_semantic_agreement_and_uncovered_words_reach_the_trajectory(ws):
    grounder = SemanticGrounder(GroundedLayer.open(ws))
    res = run_pipeline(D04_Q, ScriptedLLM(script()), BACKEND, INDEX, timeout_s=20, prompts_version="v5", semantics=grounder)
    t = to_trajectory(res)
    assert t["ontology_version"] == "ontology_v0" and t["semantic_calls"][0]["tool"] == "resolve_semantics"
    assert t["signals"]["semantics"]["agreement"] == "agree"


def test_recording_feeds_the_evolution_trigger(ws, tmp_path):
    res = run_pipeline(D04_Q, ScriptedLLM(script()), BACKEND, INDEX, timeout_s=20)
    assert pending(tmp_path) == 0
    task = record_trajectory(tmp_path, res, split="dev", extra={"result_match": True})
    assert pending(tmp_path) == 1 and task == res.response.request_id
    saved = json.loads((tmp_path / "trajectories" / f"{task}.json").read_text(encoding="utf-8"))
    assert saved["evaluation"] == {"result_match": True} and saved["recorded_at"]
    assert EvolutionTrigger(tmp_path).trajectories.count_since(None) == 1
