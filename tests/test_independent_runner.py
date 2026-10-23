"""Runner do conjunto independente: integridade do congelamento e comparação conservadora (sem LLM, sem rede)."""
import json

import pytest

from eval import run_independent as ri


def test_frozen_hash_matches_manifest():
    if not ri.FROZEN.exists():
        pytest.skip("conjunto congelado ausente")
    assert ri.verify_frozen()


def test_frozen_hash_mismatch_refuses(tmp_path):
    f = tmp_path / "q.yaml"
    f.write_text("questions: []\n", encoding="utf-8")
    m = tmp_path / "m.json"
    m.write_text(json.dumps({"files": {"questions_independent_frozen.yaml": "0" * 64}}), encoding="utf-8")
    with pytest.raises(SystemExit):
        ri.verify_frozen(f, m)


def test_auto_compare_match_and_tolerance():
    assert ri.auto_compare([["SBGL", 22.0472]], [[22.047192513368984]])[0] == "match"
    assert ri.auto_compare([[5.0]], [[22.0]])[0] == "diverge"


def test_auto_compare_uses_each_number_once():
    assert ri.auto_compare([[3.0]], [[3.0, 3.0]])[0] == "diverge"
    assert ri.auto_compare([[3.0, 3.0]], [[3.0, 3.0]])[0] == "match"


def test_auto_compare_no_numbers_goes_to_human():
    assert ri.auto_compare([["SBGL"]], [["SBGL"]])[0] == "diverge"


def _q(beh):
    return {"id": "X", "category": "c", "expected_behavior": beh}


def test_judge_row_statuses():
    orc = {"X": [[1.0]]}
    assert ri.judge_row(_q("answerable"), "answered", [[1.0]], orc)["auto"] == "match"
    assert ri.judge_row(_q("answerable"), "unsupported", [], orc)["auto"] == "abstained"
    assert ri.judge_row(_q("answerable"), "no_results", [], orc)["auto"] == "diverge"
    assert ri.judge_row(_q("unsupported"), "unsupported", [], orc)["status_ok"]
    r = ri.judge_row(_q("needs_clarification"), "answered", [[1.0]], orc)
    assert not r["status_ok"] and r["auto"] == "answered_unanswerable"


def test_sparql_rows_normalizes():
    res = {"head": {"vars": ["s", "v"]}, "results": {"bindings": [
        {"s": {"type": "uri", "value": "http://x/station/SBGL"},
         "v": {"type": "literal", "datatype": "http://www.w3.org/2001/XMLSchema#decimal", "value": "2.5"}}]}}
    assert ri.sparql_rows(res) == [["SBGL", 2.5]]
    assert ri.sparql_rows(None) == []


def test_oracle_loads_only_ok():
    if not (ri.PKG / "independent_validation.json").exists():
        pytest.skip("validação ausente")
    o = ri.load_oracle()
    assert len(o) == 40 and all(o[k] for k in o)
