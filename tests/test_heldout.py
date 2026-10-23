"""O gabarito do conjunto held-out precisa estar certo ANTES de medir o LLM: referência x oráculo, sem falso positivo
das regras e valores-chave conferidos à mão."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from eval import oracle_heldout
from eval.compare import compare, rows_from_sparql
from eval.run_reference import load_questions
from kgqa.store import PREFIXES, LocalRdflibBackend
from pipeline.validators import validate_query
from pipeline.vocab import OntologyIndex

QS = {q["id"]: q for q in load_questions(suite="heldout")}
WITH_SPARQL = [q for q in QS.values() if "sparql" in q]
B, INDEX = LocalRdflibBackend(), OntologyIndex.load()


@pytest.mark.parametrize("q", WITH_SPARQL, ids=[q["id"] for q in WITH_SPARQL])
def test_reference_matches_oracle(q):
    r = B.select(PREFIXES + q["sparql"], timeout_s=30)
    assert r.ok, r.error
    ok, why = compare(rows_from_sparql(r.results, q["compare"]["columns"]), oracle_heldout.expected(q["id"]), q["compare"])
    assert ok, why


@pytest.mark.parametrize("q", WITH_SPARQL, ids=[q["id"] for q in WITH_SPARQL])
def test_reference_queries_raise_no_findings(q):
    assert [f.diag.code for f in validate_query(q["sparql"], None, INDEX)[1]] == []


def test_split_and_behaviour_cases():
    assert len(QS) == 10 and {q["split"] for q in QS.values()} == {"heldout"}
    assert [q["expected_status"] for q in QS.values() if "sparql" not in q] == ["needs_clarification", "unsupported"]


# valores conferidos à mão a partir de data/observations.csv
def test_h08_one_interval_is_missing_so_n_is_three():
    assert oracle_heldout.expected("H08")[0][1] == 3          # EST-C PREC sem 07/03 18:00 (ausência != zero)


def test_h06_only_litoral_sul_exceeds_32():
    assert oracle_heldout.expected("H06") == [("EST-C",)]     # 32.3 e 34.6; EST-B chega a 30.5 e EST-A a 30.0


def test_h07_forecast_issue_time():
    tz = timezone(timedelta(hours=-3))
    assert oracle_heldout.expected("H07") == [(datetime(2026, 3, 8, 18, 0, tzinfo=tz),)]


def test_h04_all_28_readings():
    assert oracle_heldout.expected("H04") == [(28,)]          # 7 dias x 4 horários
    assert oracle_heldout.expected("H05")[0][0] == Decimal("18.4")      # EST-B 04/03 12h (valor planejado no gerador)
