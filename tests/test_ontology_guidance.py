"""A ontologia guia a montagem e a validação das consultas: relações, forma do tempo e agregações vêm dos axiomas
de ontology/met-structure.ttl, não de texto escrito à mão."""
import json
from pathlib import Path

import pytest
import yaml

from eval.run_reference import load_questions
from eval.safety_experiment import CASES
from pipeline.validators import PipelineInterpretation, validate_interpretation, validate_query
from pipeline.vocab import MET, SOSA, TIME, OntologyIndex

ROOT = Path(__file__).resolve().parent.parent
INDEX = OntologyIndex.load()
QS = {q["id"]: q for q in load_questions()}


# ------------------------------ o que a ontologia declara ------------------------------

def test_every_observable_property_has_a_kind_a_time_shape_and_aggregations():
    for iri, p in INDEX.properties.items():
        assert p.kind, iri
        assert INDEX.time_shape(iri), iri
        assert "count" in p.aggregations, iri


@pytest.mark.parametrize("prop,shape", [("Precipitation", "Interval"), ("PrecipitationDuration", "Interval"),
                                        ("AirTemperature", "Instant"), ("WindDirection", "Instant"), ("CloudCover", "Instant")])
def test_time_shape_is_derived_from_the_observation_class(prop, shape):
    assert INDEX.time_shape(MET + prop) == TIME + shape


def test_time_paths_are_derived_from_domain_and_range():
    assert INDEX.time_paths(TIME + "Instant") == ["time:inXSDDateTime"]
    assert INDEX.time_paths(TIME + "Interval") == ["time:hasBeginning/time:inXSDDateTime", "time:hasEnd/time:inXSDDateTime"]


def test_generated_context_carries_relations_and_patterns_without_handwritten_text():
    ctx = INDEX.prompt_context("ontology")
    assert "sosa:Platform —sosa:hosts→ sosa:Sensor" in ctx
    assert "sosa:Observation —sosa:madeBySensor→ sosa:Sensor" in ctx
    line = next(l for l in ctx.splitlines() if l.startswith("- met:Precipitation "))
    assert "time:Interval" in line and "?iv time:hasBeginning/time:inXSDDateTime ?hasBeginning" in line
    assert "time:hasEnd/time:inXSDDateTime ?hasEnd" in line and "agregações: count, max, min, sum" in line
    assert "met:observedAs" not in ctx                       # relações internas de guia não vazam para o contexto


def test_labels_context_is_unchanged_for_reproducibility_of_v1_v2():
    ctx = INDEX.prompt_context()
    assert "acumulada (soma permitida)" in ctx and "?iv" not in ctx


# ------------------------------ agregações permitidas pela ontologia ------------------------------

@pytest.mark.parametrize("prop,agg,ok", [("AirTemperature", "sum", False), ("AirTemperature", "avg", True),
                                         ("Precipitation", "sum", True), ("Precipitation", "avg", False),
                                         ("WindDirection", "avg", False), ("WindDirection", "count", True),
                                         ("CloudCover", "max", False)])
def test_allowed_aggregations_come_from_the_ontology(prop, agg, ok):
    codes = [f.diag.code for f in validate_interpretation(PipelineInterpretation(properties=[f"met:{prop}"], aggregation=agg), INDEX)]
    assert (codes == []) is ok and (ok or codes == ["AGGREGATION_NOT_ALLOWED"])


# ------------------------------ checagem de tipos dos caminhos ------------------------------

INTERVAL_OK = """SELECT (SUM(?v) AS ?total) (COUNT(?v) AS ?n) WHERE { st:EST-B sosa:hosts ?s .
  ?o sosa:madeBySensor ?s ; sosa:observedProperty met:Precipitation ; sosa:phenomenonTime ?iv ; sosa:hasResult/qudt:numericValue ?v .
  ?iv time:hasBeginning/time:inXSDDateTime ?b ; time:hasEnd/time:inXSDDateTime ?e . }"""
INTERVAL_AS_INSTANT = INTERVAL_OK.replace("sosa:phenomenonTime ?iv ;", "sosa:phenomenonTime/time:inXSDDateTime ?b ;").replace(
    "?iv time:hasBeginning/time:inXSDDateTime ?b ; time:hasEnd/time:inXSDDateTime ?e .", "")
