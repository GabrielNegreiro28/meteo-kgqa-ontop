"""Checagem prévia pelo próprio motor (Ontop /ontop/reformulate) e procedência da resposta (SQL gerado + PROV-O).

Origem: três incidentes em que o `rdflib` do validador aceitou o que o Ontop recusa (BIND com nome em uso, GROUP BY sem alias, relação
escrita ao contrário), cada um tratado por uma regra própria. O motor já sabe dizer as duas coisas: recusa ao traduzir, e `EMPTY`
quando a consulta é vazia por construção. Os testes com motor simulado rodam sempre; os com o Ontop real, só com ele no ar.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import PROV

from kgqa.contract import CONTRACT_VERSION, Provenance, QueryResponse, Status
from kgqa.store import PREFIXES, LocalRdflibBackend, OntopBackend, Reformulation, parse_reformulation
from pipeline.llm import ScriptedLLM
from pipeline.orchestrator import run_pipeline
from pipeline.provenance import build_prov, llm_model_of, prov_turtle
from pipeline.vocab import OntologyIndex
from tests.test_pipeline import BACKEND, D04_INTERP, D04_Q, INDEX, QS, J, good_answer_d04
from tests.test_real_pipeline import needs_ontop

OK_BODY = """ans1(n)
CONSTRUCT [n] [n/RDF(BIGINTToTEXT(v0),xsd:integer)]
   NATIVE [v0]
