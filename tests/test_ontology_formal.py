"""Verificação FORMAL da ontologia (documento da arquitetura, §6.4 e §6.6).

Em Python puro (roda em qualquer lugar): imports fixados, colocação sob a BFO, consistência do registro de categorias com os
axiomas, visão QL (só axiomas QL, sem nós em branco, regeneração idêntica ao arquivo versionado), domínio por união.
Com ROBOT + Java (WSL): perfil OWL 2 DL e QL pelo validador, consistência e satisfatibilidade pelo HermiT, testes de mutação que
provam que o raciocinador PEGA os defeitos que importam, e conformância do que o mapeamento produz no grafo real (Ontop).
"""
import hashlib
import re
import tempfile
from pathlib import Path

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from ontology import build_views as bv
from ontology import formal_check as fc
from tests.test_real_pipeline import needs_ontop

ROOT = Path(__file__).resolve().parent.parent
ONT = ROOT / "ontology"
MET = "https://example.org/kgqa-met/ontology#"
OBO = "http://purl.obolibrary.org/obo/"
needs_robot = pytest.mark.skipif(not fc.available(), reason="ROBOT/Java ausentes (instale com ontology/imports/fetch.sh)")


@pytest.fixture(scope="module")
def full():
    return bv.build_dl()


@pytest.fixture(scope="module")
def ql(full):
    return bv.build_ql(full)


def _is_obo(x) -> bool:
    return isinstance(x, URIRef) and str(x).startswith(OBO)


def _ancestors(g: Graph, c) -> set:
    seen, stack = set(), [c]
    while stack:
        x = stack.pop()
        for p in g.objects(x, RDFS.subClassOf):
            if isinstance(p, URIRef) and p not in seen:
                seen.add(p)
                stack.append(p)
    return seen


def _domain_classes(g: Graph) -> list[URIRef]:
    """Classes declaradas pelos módulos do projeto (met, sosa, time, qudt, skos), sem BFO/IAO."""
    return sorted({s for s in g.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef) and not _is_obo(s)}, key=str)


# ---------------------------------------------------------------------------------------------------------------- imports
def test_imports_are_pinned_by_sha256():
    text = (ONT / "imports" / "SOURCES.md").read_text(encoding="utf-8")
    for name in ("bfo-core.owl", "iao-module.owl", "iao-terms.txt"):
        digest = hashlib.sha256((ONT / "imports" / name).read_bytes()).hexdigest()
        assert digest in text, f"{name}: SHA-256 {digest} não está em imports/SOURCES.md (arquivo mudou sem registro)"


def test_bfo_is_the_2020_release_unaltered_and_has_the_relations_we_use():
    g = Graph().parse(ONT / "imports" / "bfo-core.owl")
    assert (URIRef("http://purl.obolibrary.org/obo/bfo.owl"), OWL.versionIRI,
            URIRef("http://purl.obolibrary.org/obo/bfo/2020/bfo-core.owl")) in g
    for n in ("0000015", "0000019", "0000040", "0000008", "0000038", "0000148", "0000002", "0000057", "0000199"):
        assert (URIRef(OBO + "BFO_" + n), RDFS.label, None) in g, n
    for n in ("0000030", "0000109"):
        assert (URIRef(OBO + "IAO_" + n), RDFS.label, None) in Graph().parse(ONT / "imports" / "iao-module.owl"), n


# ---------------------------------------------------------------------------------------------------------------- colocação
def test_every_domain_class_has_one_placement_under_bfo_or_iao(full):
    """§6.4 regra 3: cada classe tem UMA colocação. Aqui: no máximo um pai OBO afirmado e pelo menos um ancestral OBO."""
    unplaced, ambiguous = [], []
    for c in _domain_classes(full):
        direct = [p for p in full.objects(c, RDFS.subClassOf) if _is_obo(p)]
        if len(direct) > 1:
            ambiguous.append((str(c), [str(p) for p in direct]))
        if not any(_is_obo(a) for a in _ancestors(full, c)):
            unplaced.append(str(c))
    assert not ambiguous, f"classe com mais de um pai BFO/IAO afirmado: {ambiguous}"
    assert not unplaced, f"classes sem colocação sob a BFO/IAO (devolver à discussão, §6.4): {unplaced}"


def test_the_bfo_categories_registered_for_the_pipeline_follow_from_the_axioms(full):
    """met:bfoCategory (o que o Termo copia) tem de ser uma categoria da qual a entidade é descendente, e para uma grandeza
    a categoria da classe de qualidade que ela denota."""
    cat = URIRef(MET + "bfoCategory")
    den = URIRef(MET + "denotesQuality")
    for s, c in sorted(full.subject_objects(cat), key=str):
        assert full.value(c, SKOS.notation) is not None, f"{c} sem skos:notation"
        if (s, RDF.type, URIRef("http://www.w3.org/ns/sosa/ObservableProperty")) in full:
            quality = full.value(s, den)
            assert quality is not None, f"{s}: grandeza sem met:denotesQuality"
            assert c in _ancestors(full, quality), f"{s}: categoria {c} não é ancestral da qualidade {quality}"
        else:
            assert c in _ancestors(full, s) or c == s, f"{s}: categoria registrada {c} não decorre dos axiomas"