INSTANT_AS_INTERVAL = """SELECT (AVG(?v) AS ?avg) (COUNT(?v) AS ?n) WHERE { st:EST-B sosa:hosts ?s .
  ?o sosa:madeBySensor ?s ; sosa:observedProperty met:AirTemperature ; sosa:phenomenonTime ?iv ; sosa:hasResult/qudt:numericValue ?v .
  ?iv time:hasBeginning/time:inXSDDateTime ?b . }"""


def codes(q):
    return [f.diag.code for f in validate_query(q, None, INDEX)[1]]


def test_correct_interval_pattern_passes():
    assert codes(INTERVAL_OK) == []


def test_interval_observation_queried_as_instant_is_a_type_clash():
    assert codes(INTERVAL_AS_INSTANT) == ["TYPE_CLASH"]


def test_instant_observation_queried_as_interval_is_a_type_clash():
    assert "TYPE_CLASH" in codes(INSTANT_AS_INTERVAL)


def test_type_clash_message_tells_the_llm_how_to_repair():
    msg = next(f.diag.message for f in validate_query(INTERVAL_AS_INSTANT, None, INDEX)[1] if f.diag.code == "TYPE_CLASH")
    assert "tempo" in msg and "time:Instant" in msg and "time:Interval" in msg


# ------------------------------ controle: nenhuma consulta de referência correta é barrada ------------------------------

@pytest.mark.parametrize("suite", ["questions.yaml", "questions_real.yaml"])
def test_no_type_check_false_positives_on_reference_queries(suite):
    qs = yaml.safe_load((ROOT / "eval" / suite).read_text(encoding="utf-8"))["questions"]
    bad = [(q["id"], c) for q in qs if "sparql" in q
           for c in codes(q["sparql"]) if c in ("TYPE_CLASH", "DISJOINT_TYPES", "RESOURCE_COMPARED_TO_STRING")]
    assert bad == []


# ------------------------------ replay de falhas reais do LLM ------------------------------

@pytest.mark.parametrize("version,qid,expected", [("v1", "D05", "TYPE_CLASH"), ("v1", "T06", "TYPE_CLASH"),
                                                   ("v2", "T03", "CLASS_WITHOUT_DIRECT_INSTANCES")])
def test_replay_real_llm_false_absences_are_now_caught(version, qid, expected):
    f = ROOT / "eval" / "reports" / f"llm_run_{version}.json"
    if not f.exists():
        pytest.skip("eval/reports não é versionado: rode eval.run_llm_pipeline")
    sparql = next(r["sparql"] for r in json.loads(f.read_text(encoding="utf-8")) if r["id"] == qid)
    assert expected in codes(sparql)


# ------------------------------ semântica de período dos acumulados (D-06) e unidades ------------------------------

def test_containment_and_symbols_are_read_from_the_ontology():
    assert INDEX.properties[MET + "Precipitation"].containment and not INDEX.properties[MET + "AirTemperature"].containment
    assert INDEX.unit_symbols["http://qudt.org/vocab/unit/DEG_C"] == "°C"
    ctx = INDEX.prompt_context("ontology")
    assert "INTEIROS dentro do período" in next(l for l in ctx.splitlines() if l.startswith("- met:Precipitation "))
    assert "°C (unit:DEG_C, um recurso, não um texto)" in ctx


def test_interval_end_must_not_be_strictly_before_the_period_end():
    """O modelo escreveu `?fim < fim_do_período` e perdeu o último intervalo de 6 h (D05/T06 na execução real)."""
    for case in ("D05", "T06"):
        interp = CASES[case][0]
        ok = QS[case]["sparql"]
        assert [f.diag.code for f in validate_query(ok, interp, INDEX)[1]] == []
        strict = ok.replace("?e <= ", "?e < ")
        assert strict != ok
        assert "PERIOD_MISMATCH" in [f.diag.code for f in validate_query(strict, interp, INDEX)[1]]


def test_instant_properties_still_accept_the_exclusive_end():
    interp = CASES["D04"][0]
    assert [f.diag.code for f in validate_query(QS["D04"]["sparql"], interp, INDEX)[1]] == []


