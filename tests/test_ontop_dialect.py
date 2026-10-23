"""P-36: consultas que o rdflib aceita e o Ontop recusa (HTTP 400). Já eram duas: `BIND` com nome em uso (D-43) e esta.

Medido no grafo real (RF06 do v4): `SELECT (YEAR(?t) AS ?ano) … GROUP BY (YEAR(?t))` dá "non-aggregate expression … not allowed in
projection when using GROUP BY". O jeito aceito é dar nome à chave no GROUP BY e projetar o nome. Sem LLM; a checagem contra o motor
real roda só com o Ontop no ar.
"""
from pathlib import Path

import pytest

from eval.run_reference import SUITES, load_questions
from kgqa.store import PREFIXES, OntopBackend
from pipeline.compiler import compile_structured
from pipeline.query_facts import extract
from pipeline.validators import PipelineInterpretation, validate_query
from pipeline.vocab import STATION_NS, OntologyIndex
from tests.test_real_pipeline import needs_ontop

ROOT = Path(__file__).resolve().parent.parent

# a consulta EXATA que o v4 escreveu para RF06 e o Ontop recusou
RF06_V4 = """SELECT (YEAR(?t) AS ?ano) (COUNT(?obs) AS ?n) WHERE { st:SBCF sosa:hosts ?sensor . ?obs a met:InstantaneousObservation ; sosa:madeBySensor ?sensor ; sosa:observedProperty met:PressureQNH ; sosa:phenomenonTime/time:inXSDDateTime ?t ; sosa:hasResult ?value . ?value qudt:numericValue ?numericValue ; qudt:unit unit:HectoPA . } GROUP BY (YEAR(?t))"""

WITH_ALIAS = """SELECT ?ano (COUNT(?obs) AS ?n) WHERE { st:SBCF sosa:hosts ?sensor . ?obs a met:InstantaneousObservation ; sosa:madeBySensor ?sensor ; sosa:observedProperty met:PressureQNH ; met:localDate ?d . } GROUP BY (YEAR(?d) AS ?ano)"""


def flagged(sparql):
    return extract(PREFIXES + sparql).grouped_expr_projections


def codes(sparql, idx):
    return {f.diag.code for f in validate_query(sparql, None, idx, True)[1]}


def real_index():
    idx = OntologyIndex.load().with_profile_from_obda(ROOT / "mapping" / "met.obda")
    idx.entities = {STATION_NS + "SBCF": ["SBCF"]}
    return idx


def test_the_exact_query_that_failed_is_flagged_before_execution():
    assert flagged(RF06_V4) == ["ano"]
    assert "GROUPED_PROJECTION_EXPR" in codes(RF06_V4, real_index())


@pytest.mark.parametrize("name,sparql", [
    ("chave com nome no GROUP BY", WITH_ALIAS),
    ("agregado composto", "SELECT ?s (SUM(?v)/COUNT(?v) AS ?m) WHERE { ?s met:stationCode ?v } GROUP BY ?s"),
    ("função sobre um agregado", "SELECT (ROUND(AVG(?v)) AS ?m) WHERE { ?s met:stationCode ?v }"),
    ("variável como chave", "SELECT ?s (COUNT(?v) AS ?n) WHERE { ?s met:stationCode ?v } GROUP BY ?s"),
    ("sem agrupamento", "SELECT (YEAR(?t) AS ?a) WHERE { ?o sosa:phenomenonTime/time:inXSDDateTime ?t }"),
])
def test_the_valid_forms_are_not_flagged(name, sparql):
    assert flagged(sparql) == [], name


def test_no_reference_or_compiled_query_trips_the_rule():
    """Falso positivo custa abstenção: nenhuma consulta de referência (reais, sintéticas, conjunto novo) pode cair nela."""
    for suite in SUITES:
        for q in load_questions(None, suite):
            if "sparql" in q:
                assert flagged(q["sparql"]) == [], (suite, q["id"])


def test_every_compiled_structured_shape_avoids_the_problem():
    from tests.test_structured import FRESH_SHAPES, IDX, SHAPES
    for name, interp in [*((k, v[1]) for k, v in SHAPES.items()), *FRESH_SHAPES.items()]:
        assert flagged(compile_structured(interp, IDX)) == [], name


@needs_ontop
def test_the_rule_matches_what_the_real_engine_does():
    backend = OntopBackend()
    bad = backend.select(PREFIXES + RF06_V4, timeout_s=60)
    good = backend.select(PREFIXES + WITH_ALIAS, timeout_s=60)
    assert not bad.ok and "non-aggregate expression" in str(bad.error)          # o motor realmente recusa…
    assert good.ok and len(good.results["results"]["bindings"]) == 10          # …e executa a forma com nome (10 anos de pressão em SBCF)