def test_every_observable_property_denotes_exactly_one_quality(full):
    obs = URIRef("http://www.w3.org/ns/sosa/ObservableProperty")
    for s in full.subjects(RDF.type, obs):
        qs = list(full.objects(s, URIRef(MET + "denotesQuality")))
        assert len(qs) == 1, s
        assert (qs[0], RDFS.subClassOf, URIRef(OBO + "BFO_0000019")) in full


def test_observation_is_a_process_and_reports_forecasts_are_information_not_processes(full):
    obs, rep, fc_ = URIRef("http://www.w3.org/ns/sosa/Observation"), URIRef(MET + "WeatherReport"), URIRef(MET + "Forecast")
    proc, ice = URIRef(OBO + "BFO_0000015"), URIRef(OBO + "IAO_0000030")
    assert proc in _ancestors(full, obs) and ice not in _ancestors(full, obs)
    assert ice in _ancestors(full, rep) and proc not in _ancestors(full, rep)
    assert ice in _ancestors(full, fc_) and proc not in _ancestors(full, fc_)


# ---------------------------------------------------------------------------------------------------------------- visão completa
def test_alternative_domain_becomes_a_union_in_the_full_view(full):
    ld = URIRef(MET + "localDate")
    doms = list(full.objects(ld, RDFS.domain))
    assert len(doms) == 1 and isinstance(doms[0], BNode), "localDate deve ter UM domínio, uma união"
    from rdflib.collection import Collection
    members = set(Collection(full, full.value(doms[0], OWL.unionOf)))
    assert members == {URIRef("http://www.w3.org/ns/sosa/Observation"), URIRef(MET + "WeatherReport")}


# ---------------------------------------------------------------------------------------------------------------- visão QL
def test_ql_view_has_no_blank_nodes_and_only_ql_axioms(ql):
    assert not [t for t in ql if any(isinstance(x, BNode) for x in t)]
    allowed = {RDF.type, RDFS.subClassOf, OWL.disjointWith, RDFS.subPropertyOf, OWL.inverseOf, OWL.equivalentClass,
               OWL.equivalentProperty, OWL.propertyDisjointWith, RDFS.domain, RDFS.range, RDFS.label}
    assert {p for _, p, _ in ql} <= allowed
    assert not [t for t in ql if t[1] == RDFS.range and str(t[2]).endswith("#date")], "xsd:date não é do perfil QL"


def test_ql_view_keeps_the_hierarchies_the_pipeline_relies_on(ql):
    sub = lambda a, b: (URIRef(a), RDFS.subClassOf, URIRef(b)) in ql
    assert sub(MET + "InstantaneousObservation", "http://www.w3.org/ns/sosa/Observation")
    assert sub("http://www.w3.org/ns/sosa/Observation", OBO + "BFO_0000015")
    assert (URIRef(MET + "InstantaneousObservation"), OWL.disjointWith, URIRef(MET + "AccumulatedObservation")) in ql
    assert (URIRef("http://www.w3.org/ns/sosa/hasFeatureOfInterest"), RDFS.subPropertyOf, URIRef(OBO + "BFO_0000057")) in ql


def test_committed_views_are_exactly_what_the_generator_produces(ql):
    for name, graph in (("met-ql.ttl", ql), ("met-ontop.ttl", bv.build_ontop(ql))):
        committed = (ONT / "generated" / name).read_text(encoding="utf-8")
        assert bv.serialize(graph) == committed, f"ontology/generated/{name} está defasado: rode `python -m ontology.build_views`"


def test_the_ontop_view_drops_only_domains_and_ranges(ql):
    ontop = bv.build_ontop(ql)
    assert {p for _, p, _ in ql} - {p for _, p, _ in ontop} == {RDFS.domain, RDFS.range}
    assert len(ontop) < len(ql)
    assert (URIRef("http://www.w3.org/ns/sosa/Observation"), RDFS.subClassOf, URIRef(OBO + "BFO_0000015")) in ontop


# ---------------------------------------------------------------------------------------------------------------- mapeamento
def test_the_list_of_mapped_classes_covers_every_class_the_obda_produces():
    from ontology.conformance import MAPPED_CLASSES
    ns = {"met": MET, "sosa": "http://www.w3.org/ns/sosa/", "time": "http://www.w3.org/2006/time#", "qudt": "http://qudt.org/schema/qudt/"}
    text = (ROOT / "mapping" / "met.obda").read_text(encoding="utf-8")
    produced = {ns[p] + n for p, n in re.findall(r"\ba (met|sosa|time|qudt):(\w+)", text)}
    assert produced <= set(MAPPED_CLASSES), sorted(produced - set(MAPPED_CLASSES))


