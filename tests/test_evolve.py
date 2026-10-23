"""Ciclo de evolução (§7.3): minerar, montar o Candidate, porta, avaliação pareada, aceitar ou rejeitar. Sem LLM e sem rede.

Cenário: a pergunta usa "calorão", que nenhum Termo conhece. Duas trajetórias de construção (confiáveis) terminaram em temperatura do ar com
essa palavra sem cobertura; um Candidate que a acrescenta como sinônimo melhora a validação congelada sem regredir a regressão.
"""
import copy
import json
from pathlib import Path

import pytest
from evoontology.evolution.session import EvolutionSession
from evoontology.ontology.store import SemanticStore
from evoontology.trajectory.trajectory import TrajectoryStore

from pipeline.vocab import expand
from semantics import evolve
from semantics.build import build_v0
from semantics.resolution import CONSTRUCTION_FILES, VALIDATION_FILES, Case, ResolutionAdapter, load_cases, score
from tests.test_semantics import term

AIR = expand("met:AirTemperature")
HUM = expand("met:RelativeHumidity")


@pytest.fixture()
def ws(tmp_path):
    build_v0(tmp_path)
    return tmp_path


def trajectory(task_id, uncovered, props, *, status="answered", split="", corrections=0, findings=()):
    return {"task_id": task_id, "question": "x", "split": split, "pipeline_status": status,
            "native_tool_calls": [{"tool": "interpret", "input": {}, "result": {"interpretation": {"properties": props}, "findings": []}}],
            "signals": {"semantics": {"uncovered": uncovered}, "user_corrections": corrections, "verifier_findings": list(findings)}}


def add(ws, *ts):
    store = TrajectoryStore(ws)
    for t in ts:
        store.append(t)


VAL = [Case("v1", "Qual foi o calorão médio de SBGL em 2019?", frozenset({AIR}), "t"),
       Case("v2", "Qual a umidade relativa média de SBGL em 2019?", frozenset({HUM}), "t")]
REG = [Case("r1", "Qual a temperatura do ar média de SBGL?", frozenset({AIR}), "t")]


def adapters(ws):
    return ResolutionAdapter(ws, VAL), ResolutionAdapter(ws, REG)


def two_calorao():
    return [trajectory("t1", ["calorão"], ["met:AirTemperature"]), trajectory("t2", ["calorão"], ["met:AirTemperature"])]


# ---------- minerar ----------

def test_mining_turns_a_recurring_uncovered_word_into_an_alias(ws):
    add(ws, *two_calorao())
    hyps, _ = evolve.mine(ws, "ontology_v0")
    assert [(h.layer, h.term_id, h.alias, h.support) for h in hyps] == [("content", "term.AirTemperature", "calorão", 2)]


@pytest.mark.parametrize("name,trajs", [
    ("support_too_low", [trajectory("t1", ["calorão"], ["met:AirTemperature"])]),
    ("two_quantities_is_real_ambiguity", [trajectory("t1", ["calorão"], ["met:AirTemperature"]), trajectory("t2", ["calorão"], ["met:RelativeHumidity"])]),
    ("held_out_is_invisible_to_the_miner", [trajectory("t1", ["calorão"], ["met:AirTemperature"], split="heldout"),
                                            trajectory("t2", ["calorão"], ["met:AirTemperature"], split="validation")]),
    ("untrusted_abstentions_teach_nothing", [trajectory("t1", ["calorão"], ["met:AirTemperature"], status="unsupported"),
                                             trajectory("t2", ["calorão"], ["met:AirTemperature"], status="rejected")]),
    ("user_corrected_means_the_answer_was_not_right", [trajectory("t1", ["calorão"], ["met:AirTemperature"], corrections=1),
                                                       trajectory("t2", ["calorão"], ["met:AirTemperature"], corrections=1)]),
    ("a_word_a_term_already_has_is_a_conflict", [trajectory("t1", ["umidade"], ["met:AirTemperature"]), trajectory("t2", ["umidade"], ["met:AirTemperature"])]),
    ("two_quantities_in_one_answer_cannot_be_attributed", [trajectory("t1", ["calorão"], ["met:AirTemperature", "met:RelativeHumidity"]),
                                                           trajectory("t2", ["calorão"], ["met:AirTemperature", "met:RelativeHumidity"])]),
])
def test_mining_refuses_what_it_cannot_attribute(ws, name, trajs):
    add(ws, *trajs)
    assert evolve.mine(ws, "ontology_v0")[0] == [], name


def test_recurring_verifier_findings_become_proposals_not_patches(ws):
    add(ws, trajectory("t1", [], ["met:AirTemperature"], status="rejected", findings=["UNKNOWN_IRI", "BAD_SCHEMA"]),
        trajectory("t2", [], ["met:AirTemperature"], status="rejected", findings=["UNKNOWN_IRI"]))
    hyps, proposals = evolve.mine(ws, "ontology_v0")
    assert hyps == []
    assert {(p.layer, p.finding) for p in proposals} == {("formal", "UNKNOWN_IRI")}        # BAD_SCHEMA aparece uma vez: sem suporte
    path = evolve.write_proposals(ws, proposals)
    assert json.loads(Path(path).read_text(encoding="utf-8"))[0]["layer"] == "formal"
    assert evolve.write_proposals(ws, []) is None


