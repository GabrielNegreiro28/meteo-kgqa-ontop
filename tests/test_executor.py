"""Executor somente leitura: política, erros, truncamento e timeout."""
import pytest

from kgqa.store import PREFIXES, LocalRdflibBackend

B = LocalRdflibBackend()


@pytest.mark.parametrize("query,kind", [
    ("INSERT DATA { <urn:a> <urn:b> <urn:c> }", "policy"),
    ("DELETE WHERE { ?s ?p ?o }", "policy"),
    ("SELECT * WHERE { SERVICE <http://example.org/sparql> { ?s ?p ?o } }", "policy"),
    ("SELECT * FROM <http://example.org/g> WHERE { ?s ?p ?o }", "policy"),
    ("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }", "policy"),
    ("SELEC ?s WHERE { ?s ?p ?o }", "syntax"),
    ("SELECT ?s WHERE { ?s met:naoExiste ?o }", "syntax"),   # prefixo não declarado
])
def test_rejections(query, kind):
    r = B.select(query, timeout_s=5)
    assert not r.ok and r.error_kind == kind


def test_literal_containing_keyword_is_allowed():
    r = B.select(PREFIXES + 'SELECT ?s WHERE { ?s rdfs:label "INSERT DELETE"@pt }', timeout_s=10)
    assert r.ok and r.results["results"]["bindings"] == []


def test_truncation_flag():
    r = B.select("SELECT * WHERE { ?s ?p ?o }", timeout_s=10, max_rows=5)
    assert r.ok and r.truncated and len(r.results["results"]["bindings"]) == 5


def test_timeout_kills_query():
    r = B.select("SELECT (COUNT(*) AS ?n) WHERE { ?a ?b ?c . ?d ?e ?f . ?g ?h ?i }", timeout_s=2)
    assert not r.ok and r.error_kind == "timeout"


def test_types_are_preserved():
    iri = "<https://example.org/kgqa-met/data/result/EST-A-TEMP-20260304T1200>"
    r = B.select(PREFIXES + f"SELECT ?v WHERE {{ {iri} qudt:numericValue ?v }}", timeout_s=10)
    b = r.results["results"]["bindings"][0]["v"]
    assert b == {"type": "literal", "value": "30.0", "datatype": "http://www.w3.org/2001/XMLSchema#decimal"}
