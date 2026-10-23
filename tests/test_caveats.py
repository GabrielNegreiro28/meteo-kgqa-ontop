"""Ressalvas determinísticas na resposta: visibilidade censurada, amostra pequena, "n" = leituras, dias em UTC−3.

Origem: a auditoria dos dados (docs/ANALISE_CRITICA.md, seção 4). Cada ressalva existe porque o número, sozinho, engana:
79,8% das leituras de visibilidade valem o teto de 20 km; o ranking do RG15 trouxe a estação SBPW com n=149 ao lado de n=16.773.
"""
import json
from pathlib import Path

import pytest

from kgqa.contract import Status
from kgqa.store import OntopBackend
from pipeline.caveats import answer_caveats, format_caveats, low_sample_groups
from pipeline.dialogue import describe
from pipeline.llm import ScriptedLLM
from pipeline.orchestrator import run_pipeline
from pipeline.validators import PipelineInterpretation
from pipeline.vocab import STATION_NS, OntologyIndex
from tests.test_real_pipeline import needs_ontop

ROOT = Path(__file__).resolve().parent.parent
IDX = OntologyIndex.load().with_profile_from_obda(ROOT / "mapping" / "met.obda")
IDX.entities = {STATION_NS + s: [s] for s in ("SBGR", "SBPW", "SBFZ")}


def interp(prop="met:AirTemperature", agg="avg", **kw):
    return PipelineInterpretation(properties=[prop], aggregation=agg, entities=[], filters=[], period=None, record_kind="observation", **kw)


def results(rows):
    """rows = [(estação, valor, n)] no formato SPARQL JSON."""
    return {"head": {"vars": ["station", "value", "n"]},
            "results": {"bindings": [{"station": {"type": "uri", "value": f"{STATION_NS}{s}"},
                                      "value": {"type": "literal", "value": str(v), "datatype": "http://www.w3.org/2001/XMLSchema#decimal"},
                                      "n": {"type": "literal", "value": str(n), "datatype": "http://www.w3.org/2001/XMLSchema#integer"}}
                                     for s, v, n in rows]}}


# ---------- amostra pequena ----------

RG15 = [("SBPB", 12.51, 2931), ("SBAC", 11.48, 1743), ("SBPW", 11.09, 149), ("SBFZ", 9.98, 16773), ("SBMS", 9.98, 3762)]


def test_the_group_with_almost_no_readings_in_a_ranking_is_flagged():
    low, med = low_sample_groups(results(RG15))
    assert low == [("SBPW", 149)] and med == 2931           # os números reais do ranking RG15


def test_comparable_groups_are_not_flagged():
    assert low_sample_groups(results([("SBGR", 20, 8700), ("SBFZ", 21, 8650), ("SBPB", 22, 8800)]))[0] == []


@pytest.mark.parametrize("rows", [[("SBGR", 1, 5)], [("SBGR", 1, 5), ("SBFZ", 1, 5000)]])
def test_fewer_than_three_groups_say_nothing(rows):
    assert low_sample_groups(results(rows))[0] == []


def test_a_result_without_a_count_column_is_left_alone():
    r = {"head": {"vars": ["station", "value"]}, "results": {"bindings": [{"station": {"type": "uri", "value": STATION_NS + "SBGR"},
                                                                          "value": {"type": "literal", "value": "1"}}] * 4}}
    assert low_sample_groups(r) == ([], 0.0) and low_sample_groups(None) == ([], 0.0)


def test_the_low_sample_caveat_names_the_group_and_its_size():
    text = "\n".join(answer_caveats(interp(agg="avg"), results(RG15), IDX))
    assert "SBPW (n=149)" in text and "mediana" in text and "pouco confiáveis" in text


# ---------- por grandeza (anotação da ontologia) ----------

def test_visibility_always_carries_the_censoring_caveat():
    c = answer_caveats(interp("met:PrevailingVisibility"), results([("SBGR", 15000, 9000)]), IDX)
    assert len(c) == 1 and "20 km ou mais" in c[0] and "80%" in c[0]


