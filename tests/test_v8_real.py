"""v8 no GRAFO REAL (Ontop), sem LLM: para as perguntas do novo_a em que o v4–v7 erraram, a interpretação v8 que um LLM devolveria
(escrita à mão, só trechos) é conciliada, compilada, executada e comparada com o oráculo pandas congelado (eval/frozen/novo_a).

É a prova de que a parte determinística do v8 está certa nos dados reais: dia por extenso, parte do dia (hora UTC deslocada), fim de
semana (datas locais), horas distintas e a grandeza certa pela unidade. Não mede o LLM: isso exige a medição com verba (fase 4).
"""
import json
from pathlib import Path

import pytest

from eval.adjudicate import robust_match
from kgqa.store import PREFIXES, OntopBackend
from pipeline.compiler import compile_structured
from pipeline.reconcile import reconcile
from pipeline.validators import validate_interpretation, validate_query
from pipeline.vocab import OntologyIndex
from tests.test_real_pipeline import needs_ontop
from tests.test_reconcile import ir

ROOT = Path(__file__).resolve().parent.parent
ORACLE = {r["id"]: r.get("result") for r in json.loads((ROOT / "eval/frozen/novo_a/oracle_results.json").read_text(encoding="utf-8"))["results"]}
QUESTIONS = {q["id"]: q["question"] for q in __import__("yaml").safe_load((ROOT / "eval/frozen/novo_a/questions.yaml").read_text(encoding="utf-8"))["questions"]}

# id -> interpretação v8 (só o que é linguístico, com os trechos literais da pergunta)
CASES = {
    "E05": ir("met:PrecipitationDuration", "minutos de chuva", "SBFZ", "sum", "somando"),
    "E07": ir("met:PrevailingVisibility", "visibilidade", "SBGL", "min", "mínima"),
    "E11": ir("met:AirTemperature", "temperatura máxima do ar", "SBGO", "max", "máxima"),
    "E15": ir("met:Precipitation", "chuva", "SBCY", "count", "Quantas horas"),
    "E43": ir("met:AirTemperature", "temperatua", "sbpv", "max", "maxima"),
    "E44": ir("met:Precipitation", "choveu", "sbcg", "sum", "quantos mm"),
    "E50": ir("met:WindSpeed", "velocidade média do vento", "SBNT", "avg", "média"),
    # v4–v7 se abstiveram (todas as condições) da madrugada
    "E48": ir("met:Precipitation", "choveu", "SBBE", "sum", "Quanto choveu"),
}
# o oráculo pesa linhas IDÊNTICAS repetidas no CSV e o ingest as descarta (mesma diferença de E19/E27/E49): esperado = média das leituras
# distintas, medida nos CSV (verão de 2022 em SBSP: 3580 linhas, 2052 pares (instante, valor) distintos, média 21,971; o oráculo dá 21,78)
DEDUP = {"E47": (ir("met:AirTemperature", "temperatura", "SBSP", "avg", "média"), 21.971, 2052)}
# horas DISTINTAS (v8) contra o oráculo que contou linhas: o valor esperado é o de horas distintas medido nos CSV (julgamento do novo_a)
DISTINCT_HOURS = {
    "E13": (ir("met:PrevailingVisibility", "visibilidade", "SBSP", "count", "Em quantas horas",
               filters=[{"op": "<", "span": "abaixo de 1000 metros"}]), 12),
    "E19": (ir("met:RelativeHumidity", "umidade relativa", "SBBR", "count", "Quantas horas",
               filters=[{"op": "<", "span": "abaixo de 20%"}]), 51),
}


@pytest.fixture(scope="module")
def real():
    backend = OntopBackend()
    return backend, OntologyIndex.from_ontop(backend)


def _run(real, qid, raw):
    backend, idx = real
    rec = reconcile(raw, QUESTIONS[qid], idx)
    assert not rec.findings and rec.clarify is None and rec.unsupported is None, (qid, [f.diag.message for f in rec.findings], rec.clarify)
    assert not validate_interpretation(rec.interp, idx, None, (), True)
    sparql = compile_structured(rec.interp, idx, force=True)
    assert sparql and not validate_query(sparql, rec.interp, idx, True)[1], sparql
    ex = backend.select(PREFIXES + sparql, timeout_s=120, max_rows=100)
    assert ex.ok, ex.error
    return [[float(b[v]["value"]) for v in ex.results["head"]["vars"] if v in b] for b in ex.results["results"]["bindings"]]


@needs_ontop
@pytest.mark.parametrize("qid", sorted(CASES))
def test_v8_answers_what_v4_v7_got_wrong(real, qid):
    rows = _run(real, qid, CASES[qid])
    assert robust_match(rows, ORACLE[qid]), (qid, rows, ORACLE[qid])


@needs_ontop
def test_v8_summer_is_the_austral_season_on_distinct_readings(real):
    raw, mean, n = DEDUP["E47"]
    (value, count), = _run(real, "E47", raw)
    assert abs(value - mean) < 0.001 and count == n


@needs_ontop
@pytest.mark.parametrize("qid", sorted(DISTINCT_HOURS))
def test_v8_counts_distinct_hours(real, qid):
    raw, hours = DISTINCT_HOURS[qid]
    assert _run(real, qid, raw)[0][0] == hours
