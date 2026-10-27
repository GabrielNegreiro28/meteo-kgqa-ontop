"""MVP (`metqa/`) de ponta a ponta no GRAFO REAL (Ontop), com o LLM roteirizado: a interpretação que um LLM devolveria (só trechos) para as
perguntas do novo_a em que o v4–v7 erraram passa por TODA a pipeline (leitura, conciliação, verificação, plano, compilação, motor,
verificação, texto) e o número do texto tem de ser o do oráculo pandas. Não mede o LLM real (isso exige verba)."""
import json

import pytest

from kgqa.contract import Status
from kgqa.store import OntopBackend
from metqa.app import MetQA, Settings
from metqa.knowledge import DomainCatalog, OntologyLexicon
from metqa.presentation.render import num
from pipeline.llm import ScriptedLLM
from tests.test_real_pipeline import needs_ontop
from tests.test_reconcile import ir
from tests.test_v8_real import CASES, QUESTIONS

EXPECTED = {"E05": 13959, "E07": 1000, "E11": 35.4, "E15": 360, "E43": 31.9, "E44": 64.1, "E50": 8.81, "E48": 180.8}


@pytest.fixture(scope="module")
def real():
    source = OntopBackend()
    return source, DomainCatalog.from_ontop(source)


def ask(real, question, raw):
    source, catalog = real
    qa = MetQA(catalog, OntologyLexicon(catalog), ScriptedLLM({"interpret": [json.dumps(raw, ensure_ascii=False)]}), source,
               Settings(timeout_s=120))
    return qa.ask(question)


@needs_ontop
@pytest.mark.parametrize("qid", sorted(EXPECTED))
def test_mvp_answers_with_the_oracle_number(real, qid):
    res = ask(real, QUESTIONS[qid], CASES[qid])
    r = res.response
    assert r.status == Status.ANSWERED, (qid, [d.message for d in r.diagnostics])
    assert num(EXPECTED[qid]) in r.answer_text, (qid, r.answer_text)
    assert r.provenance.generated_sql                                          # o SQL que o Ontop gerou, para a procedência
    from semantics.trajectories import to_trajectory
    assert to_trajectory(res)["pipeline_status"] == "answered"                  # a trilha do MVP alimenta a evolução


@needs_ontop
def test_mvp_compares_two_periods(real):
    q = "SBPA esteve mais quente em janeiro de 2016 ou em janeiro de 2025?"
    raw = ir("met:AirTemperature", "quente", "SBPA", "avg", "mais quente")
    r = ask(real, q, raw).response
    assert r.status == Status.ANSWERED, [d.message for d in r.diagnostics]
    assert "janeiro de 2016" in r.answer_text and "janeiro de 2025" in r.answer_text and "Maior em" in r.answer_text


@needs_ontop
def test_mvp_reads_the_value_at_an_instant(real):
    # 14/10/2019 14h local em SBGO: 35,4 °C no CSV original (conferido na adjudicação do novo_a, E11)
    q = "Qual era a temperatura do ar em SBGO em 14/10/2019 às 14h?"
    r = ask(real, q, {**ir("met:AirTemperature", "temperatura do ar", "SBGO"), "aggregation": None}).response
    assert r.status == Status.ANSWERED, [d.message for d in r.diagnostics]
    assert "35,4 °C" in r.answer_text and "14/10/2019 14:00" in r.answer_text