# ---------- o remendo ----------

def test_the_patch_is_small_localized_and_carries_evidence(ws):
    _, records = SemanticStore.load_records(ws, version="ontology_v0")
    h = evolve.Hypothesis("alias.calorao.term.AirTemperature", "content", "add_alias", "term.AirTemperature", "calorão", 2, ["t1", "t2"], "porque sim")
    patched = evolve.apply(records, h)
    assert "calorão" in term(patched, "AirTemperature")["aliases"] and "calorao" in term(patched, "AirTemperature")["aliases"]
    before = {t["id"]: t for t in records["terms"]}
    changed = [t["id"] for t in patched["terms"] if t != before[t["id"]]]
    assert changed == ["term.AirTemperature"]                                  # só um Termo mudou
    assert len(patched["evidence"]) == len(records["evidence"]) + 1
    assert patched["constraints"] == records["constraints"] and patched["relations"] == records["relations"]


# ---------- avaliação ----------

def test_resolution_score_is_jaccard_and_the_parent_misses_the_new_word(ws):
    assert score({AIR}, frozenset({AIR})) == 1.0 and score(set(), frozenset({AIR})) == 0.0 and score({AIR, HUM}, frozenset({AIR})) == 0.5
    val, _ = adapters(ws)
    res = val.evaluate("ontology_v0")
    assert {c["id"]: c["score"] for c in res["cases"]} == {"v1": 0.0, "v2": 1.0}


def test_benchmark_cases_have_disjoint_construction_and_validation_files():
    assert not set(CONSTRUCTION_FILES) & set(VALIDATION_FILES)
    cons, val = load_cases(CONSTRUCTION_FILES), load_cases(VALIDATION_FILES)
    assert len(cons) > 20 and len(val) > 20
    assert not {c.question for c in cons} & {c.question for c in val}, "pergunta repetida entre construção e validação"


# ---------- o ciclo ----------

def run(ws, **kw):
    val, reg = adapters(ws)
    return evolve.run_evolution(ws, "ontology_v0", val, reg, **kw)


def test_a_good_candidate_is_accepted_published_and_activated(ws):
    add(ws, *two_calorao())
    s = run(ws)
    assert s["accepted_version"] == "ontology_v1" and s["rounds"][0]["decision"] == "accept"
    assert s["rounds"][0]["parent_score"] == 0.5 and s["rounds"][0]["candidate_score"] == 1.0 and not s["rounds"][0]["regression"]
    assert SemanticStore.active_version(ws) == "ontology_v1"
    assert "calorão" in term(SemanticStore.load_records(ws, version="ontology_v1")[1], "AirTemperature")["aliases"]
    assert EvolutionSession(ws).latest_run()["status"] == "accepted"


def test_the_published_version_is_reversible_the_parent_still_exists(ws):
    add(ws, *two_calorao())
    run(ws)
    SemanticStore.set_active(ws, "ontology_v0")
    assert SemanticStore.active_version(ws) == "ontology_v0"
    assert "calorão" not in term(SemanticStore.load_records(ws, version="ontology_v0")[1], "AirTemperature")["aliases"]


def test_a_candidate_that_regresses_is_rejected_even_if_it_gains_elsewhere(ws, monkeypatch):
    add(ws, *two_calorao())
    real = evolve.apply

    def greedy(records, h):
        out = real(records, h)
        term(out, "AirTemperature")["aliases"].append("umidade relativa")       # rouba a grandeza que o Parent acertava (v2)
        return out
    monkeypatch.setattr(evolve, "apply", greedy)
    s = run(ws)
    assert s["accepted_version"] is None and s["rounds"][0]["decision"] == "reject" and s["rounds"][0]["reason"] == "regression"
    assert SemanticStore.active_version(ws) == "ontology_v0"


def test_a_candidate_with_an_invented_bfo_category_never_reaches_the_evaluation(ws, monkeypatch):
    add(ws, *two_calorao())
    real = evolve.apply

    def invented(records, h):
        out = real(records, h)
        term(out, "WeatherStation")["bfo_category"] = "process"
        return out
    monkeypatch.setattr(evolve, "apply", invented)
    s = run(ws)
    assert s["rounds"][0]["reason"] == "gate" and "parent_score" not in s["rounds"][0]
    assert any("nunca inventada" in e for e in s["rounds"][0]["errors"])


def test_no_hypothesis_means_no_run_is_opened(ws):
    s = run(ws)
    assert s["run_id"] is None and s["accepted_version"] is None and "nada a evoluir" in s["note"]
    assert EvolutionSession(ws).latest_run() is None


def test_round_budget_is_frozen_and_the_run_ends_incomplete_when_spent(ws, monkeypatch):
    add(ws, *two_calorao(), trajectory("t3", ["quentura"], ["met:AirTemperature"]), trajectory("t4", ["quentura"], ["met:AirTemperature"]))
    monkeypatch.setattr(evolve, "apply", lambda records, h: copy.deepcopy(records))            # remendo vazio: nunca melhora
    s = run(ws, max_rounds=2)
    assert [r["decision"] for r in s["rounds"]] == ["reject", "reject"] and s["incomplete"] == "budget_exhausted"
    assert EvolutionSession(ws).latest_run()["status"] == "incomplete" and SemanticStore.active_version(ws) == "ontology_v0"