@pytest.mark.parametrize("prop,fragment", [("met:WindGust", "não significa vento calmo"), ("met:PressureQNH", "nível médio do mar"),
                                           ("met:RunwayTemperature", "não identifica a pista")])
def test_other_quantities_with_a_known_pitfall_carry_theirs(prop, fragment):
    assert any(fragment in c for c in answer_caveats(interp(prop), results([("SBGR", 1, 100)]), IDX))


def test_a_quantity_without_a_pitfall_adds_nothing():
    assert answer_caveats(interp("met:AirTemperature"), results([("SBGR", 25, 8000)]), IDX) == []
    assert format_caveats([]) == ""


def test_the_caveats_come_from_the_ontology_not_from_code():
    assert IDX.properties["https://example.org/kgqa-met/ontology#PrevailingVisibility"].caveat.startswith("Visibilidade:")


def test_counts_say_they_are_readings_not_bulletins():
    c = answer_caveats(interp("met:WindSpeed", agg="count"), results([("SBGR", 1, 9406)]), IDX)
    assert any("leituras, não de boletins" in x for x in c)
    assert not any("boletins" in x for x in answer_caveats(interp("met:WindSpeed", agg="avg"), results([("SBGR", 1, 9406)]), IDX))


def test_the_caveats_are_not_in_the_llm_context():
    """Existem para o usuário: não podem engordar o prompt nem mudar o que já foi medido."""
    assert "Visibilidade: 20.000" not in IDX.prompt_context("ontology") and "Visibilidade: 20.000" not in IDX.prompt_context("labels")


# ---------- fuso ----------

def test_the_description_states_the_timezone_of_days():
    period = {"start": "2019-01-01", "end": "2019-12-31", "tz": "-03:00", "inclusive_end": True}
    with_period = PipelineInterpretation(properties=["met:AirTemperature"], period=period, aggregation="avg", entities=[], filters=[],
                                         record_kind="observation")
    assert "dias em UTC−3" in describe(with_period, IDX)
    assert "UTC" not in describe(interp(), IDX)                    # sem período, nada a dizer sobre fuso


# ---------- fluxo completo ----------

@needs_ontop
def test_a_visibility_answer_on_the_real_graph_ends_with_the_caveat():
    backend = OntopBackend()
    idx = OntologyIndex.from_ontop(backend)
    plan = {"status": "ok", "properties": ["met:PrevailingVisibility"], "entities": [{"text": "SBGR", "iri": "st:SBGR"}], "filters": [],
            "period": {"start": "2019-01-01", "end": "2019-12-31", "tz": "-03:00", "inclusive_end": True}, "aggregation": "avg",
            "record_kind": "observation"}
    llm = ScriptedLLM({"interpret": [json.dumps(plan)], "generate": ["{}"], "answer": ["x"]})
    res = run_pipeline("Qual foi a visibilidade média em SBGR em 2019?", llm, backend, idx, timeout_s=60, prompts_version="v6")
    assert res.response.status == Status.ANSWERED
    text = res.response.answer_text
    assert "Ressalvas:" in text and "20 km ou mais" in text and "dias em UTC−3" in text


# ---------- Codex C10: o piso absoluto vê o que a regra relativa não vê ----------

@pytest.mark.parametrize("rows", [[("SBPW", 11.0, 1)], [("SBPW", 11.0, 1), ("SBGR", 12.0, 10000)], [("A", 1, 1), ("B", 1, 1), ("C", 1, 1)]],
                         ids=["top1", "top2", "todos-pequenos"])
def test_tiny_samples_are_flagged_even_where_the_relative_rule_is_blind(rows):
    text = "\n".join(answer_caveats(interp(agg="avg"), results(rows), IDX))
    assert "menos de 30 leituras" in text and "n=1" in text


def test_a_count_answer_is_not_flagged_as_a_small_sample():
    text = "\n".join(answer_caveats(interp(agg="count"), results([("SBGR", 3, 3)]), IDX))
    assert "menos de 30" not in text


def test_a_well_covered_result_has_no_tiny_sample_caveat():
    assert "menos de 30" not in "\n".join(answer_caveats(interp(agg="avg"), results([("SBGR", 20, 8700)]), IDX))
