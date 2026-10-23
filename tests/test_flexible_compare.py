"""O comparador por valor (usado na avaliação com LLM) aceita nomes de variável diferentes,
mas NÃO pode aceitar respostas erradas: ele é a régua do experimento."""
import pytest

from eval import oracle
from eval.compare import compare_flexible
from eval.run_reference import load_questions
from kgqa.store import PREFIXES, LocalRdflibBackend

QS = {q["id"]: q for q in load_questions()}
B = LocalRdflibBackend()


def run(sparql):
    r = B.select(PREFIXES + sparql, timeout_s=30)
    assert r.ok, r.error
    return r.results


def check(qid, sparql):
    return compare_flexible(run(sparql), oracle.expected(qid), QS[qid]["compare"])


def test_accepts_renamed_variables():
    q = QS["D03"]["sparql"].replace("?obs", "?observation")
    assert check("D03", q)[0]
    q = QS["D04"]["sparql"].replace("?avg", "?average")
    assert check("D04", q)[0]


def test_accepts_omitting_a_non_key_column_and_says_so():
    ok, note = check("T03", QS["T03"]["sparql"].replace("?station ?value ?t ?n WHERE", "?station ?value ?n WHERE"))
    assert ok and "omitidas" in note


@pytest.mark.parametrize("qid,old,new", [
    ("D03", "?value > 30", "?value > 29"),                                            # filtro diferente
    ("D04", "2026-03-06T00:00:00-03:00", "2026-03-05T00:00:00-03:00"),                # período diferente
    ("D04", "AVG(?v)", "MAX(?v)"),                                                    # agregação errada
    ("T04", "met:RelativeHumidity", "met:AirTemperature"),                            # propriedade errada
    ("T11", "st:EST-B", "st:EST-A"),                                                  # entidade errada
])
def test_rejects_wrong_answers(qid, old, new):
    assert old in QS[qid]["sparql"]
    assert not check(qid, QS[qid]["sparql"].replace(old, new))[0]


def test_never_accepts_omitting_a_key_column():
    """T06 agrupa por estação: sem a coluna da chave, os totais soltos não respondem a pergunta."""
    q = QS["T06"]["sparql"].replace("SELECT ?station (SUM(?v) AS ?total) (COUNT(?v) AS ?n)", "SELECT (SUM(?v) AS ?total) (COUNT(?v) AS ?n)")
    r = B.select(PREFIXES + q.replace("GROUP BY ?station", "GROUP BY ?station"), timeout_s=30)
    if r.ok:
        assert not compare_flexible(r.results, oracle.expected("T06"), QS["T06"]["compare"])[0]


def test_empty_matches_empty_whatever_the_columns():
    """T09 (dado ausente): resultado vazio com colunas diferentes das esperadas continua sendo 'vazio = vazio'."""
    q = QS["T09"]["sparql"].replace("?obs ?value", "?value")
    assert compare_flexible(run(q), oracle.expected("T09"), QS["T09"]["compare"])[0]


def test_empty_never_matches_a_non_empty_expectation():
    q = QS["D03"]["sparql"].replace("?value > 30", "?value > 99")
    assert not compare_flexible(run(q), oracle.expected("D03"), QS["D03"]["compare"])[0]


# ------------------------------------------------------------------ veredito com causa (incompleta / outra ordem / errada)
def _res(vars_, rows):
    return {"head": {"vars": vars_}, "results": {"bindings": [
        {v: ({"type": "uri", "value": f"x/{val}"} if isinstance(val, str) else
             {"type": "literal", "datatype": "http://www.w3.org/2001/XMLSchema#decimal", "value": str(val)}) for v, val in zip(vars_, r)}
        for r in rows]}}


def test_judge_separates_incomplete_and_reordered_from_wrong():
    from decimal import Decimal
    from eval.compare import judge
    spec = {"mode": "set", "columns": ["forecast", "value", "issued"]}
    expected = [("FC-1", Decimal("35.0"), "2026-03-08T18:00")]
    # valor certo, faltam id e emissão: INCOMPLETA (não errada)
    assert judge(_res(["value"], [(35.0,)]), expected, spec)[::2] == (True, "incomplete") or \
        judge(_res(["value"], [(35.0,)]), expected, spec)[2] == "incomplete"
    # valor errado continua errado
    assert judge(_res(["value"], [(36.0,)]), expected, spec)[2] == "wrong"
    # omitir a coluna NUMÉRICA nunca é "incompleta"
    only_id = _res(["forecast"], [("FC-1",)])
    assert judge(only_id, expected, spec)[2] == "wrong"
    ordered = {"mode": "ordered", "columns": ["station", "total"], "order_key": "total", "descending": True, "tolerance": {"total": 0.001}}
    exp2 = [("EST-B", Decimal("80.0")), ("EST-A", Decimal("55.4"))]
    assert judge(_res(["s", "t"], [("EST-B", 80.0), ("EST-A", 55.4)]), exp2, ordered)[2] == "exact"
    assert judge(_res(["s", "t"], [("EST-A", 55.4), ("EST-B", 80.0)]), exp2, ordered)[2] == "order_only"
    assert judge(_res(["s", "t"], [("EST-A", 80.0), ("EST-B", 55.4)]), exp2, ordered)[2] == "wrong"      # valores trocados entre estações
