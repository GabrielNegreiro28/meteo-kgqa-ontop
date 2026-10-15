"""Consultas de referência x oráculo, e prova de que o avaliador detecta consultas erradas."""
import pytest

from eval import oracle
from eval.compare import compare, rows_from_sparql
from eval.run_reference import load_questions
from kgqa.contract import Status
from kgqa.store import PREFIXES, LocalRdflibBackend
from kgqa.verify import result_status

B = LocalRdflibBackend()
QS = {q["id"]: q for q in load_questions()}
WITH_SPARQL = [q for q in QS.values() if "sparql" in q]


def _run(q, sparql=None):
    r = B.select(PREFIXES + (sparql or q["sparql"]), timeout_s=20)
    assert r.ok, r.error
    return r.results


@pytest.mark.parametrize("q", WITH_SPARQL, ids=[q["id"] for q in WITH_SPARQL])
def test_reference_matches_oracle(q):
    res = _run(q)
    ok, why = compare(rows_from_sparql(res, q["compare"]["columns"]), oracle.expected(q["id"]), q["compare"])
    assert ok, why
    assert result_status(res)[0].value == q["expected_status"]


def test_split_sizes():
    assert sum(q["split"] == "dev" for q in QS.values()) == 8
    assert sum(q["split"] == "test" for q in QS.values()) == 16


# ---- Mutações: consultas plausíveis porém erradas devem FALHAR na comparação ----

def test_mutation_forecast_leaks_into_max():
    """Sem exigir o tipo observação, a previsão de 35,0 °C vira a 'maior temperatura registrada'."""
    q = QS["T03"]
    naive = """SELECT ?station ?value ?t WHERE {
      ?x sosa:hasResult/qudt:numericValue ?value ; (sosa:phenomenonTime|met:validTime)/time:inXSDDateTime ?t .
      ?x (sosa:madeBySensor/^sosa:hosts)|met:forStation ?station .
      ?x (sosa:observedProperty|met:forecastedProperty) met:AirTemperature .
    } ORDER BY DESC(?value) LIMIT 1"""
    ok, _ = compare(rows_from_sparql(_run(q, naive), q["compare"]["columns"]), oracle.expected("T03"), q["compare"])
    assert not ok


def test_mutation_boundary_operator():
    q = QS["D03"]
    wrong = q["sparql"].replace("?value > 30", "?value >= 30")
    ok, why = compare(rows_from_sparql(_run(q, wrong), q["compare"]["columns"]), oracle.expected("D03"), q["compare"])
    assert not ok and "EST-A-TEMP-20260304T1200" in why


def test_mutation_avg_of_empty_is_zero_not_missing():
    """Sem ?n, AVG sobre vazio devolve 0 e pareceria 'umidade média 0 %'."""
    q = QS["T08"]
    no_count = q["sparql"].replace("(COUNT(?v) AS ?n)", "")
    res = _run(q, no_count)
    assert res["results"]["bindings"][0]["avg"]["value"] == "0"
    assert result_status(res)[0] == Status.ANSWERED          # o verificador não tem como saber...
    assert result_status(_run(q))[0] == Status.NO_RESULTS    # ...por isso exigimos ?n nas agregações


def test_mutation_period_end_exclusive():
    """Tratar 'até 05/03' como < 05/03 00:00 perde o último dia."""
    q = QS["D04"]
    wrong = q["sparql"].replace("2026-03-06T00:00:00-03:00", "2026-03-05T00:00:00-03:00")
    ok, _ = compare(rows_from_sparql(_run(q, wrong), q["compare"]["columns"]), oracle.expected("D04"), q["compare"])
    assert not ok
