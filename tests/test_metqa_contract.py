"""Contrato 0.3.0, capacidades para o roteador e trilha que a evolução lê (plano, Fase 6). Sem LLM real e sem Ontop."""
import json

from kgqa.contract import CONTRACT_VERSION, Status
from pipeline.dialogue import ScriptedUser
from semantics.trajectories import to_trajectory
from tests.test_metqa_shapes import CAT, Rows, XD, lit, table
from tests.test_metqa import nir
from tests.test_metqa_understanding import MAX, MEAN, Q_AMB, run
from metqa.app import MetQA, Settings
from metqa.knowledge import ExemplarStore, OntologyLexicon
from pipeline.llm import ScriptedLLM

ROW = table({"value": lit(39, XD), "n": lit(8000)})


def test_capacidades_dizem_o_que_o_modulo_responde_sem_llm_nem_consulta():
    llm, src = ScriptedLLM({}), Rows()
    cap = MetQA(CAT, OntologyLexicon(CAT), llm, src, Settings(), ExemplarStore(None)).capabilities()
    assert cap["contract"] == CONTRACT_VERSION == "0.3.0" and cap["coverage"] == {"start": "2016-01-01", "end": "2025-12-31"}
    iris = {m["iri"].rsplit("#", 1)[-1] for m in cap["measures"]}
    assert {"AirTemperature", "Precipitation", "WindSpeed"} <= iris and cap["limits"]["comparison_parts"] == 4
    assert "weekdays" in cap["time_filters"] and llm.calls == [] and src.queries == []
    json.dumps(cap)                                                               # serializável para o roteador


def test_resposta_traz_o_papel_das_colunas():
    ir = nir("met:AirTemperature", ["st:SBGL"], "avg", "2020-01-01", "2020-12-31", evidence={"measure": "temperatura", "time": "em 2020"})
    r, _ = run({"interpret_A": [ir], "interpret_B": [ir]}, "Qual a temperatura média de SBGL em 2020?", ROW, reread=False)
    assert r.result_shape == [{"value": "value", "n": "n", "n_of": "readings", "is_count": False, "keys": [], "attributes": [], "time": None,
                               "label": ""}]
    assert r.to_dict()["contract_version"] == "0.3.0"


def test_trilha_do_metqa_vira_trajetoria_com_os_sinais_novos():
    user = ScriptedUser(["2"])
    llm = ScriptedLLM({"interpret_A": [json.dumps(MEAN)], "interpret_B": [json.dumps(MAX)]})
    store = ExemplarStore(None)
    res = MetQA(CAT, OntologyLexicon(CAT), llm, Rows(ROW), Settings(reread=False), store).ask(Q_AMB, user=user)
    t = to_trajectory(res, split="eval")
    sig = t["signals"]
    assert t["pipeline_status"] == "answered" and t["split"] == "eval"
    assert sig["crosscheck"]["differ"] == ["aggregation"] and sig["user_dialogue"] == ["choose"] and sig["verified_by_user"]
    assert sig["result_shapes"][0]["value"] == "value"
    props = next(c for c in t["native_tool_calls"] if c["tool"] == "interpret")["result"]["interpretation"]["properties"]
    assert props == ["https://example.org/kgqa-met/ontology#AirTemperature"]       # IRI completo: a evolução atribui a palavra à grandeza


def test_medicao_nunca_e_minerada_e_esclarecimento_vira_proposta(tmp_path):
    from semantics.evolve import HELD_OUT, mine, trusted
    assert "eval" in HELD_OUT
    assert trusted({"pipeline_status": "answered", "signals": {"user_corrections": 1, "verified_by_user": True}})
    assert not trusted({"pipeline_status": "answered", "signals": {"user_corrections": 1}})
    import shutil
    from pathlib import Path
    ws = tmp_path / "ws"
    shutil.copytree(Path(__file__).resolve().parent.parent / ".evoontology", ws, ignore=shutil.ignore_patterns("trajectories", "evolution"))
    from evoontology.trajectory.trajectory import TrajectoryStore
    store = TrajectoryStore(ws)
    for i in range(2):
        store.append({"task_id": f"c{i}", "question": "a garoa estava forte?", "split": "", "native_tool_calls": [], "pipeline_status":
                      "needs_clarification", "signals": {"clarification": True, "semantics": {"uncovered": ["garoa"]}, "verifier_findings": []}})
    store.append({"task_id": "e0", "question": "garoa", "split": "eval", "native_tool_calls": [], "pipeline_status": "needs_clarification",
                  "signals": {"clarification": True, "semantics": {"uncovered": ["neblina"]}, "verifier_findings": []}})
    active = json.loads((ws / "active.json").read_text(encoding="utf-8"))["active_version"]
    _, proposals = mine(ws, active)
    found = {p.finding: p for p in proposals}
    assert found["UNCOVERED_IN_CLARIFICATION"].support == 2 and "garoa" in found["UNCOVERED_IN_CLARIFICATION"].id
    assert not any("neblina" in p.id for p in proposals)                          # a trilha de medição não entra
