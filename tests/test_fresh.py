"""O gabarito do conjunto "fresh" precisa estar certo ANTES de medir o LLM: referência x oráculo, sem falso positivo
das regras, valores-chave conferidos à mão e comportamento das recusas."""
import pytest

from eval import oracle_fresh
from eval.compare import compare, rows_from_sparql
from eval.run_reference import load_questions
from kgqa.store import PREFIXES, LocalRdflibBackend
from pipeline.validators import validate_query
from pipeline.vocab import OntologyIndex

QS = {q["id"]: q for q in load_questions(suite="fresh")}
WITH_SPARQL = [q for q in QS.values() if "sparql" in q]
B, INDEX = LocalRdflibBackend(), OntologyIndex.load()


@pytest.mark.parametrize("q", WITH_SPARQL, ids=[q["id"] for q in WITH_SPARQL])
def test_reference_matches_oracle(q):
    r = B.select(PREFIXES + q["sparql"], timeout_s=30)
    assert r.ok, r.error
    ok, why = compare(rows_from_sparql(r.results, q["compare"]["columns"]), oracle_fresh.expected(q["id"]), q["compare"])
    assert ok, why


@pytest.mark.parametrize("q", WITH_SPARQL, ids=[q["id"] for q in WITH_SPARQL])
def test_reference_queries_raise_no_findings(q):
    assert [f.diag.code for f in validate_query(q["sparql"], None, INDEX)[1]] == []


def test_split_and_behaviour_cases():
    assert len(QS) == 10 and {q["split"] for q in QS.values()} == {"fresh"}
    assert {q["id"]: q["expected_status"] for q in QS.values() if "sparql" not in q} == {
        "G07": "unsupported", "G08": "needs_clarification", "G09": "unsupported"}


# valores conferidos à mão a partir de data/observations.csv
def test_hand_checked_values():
    assert oracle_fresh.expected("G05") == [(28,)]                       # 7 dias x 4 horários
    assert oracle_fresh.expected("G04") == [(0,)]                        # 12/03 está fora de 02–08/03
    assert [r[0] for r in oracle_fresh.expected("G06")] == ["EST-A", "EST-B"]
    assert [str(v) for (v,) in oracle_fresh.expected("G03")] == ["90.1"]


def test_the_refusal_cases_really_are_outside_what_the_source_can_answer():
    """G07: a ontologia prevê WindSpeed, o grafo não tem dado. G09: a estação não existe. G08: data relativa."""
    from pipeline.vocab import MET
    assert MET + "WindSpeed" in INDEX.properties and MET + "WindSpeed" not in INDEX.properties_with_data
    assert not INDEX.link_entities(QS["G09"]["question"])
    from pipeline.validators import RELATIVE_TIME
    from pipeline.vocab import fold
    assert RELATIVE_TIME.search(fold(QS["G08"]["question"]))
    assert INDEX.coverage and INDEX.coverage[1].isoformat() < "2026-03-12"          # G04
