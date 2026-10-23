"""Contexto do LLM no grafo real: atributos próprios por grandeza (P-29), estações numa linha (P-31) e a regra ATTRIBUTE_NOT_AVAILABLE.

Sem LLM e sem Ontop: o índice usa o perfil do `.obda`. O contexto do índice SINTÉTICO não pode mudar (v1–v4 foram medidos nele).
"""
from pathlib import Path

import pytest

from pipeline.validators import PipelineInterpretation, validate_query
from pipeline.vocab import MET, OBS_COMMON, STATION_NS, OntologyIndex, obda_observation_attributes, obda_profile

ROOT = Path(__file__).resolve().parent.parent
OBDA = ROOT / "mapping" / "met.obda"


def real_like(n=178):
    idx = OntologyIndex.load().with_profile_from_obda(OBDA)
    idx.entities = {f"{STATION_NS}SB{i:03d}": [f"SB{i:03d}"] for i in range(n)}      # como no grafo real: rótulo = código
    idx.entities[STATION_NS + "SBGR"] = ["SBGR"]
    return idx


def line_of(ctx: str, prop: str) -> str:
    return next(l for l in ctx.splitlines() if l.startswith(f"- met:{prop} "))


# ---------- atributos próprios, lidos do mapeamento ----------

def test_own_attributes_come_from_the_mapping_and_only_wind_has_them():
    attrs = obda_observation_attributes(OBDA)
    own = {p.rsplit("#", 1)[1]: sorted(a.rsplit("#", 1)[1] for a in v - OBS_COMMON - {"a"}) for p, v in attrs.items() if v - OBS_COMMON - {"a"}}
    assert own == {"WindSpeed": ["runwayDesignator", "windCondition"], "WindDirection": ["runwayDesignator"], "WindGust": ["runwayDesignator"]}


def test_obda_profile_is_unchanged_by_the_refactor():
    preds, types = obda_profile(OBDA)
    assert MET + "localDate" in preds and MET + "runwayDesignator" in preds and MET + "windCondition" in preds
    assert MET + "AccumulatedObservation" in types and MET + "WeatherStation" in types


def test_context_tells_the_llm_where_each_attribute_exists():
    ctx = real_like().prompt_context("ontology")
    assert "met:runwayDesignator" in line_of(ctx, "WindSpeed") and "met:windCondition" in line_of(ctx, "WindSpeed")
    assert "met:runwayDesignator" in line_of(ctx, "WindGust") and "windCondition" not in line_of(ctx, "WindGust")
    assert "atributos próprios" not in line_of(ctx, "AirTemperature")
    assert "Cabeceira" in line_of(ctx, "WindSpeed")                              # a descrição vem do rdfs:comment da ontologia


# ---------- estações ----------

def test_stations_go_on_one_line_when_the_label_is_the_code():
    ctx = real_like(178).prompt_context("ontology")
    stations = [l for l in ctx.splitlines() if l.startswith("Estações")]
    assert len(stations) == 1 and "SBGR" in stations[0] and "st:CÓDIGO" in stations[0]
    assert "- st:" not in ctx                                                    # nenhuma linha por estação
    assert len(stations[0]) < 2500                                               # eram ~4 mil caracteres só nesta parte


def test_both_context_styles_use_the_compact_line():
    idx = real_like()
    for style in ("labels", "ontology"):
        assert "- st:" not in idx.prompt_context(style)


def test_synthetic_context_keeps_the_old_one_line_per_station_format():
    """v1–v4 foram medidos no sintético: o formato das estações com nome não pode mudar."""
    idx = OntologyIndex.load()
    expected = "Estações conhecidas:\n" + "\n".join(
        f"- {iri.replace(STATION_NS, 'st:')} | {', '.join(labels)}" for iri, labels in sorted(idx.entities.items()))
    for style in ("labels", "ontology"):
        assert idx.prompt_context(style).endswith(expected)
    assert "atributos próprios" not in idx.prompt_context("ontology") and "met:localDate" not in idx.prompt_context("ontology")


# ---------- regra ATTRIBUTE_NOT_AVAILABLE ----------

IDX = real_like()


def interp(prop, agg="count", period=None):
    return PipelineInterpretation(entities=[{"text": "SBGR", "iri": "st:SBGR"}], properties=[prop], filters=[], period=period,
                                  aggregation=agg, record_kind="observation")


def q(prop, attr_triple):
    return (f"SELECT (COUNT(?o) AS ?n) WHERE {{ st:SBGR sosa:hosts ?s . ?o sosa:madeBySensor ?s ; sosa:observedProperty {prop} ; {attr_triple} . }}")


def codes(sparql, i):
    return sorted({f.diag.code for f in validate_query(sparql, i, IDX, True)[1]})


def test_runway_attribute_with_a_wind_quantity_is_accepted():
    assert "ATTRIBUTE_NOT_AVAILABLE" not in codes(q("met:WindSpeed", "met:runwayDesignator ?r"), interp("met:WindSpeed"))
    assert "ATTRIBUTE_NOT_AVAILABLE" not in codes(q("met:WindGust", "met:runwayDesignator ?r"), interp("met:WindGust"))


@pytest.mark.parametrize("prop,attr", [
    ("met:AirTemperature", "met:runwayDesignator"),        # temperatura não tem cabeceira
    ("met:Precipitation", "met:runwayDesignator"),
    ("met:WindGust", "met:windCondition"),                 # só a velocidade do vento tem a condição
    ("met:WindDirection", "met:windCondition"),
])
def test_an_attribute_the_quantity_does_not_have_is_rejected(prop, attr):
    got = codes(q(prop, f"{attr} ?x"), interp(prop))
    assert "ATTRIBUTE_NOT_AVAILABLE" in got


def test_universal_attributes_are_never_flagged():
    for attr in ("met:localDate ?x", "met:multipleReadings ?x", "met:sourceFile ?x", "met:inReport ?x"):
        assert "ATTRIBUTE_NOT_AVAILABLE" not in codes(q("met:AirTemperature", attr), interp("met:AirTemperature"))


def test_the_rule_is_off_without_a_real_profile():
    """No índice sintético não há mapeamento: a regra não age (e as consultas sintéticas continuam como estavam)."""
    syn = OntologyIndex.load()
    got = [f.diag.code for f in validate_query(q("met:AirTemperature", "met:runwayDesignator ?r"), interp("met:AirTemperature"), syn, True)[1]]
    assert "ATTRIBUTE_NOT_AVAILABLE" not in got