def test_unit_compared_to_text_is_flagged():
    q = QS["D03"]["sparql"].replace("qudt:unit unit:DEG_C", "qudt:unit ?u").replace(
        "FILTER(?value > 30)", 'FILTER(?value > 30) FILTER(?u = "unit:DEG_C")')
    assert "RESOURCE_COMPARED_TO_STRING" in codes(q)
    assert "RESOURCE_COMPARED_TO_STRING" not in codes(QS["D03"]["sparql"])


def test_text_comparison_of_a_literal_valued_variable_is_fine():
    q = "SELECT ?l WHERE { ?s a met:WeatherStation ; rdfs:label ?l . FILTER(?l = \"Estação Serra Azul\"@pt) }"
    assert "RESOURCE_COMPARED_TO_STRING" not in codes(q)


@pytest.mark.parametrize("version,qid,code", [("v3_r1", "T02", "RESOURCE_COMPARED_TO_STRING"),
                                               ("v3_r1", "D05", "PERIOD_MISMATCH"), ("v3_r1", "T06", "PERIOD_MISMATCH")])
def test_replay_real_failures_of_the_ontology_context_run(version, qid, code):
    f = ROOT / "eval" / "reports" / f"llm_run_{version}.json"
    if not f.exists():
        pytest.skip("eval/reports não é versionado: rode eval.run_llm_pipeline --prompts v3 --tag _r1")
    sparql = next(r["sparql"] for r in json.loads(f.read_text(encoding="utf-8")) if r["id"] == qid)
    interp = CASES[qid][0] if qid in CASES else None
    assert code in [x.diag.code for x in validate_query(sparql, interp, INDEX)[1]]


# ------------------------------ cobertura: o que a ontologia descreve, o contexto entrega ------------------------------

def test_context_lists_forecast_relations_and_disjointness_derived_from_the_ontology():
    ctx = INDEX.prompt_context("ontology")
    assert "met:Forecast —met:forStation→ met:WeatherStation" in ctx
    assert "met:Forecast —met:validTime→ time:Instant" in ctx
    assert "met:Forecast —met:forecastedProperty→ sosa:ObservableProperty" in ctx
    assert "met:Forecast ⟂ sosa:Observation" in ctx and "time:Instant ⟂ time:Interval" in ctx
    assert "met:observedAs" not in ctx and "met:symbol" not in ctx      # relações internas de guia ficam fora


def test_a_forecast_query_built_from_the_context_relations_is_valid():
    q = """SELECT ?f ?v ?issued WHERE { ?f a met:Forecast ; met:forStation st:EST-A ; met:forecastedProperty met:AirTemperature ;
        met:validTime/time:inXSDDateTime "2026-03-09T12:00:00-03:00"^^xsd:dateTime ; met:issuedAt ?issued ;
        sosa:hasResult/qudt:numericValue ?v . }"""
    assert codes(q) == []


# ------------------------------ perfil dos dados: a ontologia diz o que PODE existir, o grafo o que ESTÁ populado ------------------------------

def test_context_only_lists_relations_the_graph_actually_has():
    ctx = INDEX.prompt_context("ontology")
    assert "met:inReport" not in ctx and "met:reportOf" not in ctx            # na ontologia, mas sem dados no grafo sintético
    assert "sosa:Platform —sosa:hosts→ sosa:Sensor" in ctx and "met:Forecast —met:forStation→ met:WeatherStation" in ctx


def test_context_flags_quantities_without_observations():
    ctx = INDEX.prompt_context("ontology")
    assert "met:AirTemperature | dados: sim" in ctx
    assert "met:WindSpeed | dados: NENHUMA observação neste grafo" in ctx


def test_relation_declared_but_unpopulated_is_flagged():
    q = QS["D04"]["sparql"].replace("sosa:madeBySensor ?sensor ;", "sosa:madeBySensor ?sensor ; met:inReport ?rep ;")
    assert q != QS["D04"]["sparql"] and "RELATION_WITHOUT_DATA" in codes(q)


def test_reference_queries_use_only_populated_relations():
    for qid, q in QS.items():
        if "sparql" in q:
            assert "RELATION_WITHOUT_DATA" not in codes(q["sparql"]), qid


def test_with_a_real_data_profile_the_relation_is_allowed():
    idx = OntologyIndex.load()
    idx.data_predicates = idx.data_predicates | {MET + "inReport", MET + "reportOf"}      # perfil vindo do mapeamento Ontop
    q = "SELECT (COUNT(?o) AS ?n) WHERE { ?o met:inReport ?r . ?r met:reportOf st:EST-A }"
    assert "RELATION_WITHOUT_DATA" not in [f.diag.code for f in validate_query(q, None, idx)[1]]
    assert "met:inReport" in idx.prompt_context("ontology")


