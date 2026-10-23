"""Regressões da 1ª medição com o LLM real no grafo real (split dev, v4, 22/10/2026): consultas EXATAS que o modelo escreveu.

RD02: a 1ª tentativa estava certa e foi recusada por uma regra conservadora demais; o reparo inverteu `met:reportOf` e a consulta
vazia chegou ao usuário como "sem registros" onde há 3196 mm. RD03: BIND com nome já em uso, que o Ontop recusa e o rdflib aceita.
Sem LLM e sem Ontop.
"""
import re
from pathlib import Path

import pytest
import yaml

from eval.run_reference import SUITES, load_questions
from pipeline.validators import PipelineInterpretation, validate_query
from pipeline.vocab import STATION_NS, OntologyIndex

ROOT = Path(__file__).resolve().parent.parent

RD02_FIRST_ATTEMPT = """SELECT (SUM(?value) AS ?sum) (COUNT(?obs) AS ?n) WHERE { ?obs a met:AccumulatedObservation ; sosa:observedProperty met:Precipitation ; met:inReport ?report ; sosa:phenomenonTime ?iv ; met:localDate ?d ; sosa:hasResult ?result . ?report met:reportOf st:SBBE . ?result qudt:numericValue ?value ; qudt:unit unit:MilliM . ?iv time:hasBeginning/time:inXSDDateTime ?hasBeginning ; time:hasEnd/time:inXSDDateTime ?hasEnd . FILTER(?d >= "2019-01-01"^^xsd:date && ?d <= "2019-12-31"^^xsd:date && ?hasBeginning >= "2019-01-01T00:00:00-03:00"^^xsd:dateTime && ?hasEnd <= "2020-01-01T00:00:00-03:00"^^xsd:dateTime) }"""

RD02_AFTER_REPAIR_REVERSED = """SELECT (SUM(?value) AS ?total) (COUNT(?obs) AS ?n) WHERE { st:SBBE met:reportOf ?report . ?obs met:inReport ?report ; a met:AccumulatedObservation ; sosa:observedProperty met:Precipitation ; met:localDate ?d ; sosa:hasResult ?result . ?result qudt:numericValue ?value ; qudt:unit unit:MilliM . FILTER(?d >= "2019-01-01"^^xsd:date && ?d <= "2019-12-31"^^xsd:date) }"""

RD03_BIND_REUSES_NAME = """SELECT ?station ?max (COUNT(?obs) AS ?n) WHERE { { SELECT (MAX(?v0) AS ?max) WHERE { ?o0 sosa:observedProperty met:AirTemperature ; sosa:hasResult ?q0 . ?q0 qudt:numericValue ?v0 ; qudt:unit unit:DEG_C . } } ?station met:stationCode ?stationCode ; sosa:hosts ?sensor . ?obs sosa:madeBySensor ?sensor ; sosa:observedProperty met:AirTemperature ; sosa:hasResult ?q . ?q qudt:numericValue ?max ; qudt:unit unit:DEG_C . BIND(?stationCode AS ?station) } GROUP BY ?station ?max"""

YEAR = {"start": "2019-01-01", "end": "2019-12-31", "tz": "-03:00", "inclusive_end": True}


def real_index(stations=("SBBE", "SBGR")):
    idx = OntologyIndex.load().with_profile_from_obda(ROOT / "mapping" / "met.obda")
    idx.entities = {STATION_NS + s: [s] for s in stations}
    return idx


IDX = real_index()
RD02 = PipelineInterpretation(entities=[{"text": "SBBE", "iri": "st:SBBE"}], properties=["met:Precipitation"], filters=[],
                              period=YEAR, aggregation="sum", record_kind="observation")


def codes(sparql, interp=RD02, idx=IDX):
    return sorted({f.diag.code for f in validate_query(sparql, interp, idx, True)[1]})


# ---------- RD02 ----------

def test_rd02_first_attempt_is_accepted():
    """Estava certa (o mesmo valor do oráculo, 3196,0 mm) e passa a não ser recusada."""
    assert codes(RD02_FIRST_ATTEMPT) == []


def test_rd02_reversed_relation_is_rejected_before_it_becomes_a_false_empty_answer():
    got = codes(RD02_AFTER_REPAIR_REVERSED)
    assert "RELATION_DIRECTION" in got


@pytest.mark.parametrize("triple,side", [
    ("st:SBBE met:reportOf ?r", "sujeito"),            # o certo é ?r met:reportOf st:SBBE
    ("st:SBBE met:inReport ?r", "sujeito"),            # inReport tem como sujeito a observação
    ("?r sosa:hosts st:SBBE", "objeto"),               # hosts tem como objeto o sensor
])
def test_a_constant_station_in_the_wrong_position_is_rejected(triple, side):
    q = f"SELECT ?r WHERE {{ {triple} . }}"
    assert "RELATION_DIRECTION" in codes(q), side