SELECT COUNT(*) AS "v0"
FROM "station" v1
"""
EMPTY_BODY = "ans1(o)\nEMPTY [o]\n"


# ---------- leitura do plano ----------

def test_parse_reformulation_extracts_the_sql_or_the_emptiness():
    assert parse_reformulation(OK_BODY) == ("ok", 'SELECT COUNT(*) AS "v0"\nFROM "station" v1')
    assert parse_reformulation(EMPTY_BODY) == ("empty", None)
    assert parse_reformulation("ans1(x)\nCONSTRUCT [x] []\n") == ("ok", None)           # sem bloco nativo: sem SQL, mas aceita


# ---------- fluxo com um motor simulado (cada veredito) ----------

class FakeEngine:
    """Backend de teste: executa no rdflib e responde à reformulação como o motor responderia, na ordem dada."""
    source_id = "fake-engine"

    def __init__(self, verdicts):
        self.verdicts, self.calls = list(verdicts), []

    def select(self, *a, **k):
        return BACKEND.select(*a, **k)

    def reformulate(self, query, timeout_s=15.0):
        self.calls.append(query)
        v = self.verdicts.pop(0) if len(self.verdicts) > 1 else self.verdicts[0]
        return v


def script(sparqls):
    return {"interpret": [json.dumps(D04_INTERP)], "generate": [J(sparql=q) for q in sparqls], "answer": [J(answer=good_answer_d04())]}


def run(engine, sparqls=None):
    llm = ScriptedLLM(script(sparqls or [QS["D04"]["sparql"]]))
    return run_pipeline(D04_Q, llm, engine, INDEX, timeout_s=20), llm


def test_an_engine_that_accepts_the_query_leaves_the_flow_unchanged_and_records_the_sql():
    engine = FakeEngine([Reformulation("ok", sql='SELECT 1 FROM "t"', plan=OK_BODY)])
    res, _ = run(engine)
    assert res.response.status == Status.ANSWERED and len(engine.calls) == 2      # a consulta como escrita e a que o executor ENVIA (com LIMIT)
    assert "LIMIT" not in engine.calls[0].split("GROUP BY")[-1] and engine.calls[1].rstrip().endswith("LIMIT 1001")
    assert next(t for t in res.trace if t["event"] == "engine_check")["status"] == "ok"
    p = res.response.provenance
    assert p.generated_sql == 'SELECT 1 FROM "t"' and p.engine == "ontop-reformulate"
    assert p.executed_sparql == engine.calls[1] and p.complete                 # o SQL registrado é o da consulta enviada, não o da anterior ao LIMIT
    assert {"mapping", "cleaning", "structure", "code"} <= set(p.versions)      # identidade dos artefatos que dão significado à resposta
    assert p.versions["prompts"] == "v1" and p.versions["contract"] == CONTRACT_VERSION


def test_a_query_proved_empty_by_the_engine_is_repaired_instead_of_answered_as_no_records():
    engine = FakeEngine([Reformulation("empty", plan=EMPTY_BODY), Reformulation("ok", sql="SELECT 1")])
    res, llm = run(engine, [QS["D04"]["sparql"], QS["D04"]["sparql"]])
    assert [c["stage"] for c in llm.calls].count("generate") == 2                      # o veredito do motor entrou no laço de reparo
    assert "EMPTY_BY_CONSTRUCTION" in next(c for c in llm.calls if "recusada" in c["user"])["user"]
    assert res.response.status == Status.ANSWERED


def test_a_query_the_engine_rejects_is_never_executed_and_ends_rejected():
    engine = FakeEngine([Reformulation("rejected", detail="o motor recusou a consulta (HTTP 500)")])
    res, _ = run(engine)
    assert res.response.status == Status.REJECTED
    assert "ENGINE_REJECTED" in {d.code for d in res.response.diagnostics}
    assert res.response.results is None


def test_an_engine_without_a_verdict_does_not_block_anything():
    engine = FakeEngine([Reformulation("unavailable", detail="Ontop sem --dev")])
    res, _ = run(engine)
    assert res.response.status == Status.ANSWERED
    assert res.response.provenance.generated_sql is None                                 # sem veredito, sem SQL: nada é inventado


def test_a_backend_without_reformulation_is_skipped_silently():
    res = run_pipeline(D04_Q, ScriptedLLM(script([QS["D04"]["sparql"]])), BACKEND, INDEX, timeout_s=20)
    assert res.response.status == Status.ANSWERED
    assert next(t for t in res.trace if t["event"] == "engine_check")["status"] == "n/a"          # a trilha diz que NÃO houve checagem


def test_the_engine_message_given_back_to_the_llm_is_short_and_has_no_internal_detail():
    engine = FakeEngine([Reformulation("rejected", detail="x" * 5000 + " http://10.0.0.1:8080/secret C:/segredo"), Reformulation("ok", sql="SELECT 1")])
    _, llm = run(engine, [QS["D04"]["sparql"], QS["D04"]["sparql"]])
    feedback = next(c for c in llm.calls if "ENGINE_REJECTED" in c["user"])["user"]
    assert len(feedback) < 4000 and "secret" not in feedback.split("ENGINE_REJECTED")[1][:400]


# ---------- procedência em PROV-O ----------

def response(**kw):
    r = QueryResponse(request_id="r1", status=Status.ANSWERED, question='Quanto choveu em "SBGR"?\nlinha 2',
                      sparql='SELECT ?x WHERE { ?x a "q\\"" }', provenance=Provenance(source_id="kg:teste"))
    for k, v in kw.items():
        setattr(r, k, v)
    return r


T0 = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def test_provenance_is_valid_prov_o_and_round_trips_hostile_text():
    r = response()
    r.provenance.generated_sql, r.provenance.engine = 'SELECT "a"\nFROM "t"', "ontop-reformulate"
    r.provenance.versions = {"prompts": "v6", "ontology": "abc123", "model": "gpt-x", "semantic_layer": None}
    g = Graph().parse(data=prov_turtle(r, T0), format="turtle")
    run = URIRef("https://example.org/kgqa-met/run/r1")
    assert (URIRef(f"{run}/answer"), PROV.wasGeneratedBy, URIRef(f"{run}/activity")) in g
    assert (URIRef(f"{run}/activity"), PROV.used, URIRef(f"{run}/sparql")) in g
    assert (URIRef(f"{run}/sql"), PROV.wasDerivedFrom, URIRef(f"{run}/sparql")) in g
    texts = {str(o) for _, _, o in g.triples((None, None, None)) if isinstance(o, Literal)}
    assert 'Quanto choveu em "SBGR"?\nlinha 2' in texts and 'SELECT "a"\nFROM "t"' in texts          # nada se perde no escape
    assert "gpt-x" in texts and "v6" in texts and "abc123" in texts


def test_provenance_of_a_refusal_has_no_query_and_no_sql():
    r = response(sparql=None, status=Status.UNSUPPORTED)
    g = build_prov(r, T0)
    assert not list(g.triples((None, PROV.used, URIRef("https://example.org/kgqa-met/run/r1/sparql"))))
    assert not [t for t in g if str(t[0]).endswith("/sql")]


def test_the_pipeline_attaches_parseable_prov_to_every_answer_including_refusals():
    ok = run_pipeline(D04_Q, ScriptedLLM(script([QS["D04"]["sparql"]])), BACKEND, INDEX, timeout_s=20)
    refused = run_pipeline("", ScriptedLLM({}), BACKEND, INDEX)
    for res in (ok, refused):
        g = Graph().parse(data=res.response.provenance.prov_turtle, format="turtle")
        assert len(g) > 5


def test_llm_model_is_found_through_the_wrappers():
    class Inner: model = "gpt-6-luna"
    class Wrap: client = Inner()
    class Outer: client = Wrap()
    assert llm_model_of(Outer()) == "gpt-6-luna" and llm_model_of(object()) is None


def test_a_failure_while_building_provenance_never_breaks_the_answer(monkeypatch):
    import pipeline.orchestrator as o
    monkeypatch.setattr(o, "prov_turtle", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    res = run_pipeline(D04_Q, ScriptedLLM(script([QS["D04"]["sparql"]])), BACKEND, INDEX, timeout_s=20)
    assert res.response.status == Status.ANSWERED


# ---------- motor real ----------

REVERSED = "SELECT ?o WHERE { st:SBBE met:reportOf ?r . ?o met:inReport ?r }"
BIND_REUSE = "SELECT ?station ?n WHERE { ?station met:stationCode ?c . BIND(?c AS ?station) }"
GROUP_NO_ALIAS = "SELECT (YEAR(?t) AS ?ano) (COUNT(?o) AS ?n) WHERE { ?o sosa:phenomenonTime/time:inXSDDateTime ?t } GROUP BY (YEAR(?t))"
GROUP_ALIAS = "SELECT ?ano (COUNT(?o) AS ?n) WHERE { ?o met:localDate ?d } GROUP BY (YEAR(?d) AS ?ano)"


@needs_ontop
@pytest.mark.parametrize("name,query,expected", [
    ("relação ao contrário", REVERSED, "empty"),
    ("BIND com nome em uso", BIND_REUSE, "rejected"),
    ("GROUP BY sem alias", GROUP_NO_ALIAS, "rejected"),
    ("GROUP BY com alias", GROUP_ALIAS, "ok"),
])
def test_the_real_engine_gives_the_verdicts_the_rules_used_to_guess(name, query, expected):
    r = OntopBackend().reformulate(PREFIXES + query)
    if r.status == "unavailable":
        pytest.skip("Ontop sem --dev")
    assert r.status == expected, (name, r)
    if expected == "ok":
        assert "GROUP BY" in r.sql and r.elapsed_ms < 2000


@needs_ontop
def test_the_real_engine_returns_the_generated_sql_and_the_pipeline_records_it():
    backend = OntopBackend()
    if backend.reformulate(PREFIXES + GROUP_ALIAS).status == "unavailable":
        pytest.skip("Ontop sem --dev")
    idx = OntologyIndex.from_ontop(backend)
    interp = {"status": "ok", "properties": ["met:Precipitation"], "entities": [{"text": "SBBE", "iri": "st:SBBE"}], "filters": [],
              "period": {"start": "2019-01-01", "end": "2019-12-31", "tz": "-03:00", "inclusive_end": True}, "aggregation": "sum",
              "record_kind": "observation"}
    sparql = next(q for q in __import__("yaml").safe_load((Path(__file__).resolve().parent.parent / "eval" / "questions_real.yaml").read_text(encoding="utf-8"))["questions"] if q["id"] == "RD02")["sparql"]
    llm = ScriptedLLM({"interpret": [json.dumps(interp)], "generate": [J(sparql=sparql)], "answer": ["Em SBBE, em 2019, choveu 3196 mm em 8760 medições."]})
    res = run_pipeline("Quanto choveu em SBBE em 2019?", llm, backend, idx, timeout_s=60, prompts_version="v4")
    assert res.response.status == Status.ANSWERED
    assert "obs_precip" in res.response.provenance.generated_sql and res.response.provenance.engine == "ontop-reformulate"
    g = Graph().parse(data=res.response.provenance.prov_turtle, format="turtle")
    assert any(str(s).endswith("/sql") for s, _, _ in g)
