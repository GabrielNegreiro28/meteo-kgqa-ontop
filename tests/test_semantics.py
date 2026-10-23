"""Camada semântica consultiva (EvoOntology) ligada à ontologia formal: geração da v0, fachada, porta de validação, MCP.

Sem LLM e sem Ontop. As mutações mostram que a porta barra o que o documento da arquitetura proíbe (§7.4, regra 4):
IRI inexistente ou ausente, categoria BFO inventada, IRI disputado e Restrição que contradiz a ontologia.
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from evoontology.ontology.store import SemanticStore
from rdflib import OWL, RDF, Graph, URIRef

from semantics.build import BFO_TTL, MET_TTL, STRUCTURE_TTL, build_records, build_v0
from semantics.facade import GroundedLayer
from semantics.gate import validate_candidate
from semantics.mcp_server import GroundedMCPServer

ROOT = Path(__file__).resolve().parent.parent
MET = "https://example.org/kgqa-met/ontology#"


@pytest.fixture(scope="module")
def ws(tmp_path_factory):
    path = tmp_path_factory.mktemp("evo")
    build_v0(path)
    return path


def candidate(ws, name, mutate):
    """Grava uma cópia mutada da v0 como versão-candidata e devolve o resultado da porta."""
    _, records = SemanticStore.load_records(ws, version="ontology_v0")
    records = copy.deepcopy(records)
    mutate(records)
    SemanticStore.save_version(ws, name, records)
    return validate_candidate(ws, name)


def term(records, local):
    return next(t for t in records["terms"] if t["id"] == f"term.{local}")


# ---------- geração da v0 ----------

def test_build_is_deterministic():
    assert build_records() == build_records()


def test_every_formal_class_and_observable_property_becomes_a_term():
    g = Graph().parse(MET_TTL)
    expected = {str(s) for s in g.subjects(RDF.type, OWL.Class) if str(s).startswith(MET)}
    expected |= {str(s) for s in g.subjects(RDF.type, URIRef("http://www.w3.org/ns/sosa/ObservableProperty"))}
    got = {t["iri"] for t in build_records()["terms"]}
    assert expected <= got


def test_every_class_and_observable_property_has_a_bfo_category_from_the_alignment_file():
    for t in build_records()["terms"]:
        if t["type"] in ("class", "observable_property"):
            assert t["bfo_category"] and t["bfo_iri"], t["id"]
        else:
            assert t["bfo_category"] is None, f"{t['id']}: propriedade não leva categoria BFO"


def test_published_v0_passes_the_gate(ws):
    assert validate_candidate(ws, "ontology_v0") == {"passed": True, "version": "ontology_v0", "errors": []}


def test_evidence_is_provenance_of_the_ontology_only():
    """Perguntas de eval/ não podem virar Evidência: o conjunto que avalia a evolução ficaria contaminado."""
    ev = build_records()["evidence"]
    assert ev and {e["source"] for e in ev} == {"ontology/met.ttl"}
    assert all(e["query"].startswith("https://example.org/kgqa-met/evidence/ev.") for e in ev)      # só o IRI PROV-O da Evidência (C12), nunca texto de pergunta


def test_constraints_mirror_the_formal_aggregations():
    from pipeline.vocab import OntologyIndex
    cons = {c["id"]: c for c in build_records()["constraints"]}
    formal = sorted(OntologyIndex.load().properties[MET + "AirTemperature"].aggregations)
    assert "sum" not in formal                      # premissa do teste: grandeza instantânea não admite soma
    assert cons["con.AirTemperature.allowed_aggregations"]["description"].endswith(f"{', '.join(formal)}.")
    assert "con.Precipitation.period_containment" in cons


def test_ontop_never_sees_the_alignment():
    """met-bfo.ttl é só da camada semântica: o mapeamento do Ontop continua usando apenas met.ttl."""
    assert "bfoCategory" not in MET_TTL.read_text(encoding="utf-8")
    assert "bfoCategory" not in STRUCTURE_TTL.read_text(encoding="utf-8")
    assert BFO_TTL.exists()


# ---------- fachada ----------

def test_resolve_returns_formal_iri_and_bfo_category(ws):
    r = GroundedLayer.open(ws).resolve(["temperatura do ar"])["results"][0]
    assert r["status"] == "resolved"
    t = r["term"]
    assert t["iri"] == MET + "AirTemperature"
    assert t["bfo_category"] == "quality" and t["bfo_iri"].endswith("BFO_0000019")
    assert t["formal_status"] == "bound"
    assert any(c["id"].endswith("allowed_aggregations") for c in r["constraints"])


def test_resolve_ignores_accents_unlike_the_core(ws):
    layer = GroundedLayer.open(ws)
    a = layer.resolve(["estação"])["results"][0]["term"]["iri"]
    b = layer.resolve(["estacao"])["results"][0]["term"]["iri"]
    assert a == b == MET + "WeatherStation"


def test_unknown_phrase_is_unresolved_and_carries_no_iri(ws):
    r = GroundedLayer.open(ws).resolve(["choveu"])["results"][0]
    assert r["status"] == "unresolved" and "term" not in r


def test_browse_carries_the_binding(ws):
    items = GroundedLayer.open(ws).browse("bulbo úmido")["items"]
    assert items and items[0]["iri"] == MET + "WetBulbTemperature" and items[0]["formal_status"] == "bound"


def test_term_without_iri_is_flagged_unbound(ws):
    def drop(records):
        term(records, "AirTemperature")["iri"] = None
    _, records = SemanticStore.load_records(ws, version="ontology_v0")
    records = copy.deepcopy(records)
    drop(records)
    SemanticStore.save_version(ws, "v0-unbound", records)
    t = GroundedLayer.open(ws, "v0-unbound").resolve(["temperatura do ar"])["results"][0]["term"]
    assert t["formal_status"] == "unbound"


def test_explicit_version_does_not_touch_active(ws):
    before = SemanticStore.active_version(ws)
    GroundedLayer.open(ws, "ontology_v0")
    assert SemanticStore.active_version(ws) == before


# ---------- porta de validação: mutações ----------

def test_gate_rejects_missing_iri(ws):
    r = candidate(ws, "m-no-iri", lambda rec: term(rec, "AirTemperature").update(iri=None))
    assert not r["passed"] and any("sem IRI" in e for e in r["errors"])


def test_gate_rejects_invented_iri(ws):
    r = candidate(ws, "m-bad-iri", lambda rec: term(rec, "AirTemperature").update(iri=MET + "TemperaturaInventada"))
    assert not r["passed"] and any("não existe na ontologia formal" in e for e in r["errors"])


def test_gate_rejects_invented_bfo_category(ws):
    r = candidate(ws, "m-bad-bfo", lambda rec: term(rec, "WeatherStation").update(bfo_category="process"))
    assert not r["passed"] and any("nunca inventada" in e for e in r["errors"])


def test_gate_rejects_missing_bfo_on_a_class(ws):
    r = candidate(ws, "m-no-bfo", lambda rec: term(rec, "WeatherStation").update(bfo_category=None, bfo_iri=None))
    assert not r["passed"] and any("falta a categoria BFO" in e for e in r["errors"])


def test_gate_rejects_two_terms_on_the_same_iri(ws):
    r = candidate(ws, "m-dup", lambda rec: term(rec, "RelativeHumidity").update(iri=MET + "AirTemperature"))
    assert not r["passed"] and any("já é de" in e for e in r["errors"])


def test_gate_rejects_a_sum_constraint_on_an_instantaneous_quantity(ws):
    def mutate(rec):
        c = next(c for c in rec["constraints"] if c["id"] == "con.AirTemperature.allowed_aggregations")
        c["description"] = "Agregações permitidas para temperatura do ar: avg, sum."
    r = candidate(ws, "m-sum", mutate)
    assert not r["passed"] and any("não estão entre as permitidas" in e for e in r["errors"])


def test_gate_rejects_a_wrong_unit(ws):
    def mutate(rec):
        c = next(c for c in rec["constraints"] if c["id"] == "con.AirTemperature.unit")
        c["description"] = "Unidade canônica de temperatura do ar: K."
    r = candidate(ws, "m-unit", mutate)
    assert not r["passed"] and any("unidade diverge" in e for e in r["errors"])


def test_gate_accepts_a_legitimate_advisory_patch(ws):
    """O caso que o EvoOntology existe para resolver: um sinônimo novo ('choveu' -> precipitação) passa na porta."""
    r = candidate(ws, "ok-synonym", lambda rec: term(rec, "Precipitation")["aliases"].append("choveu"))
    assert r["passed"], r["errors"]
    assert GroundedLayer.open(ws, "ok-synonym").resolve(["choveu"])["results"][0]["term"]["iri"] == MET + "Precipitation"


# ---------- MCP ----------

def call(server, name, **arguments):
    out = server.dispatch("tools/call", {"name": name, "arguments": arguments})
    return json.loads(out["content"][0]["text"]), out["isError"]


def test_mcp_resolve_returns_binding(ws):
    result, err = call(GroundedMCPServer(str(ws)), "resolve_semantics", mentions=["precipitação"])
    assert not err and result["results"][0]["term"]["iri"] == MET + "Precipitation"


def test_mcp_ignores_caller_chosen_workspace(ws, tmp_path):
    """O servidor serve UM workspace: o chamador não escolhe o caminho a ler."""
    result, err = call(GroundedMCPServer(str(ws)), "resolve_semantics", mentions=["precipitação"], workspace=str(tmp_path))
    assert not err and result["results"][0]["status"] == "resolved"


def test_mcp_stdio_roundtrip(ws):
    reqs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "resolve_semantics", "arguments": {"mentions": ["umidade"]}}}]
    p = subprocess.run([sys.executable, "-m", "semantics.mcp_server", "--store", str(ws)], cwd=ROOT, text=True, encoding="utf-8",
                       input="\n".join(json.dumps(r) for r in reqs) + "\n", capture_output=True, timeout=60)
    lines = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
    assert [l["id"] for l in lines] == [1, 2]
    body = json.loads(lines[1]["result"]["content"][0]["text"])
    assert body["results"][0]["term"]["iri"] == MET + "RelativeHumidity"


def test_build_never_overwrites_a_published_version(ws):
    before = (ws / "versions" / "ontology_v0" / "terms.json").read_bytes()
    with pytest.raises(ValueError, match="não se sobrescrevem"):
        build_v0(ws)
    assert (ws / "versions" / "ontology_v0" / "terms.json").read_bytes() == before