@pytest.mark.parametrize("triple", [
    "?r met:reportOf st:SBBE",                          # o jeito certo
    "st:SBBE sosa:hosts ?s",
    "st:SBBE met:stationCode ?c",
    "?site met:siteOf st:SBBE",
    "st:SBBE rdfs:label ?l",
])
def test_the_right_use_of_a_constant_station_is_not_flagged(triple):
    q = f"SELECT * WHERE {{ {triple} . }}"
    assert "RELATION_DIRECTION" not in codes(q)


def test_no_reference_query_trips_the_new_rules():
    """Falso positivo custa abstenção: nenhuma consulta de referência (reais e sintéticas) pode cair nas regras novas."""
    new = {"RELATION_DIRECTION", "BIND_REUSES_VARIABLE"}
    for suite in SUITES:
        for q in load_questions(None, suite):
            if "sparql" not in q:
                continue
            if suite == "real":
                stations = tuple(set(re.findall(r"st:([A-Z0-9]+)", q["sparql"])))
                idx = real_index(stations or ("SBGR",))
            else:
                idx = OntologyIndex.load()
            _, findings = validate_query(q["sparql"], None, idx, True)
            assert not new & {f.diag.code for f in findings}, (suite, q["id"])


# ---------- RD03 ----------

def test_rd03_bind_reusing_a_name_is_rejected_before_execution():
    interp = PipelineInterpretation(entities=[], properties=["met:AirTemperature"], filters=[], period=None, aggregation="max",
                                    record_kind="observation")
    assert "BIND_REUSES_VARIABLE" in codes(RD03_BIND_REUSES_NAME, interp)


def test_bind_with_a_fresh_name_is_not_flagged():
    q = ("SELECT ?x WHERE { ?station met:stationCode ?code . BIND(?code AS ?x) }")
    assert "BIND_REUSES_VARIABLE" not in codes(q)


# ---------- RD07 (rodada 2): "Manaus" virou st:SBEG por conhecimento externo ----------

from kgqa.contract import Status  # noqa: E402
from kgqa.store import LocalRdflibBackend  # noqa: E402
from pipeline.llm import ScriptedLLM  # noqa: E402
from pipeline.orchestrator import run_pipeline  # noqa: E402
from pipeline.validators import validate_interpretation  # noqa: E402

RD07_Q = "Quanto choveu em Manaus em 2020?"
Y2020 = {"start": "2020-01-01", "end": "2020-12-31", "tz": "-03:00", "inclusive_end": True}


def precip(entity):
    return PipelineInterpretation(entities=[entity], properties=["met:Precipitation"], filters=[], period=Y2020,
                                  aggregation="sum", record_kind="observation")


def interp_codes(interp, question, idx):
    return sorted({f.diag.code for f in validate_interpretation(interp, idx, question)})


def test_a_city_name_mapped_to_an_icao_code_is_not_accepted():
    """A ontologia só tem o código ICAO como rótulo: 'Manaus' não pode virar SBEG com o conhecimento do modelo."""
    idx = real_index(("SBEG", "SBGR"))
    assert "ENTITY_TEXT_MISMATCH" in interp_codes(precip({"text": "Manaus", "iri": "st:SBEG"}), RD07_Q, idx)


@pytest.mark.parametrize("entity,question", [
    ({"text": "SBEG", "iri": "st:SBEG"}, "Quanto choveu em SBEG em 2020?"),            # o código está na pergunta
    ({"text": "sbeg", "iri": "st:SBEG"}, "Quanto choveu em SBEG em 2020?"),            # caixa não importa
])
def test_a_station_named_by_its_code_is_accepted(entity, question):
    assert "ENTITY_TEXT_MISMATCH" not in interp_codes(precip(entity), question, real_index(("SBEG",)))


def test_a_partial_label_still_counts_for_stations_with_names():
    """No grafo sintético o rótulo é 'Estação Serra Azul': 'Serra Azul' é parte dele e continua válido."""
    syn = OntologyIndex.load()
    i = PipelineInterpretation(entities=[{"text": "Serra Azul", "iri": "st:EST-A"}], properties=["met:AirTemperature"], filters=[],
                               period=None, aggregation="avg", record_kind="observation")
    assert "ENTITY_TEXT_MISMATCH" not in interp_codes(i, "Qual a temperatura média na Serra Azul?", syn)


def test_a_model_that_insists_on_the_city_ends_unsupported_and_never_generates_a_query():
    import json
    bad = {"status": "ok", "properties": ["met:Precipitation"], "entities": [{"text": "Manaus", "iri": "st:SBEG"}], "filters": [],
           "period": Y2020, "aggregation": "sum", "record_kind": "observation"}
    llm = ScriptedLLM({"interpret": [json.dumps(bad)], "generate": [json.dumps({"sparql": "SELECT * WHERE { ?s ?p ?o }"})], "answer": ["x"]})
    res = run_pipeline(RD07_Q, llm, LocalRdflibBackend(), real_index(("SBEG", "SBGR")), timeout_s=20, prompts_version="v4")
    assert res.response.status == Status.UNSUPPORTED
    assert "ENTITY_TEXT_MISMATCH" in {d.code for d in res.response.diagnostics}
    assert not [c for c in llm.calls if c["stage"] == "generate"]                  # nenhuma consulta foi gerada nem executada