def test_every_predicate_and_class_in_the_mapping_is_declared_in_the_ontology(full):
    ns = {"met": MET, "sosa": "http://www.w3.org/ns/sosa/", "time": "http://www.w3.org/2006/time#", "qudt": "http://qudt.org/schema/qudt/",
          "rdfs": str(RDFS), "xsd": "http://www.w3.org/2001/XMLSchema#"}
    text = (ROOT / "mapping" / "met.obda").read_text(encoding="utf-8")
    targets = "\n".join(l for l in text.splitlines() if l.startswith("target"))
    used = {ns[p] + n for p, n in re.findall(r"\b(met|sosa|time|qudt|rdfs):(\w+)", targets)}
    declared = {s for s, _, _ in full.triples((None, RDF.type, None)) if isinstance(s, URIRef)}
    declared |= {URIRef(str(RDFS) + "label")}
    assert not sorted(u for u in used if URIRef(u) not in declared), "termos do mapeamento sem declaração na ontologia"


# ---------------------------------------------------------------------------------------------------------------- ROBOT + HermiT
@needs_robot
def test_full_view_is_owl2_dl_and_consistent_with_no_unsatisfiable_class(full, tmp_path):
    f = tmp_path / "met-dl.ttl"
    f.write_text(full.serialize(format="turtle"), encoding="utf-8")
    ok, report = fc.validate_profile("DL", f)
    assert ok, report[:2000]
    ok, text = fc.reason(f)
    assert ok, text[-1500:]


@needs_robot
def test_ql_view_is_owl2_ql_and_consistent():
    ok, report = fc.validate_profile("QL", ONT / "generated" / "met-ql.ttl")
    assert ok, report[:2000]
    ok, text = fc.reason(ONT / "generated" / "met-ql.ttl")
    assert ok, text[-1500:]


def _with(full: Graph, tmp_path, extra: str, name: str) -> Path:
    f = tmp_path / name
    f.write_text(full.serialize(format="turtle") + "\n" + extra, encoding="utf-8")
    return f


PREFIXES = ("@prefix met: <" + MET + "> .\n@prefix sosa: <http://www.w3.org/ns/sosa/> .\n@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n")


@needs_robot
@pytest.mark.parametrize("name,extra", [
    ("forecast_as_observation", "met:Forecast rdfs:subClassOf sosa:Observation .\n"),
    ("report_and_observation_at_once", "met:Bad rdfs:subClassOf met:WeatherReport , sosa:Observation .\n"),
    ("process_and_information_at_once", "met:Bad2 rdfs:subClassOf sosa:Observation , met:AggregationFunction .\n"),
    ("station_as_information", "met:WeatherStation rdfs:subClassOf met:WeatherReport .\n"),
    ("old_localdate_domain_with_a_report", "met:localDate rdfs:domain sosa:Observation .\nmet:r1 a met:WeatherReport ; met:localDate \"2020-01-01\"^^xsd:date .\n"),
])
def test_the_reasoner_catches_the_defects_that_matter(full, tmp_path, name, extra):
    """Teste de mutação: cada defeito injetado TEM de ser recusado. Prova que o raciocinador está de fato verificando algo."""
    ok, text = fc.reason(_with(full, tmp_path, PREFIXES + extra, name + ".ttl"))
    assert not ok, f"o raciocinador deixou passar: {name}"
    assert "unsatisfiable" in text or "inconsistent" in text


@needs_robot
@needs_ontop
def test_what_the_mapping_produces_in_the_real_graph_is_consistent_with_the_axioms(full, tmp_path):
    from metqa.execution.store import OntopBackend
    from ontology.conformance import sample_abox
    sample, found = sample_abox(OntopBackend(), per_class=3)
    assert all(n > 0 for n in found.values()), found
    # UM arquivo só: o ROBOT interpreta cada arquivo sozinho, e uma propriedade não declarada NAQUELE arquivo vira anotação (ignorada pelo
    # raciocinador). Com a amostra num arquivo à parte, o teste passaria sem verificar nada.
    both = Graph()
    for t in (*full, *sample):
        both.add(t)
    f = tmp_path / "dl-with-sample.ttl"
    f.write_text(both.serialize(format="turtle"), encoding="utf-8")
    ok, text = fc.reason(f)
    assert ok, text[-1500:]
    # controle negativo: com o defeito antigo (domínio só na observação, sem a união), a amostra TEM de contradizer a ontologia,
    # pois tem boletins com localDate (Codex C08). Se isto passar, o teste acima não prova nada.
    ld = URIRef(MET + "localDate")
    for d in list(both.objects(ld, RDFS.domain)):
        both.remove((ld, RDFS.domain, d))
    both.add((ld, RDFS.domain, URIRef("http://www.w3.org/ns/sosa/Observation")))
    badf = tmp_path / "dl-bad.ttl"
    badf.write_text(both.serialize(format="turtle"), encoding="utf-8")
    ok2, _ = fc.reason(badf)
    assert not ok2, "a amostra real deveria contradizer o domínio sem união (Codex C08)"
