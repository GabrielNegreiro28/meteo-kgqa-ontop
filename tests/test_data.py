"""Dados sintéticos: reprodutibilidade, cardinalidades planejadas e validação SHACL."""
import hashlib

from pyshacl import validate
from rdflib import XSD, Graph, Literal, Namespace, URIRef

import generate
from conftest import ROOT

QUDT = Namespace("http://qudt.org/schema/qudt/")


def _canonical(g: Graph) -> str:
    lines = sorted(l for l in g.serialize(format="nt").splitlines() if l.strip())
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def test_generation_is_reproducible():
    assert _canonical(generate.build_graph(generate.gen_records())) == \
           _canonical(generate.build_graph(generate.gen_records()))


def test_file_on_disk_matches_generator():
    on_disk = Graph().parse(ROOT / "data" / "synthetic.nt")
    assert _canonical(on_disk) == _canonical(generate.build_graph(generate.gen_records()))


def test_planned_cardinalities():
    recs = generate.gen_records()
    # 7 dias x 4 horários x (3+3+2 sensores) = 224, menos 5 ausências planejadas
    assert len(recs) == 219
    assert sum(r.station == "EST-C" and r.prop == "RelativeHumidity" for r in recs) == 0
    assert sum(r.station == "EST-B" and r.prop == "AirTemperature" and r.start.startswith("2026-03-05")
               for r in recs) == 0


def _shapes():
    return Graph().parse(ROOT / "ontology" / "shapes.ttl")


def _data():
    g = Graph().parse(ROOT / "data" / "synthetic.nt")
    g.parse(ROOT / "ontology" / "met.ttl")
    return g


def test_shacl_conforms():
    conforms, _, report = validate(_data(), shacl_graph=_shapes(), inference="none")
    assert conforms, report


def test_shacl_catches_bad_data():
    g = _data()
    r = URIRef("https://example.org/kgqa-met/data/result/EST-A-RH-20260302T0000")
    g.set((r, QUDT.numericValue, Literal("120.0", datatype=XSD.decimal)))   # umidade impossível
    r2 = URIRef("https://example.org/kgqa-met/data/result/EST-A-TEMP-20260302T0000")
    g.remove((r2, QUDT.unit, None))                                          # resultado sem unidade
    conforms, _, report = validate(g, shacl_graph=_shapes(), inference="none")
    assert not conforms
    assert "faixa física" in report
    assert "unit" in report
