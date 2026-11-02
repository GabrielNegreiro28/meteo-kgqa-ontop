"""Conformância: o que o MAPEAMENTO realmente produz é coerente com os axiomas da ontologia?

A ontologia pode estar consistente e o grafo violá-la (foi o caso do Codex C08: `met:localDate` em observação e em boletim, com
domínio declarado só na observação). Raciocinar só sobre os axiomas não pega isso, porque sem indivíduos nada contradiz nada.
Aqui amostramos indivíduos do grafo real (Ontop), com todas as suas propriedades e os tipos dos vizinhos, e o raciocinador
confere se (visão completa + amostra) continua consistente.

Só leitura: consultas SELECT com LIMIT pequeno. Nenhum dado real é gravado em arquivo versionado.
"""
from __future__ import annotations

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

from metqa.execution.store import PREFIXES

MET = "https://example.org/kgqa-met/ontology#"
SOSA = "http://www.w3.org/ns/sosa/"
TIME = "http://www.w3.org/2006/time#"
QUDT = "http://qudt.org/schema/qudt/"

# Classes que o mapeamento produz (mapping/met.obda). Um teste confere que esta lista cobre todas as que o .obda declara.
MAPPED_CLASSES = [MET + "WeatherStation", MET + "Site", MET + "WeatherReport", MET + "InstantaneousObservation",
                  MET + "AccumulatedObservation", MET + "CloudLayerObservation", SOSA + "Sensor", TIME + "Interval", TIME + "Instant",
                  QUDT + "QuantityValue", MET + "CloudLayerResult"]


def _term(b: dict):
    if b["type"] == "uri":
        return URIRef(b["value"])
    dt = b.get("datatype")
    return Literal(b["value"], datatype=URIRef(dt)) if dt else Literal(b["value"], lang=b.get("xml:lang"))


def _select(backend, query: str, timeout_s: float = 60):
    ex = backend.select(PREFIXES + query, timeout_s=timeout_s, max_rows=2000)
    if not ex.ok:
        raise RuntimeError(ex.error)
    return ex.results["results"]["bindings"]


def sample_abox(backend, classes=MAPPED_CLASSES, per_class: int = 3) -> tuple[Graph, dict[str, int]]:
    """Amostra `per_class` indivíduos de cada classe, com TODAS as propriedades e o tipo de cada vizinho que é um nó."""
    g = Graph()
    found: dict[str, int] = {}
    for cls in classes:
        subjects = [b["s"]["value"] for b in _select(backend, f"SELECT ?s WHERE {{ ?s a <{cls}> }} LIMIT {per_class}")]
        found[cls] = len(subjects)
        for s in subjects:
            for b in _select(backend, f"SELECT ?p ?o WHERE {{ <{s}> ?p ?o }}"):
                p, o = URIRef(b["p"]["value"]), _term(b["o"])
                g.add((URIRef(s), p, o))
                if isinstance(o, URIRef) and p != RDF.type:
                    for t in _select(backend, f"SELECT ?t WHERE {{ <{o}> a ?t }}"):
                        g.add((o, RDF.type, URIRef(t["t"]["value"])))
    return g, found