@pytest.mark.parametrize("version,qids", [("v3_h1", ["H01", "H02", "H04", "H08"]), ("v3_s3", ["D05", "T02"]), ("v3_s4", ["D05", "T02"])])
def test_replay_false_absences_caused_by_unpopulated_relations(version, qids):
    f = ROOT / "eval" / "reports" / f"llm_run_{version}.json"
    if not f.exists():
        pytest.skip("eval/reports não é versionado")
    rows = {r["id"]: r for r in json.loads(f.read_text(encoding="utf-8"))}
    hits = [q for q in qids if rows[q]["sparql"] and "RELATION_WITHOUT_DATA" in codes(rows[q]["sparql"])]
    assert hits, f"nenhuma consulta de {version} foi pega pela nova regra"


# ------------------------------ funções fora do SPARQL 1.1 ------------------------------

def test_xsd_date_is_not_a_sparql_function():
    q = QS["T16"]["sparql"].replace("SUBSTR(STR(?t), 1, 10)", "xsd:date(?t)")
    assert q != QS["T16"]["sparql"] and "UNSUPPORTED_FUNCTION" in codes(q)
    assert "UNSUPPORTED_FUNCTION" not in codes(QS["T16"]["sparql"])         # SUBSTR/STR são válidos


def test_standard_casts_are_allowed():
    q = "SELECT ?x WHERE { ?o qudt:numericValue ?v . BIND(xsd:integer(?v) AS ?x) BIND(xsd:string(?v) AS ?y) }"
    assert "UNSUPPORTED_FUNCTION" not in codes(q)


@pytest.mark.parametrize("version,qid", [("v3_s5", "T16"), ("pass1_namebased", "T07")])
def test_replay_real_xsd_date_failures(version, qid):
    f = ROOT / "eval" / "reports" / f"llm_run_{version}.json"
    if not f.exists():
        pytest.skip("eval/reports não é versionado")
    sparql = next(r["sparql"] for r in json.loads(f.read_text(encoding="utf-8")) if r["id"] == qid)
    assert "UNSUPPORTED_FUNCTION" in codes(sparql)


# ------------------------------ a estação é plataforma, não o local observado ------------------------------

def test_station_as_feature_of_interest_is_a_type_clash_for_constants_and_values():
    const = ("SELECT (COUNT(?o) AS ?n) WHERE { ?o a met:InstantaneousObservation ; sosa:hasFeatureOfInterest st:EST-C ; "
             "sosa:observedProperty met:AirTemperature . }")
    values = ("SELECT ?s (COUNT(?o) AS ?n) WHERE { VALUES ?s { st:EST-A st:EST-B } ?o a met:InstantaneousObservation ; "
              "sosa:hasFeatureOfInterest ?s ; sosa:observedProperty met:AirTemperature . } GROUP BY ?s")
    for q in (const, values):
        assert "TYPE_CLASH" in codes(q)
    msg = next(f.diag.message for f in validate_query(const, None, INDEX)[1] if f.diag.code == "TYPE_CLASH")
    assert "met:Site" in msg


def test_site_as_feature_of_interest_is_fine():
    q = ("SELECT (COUNT(?o) AS ?n) WHERE { ?site met:siteOf st:EST-C . ?o sosa:hasFeatureOfInterest ?site ; "
         "sosa:observedProperty met:AirTemperature . }")
    assert "TYPE_CLASH" not in codes(q)


@pytest.mark.parametrize("version,qids", [("v3_s6", ["D02", "D04", "T07"]), ("v3_h2", ["H03", "H08"])])
def test_replay_station_as_feature_of_interest_failures(version, qids):
    f = ROOT / "eval" / "reports" / f"llm_run_{version}.json"
    if not f.exists():
        pytest.skip("eval/reports não é versionado")
    rows = {r["id"]: r for r in json.loads(f.read_text(encoding="utf-8"))}
    hits = [q for q in qids if rows[q]["sparql"] and "TYPE_CLASH" in codes(rows[q]["sparql"])]
    assert len(hits) >= 2, hits
