"""Índice da ontologia construído a partir do grafo REAL (Ontop), em vez do `synthetic.nt`.

Os testes de falha usam um backend de mentira e rodam sempre. Os que dependem do Ontop e do DuckDB reais são pulados quando eles
não estão no ar (mesma regra de tests/test_real_pipeline.py).
"""
import json
from datetime import date

import pytest
import yaml

from kgqa.store import ExecResult, OntopBackend
from pipeline.llm import ScriptedLLM
from pipeline.orchestrator import run_pipeline
from pipeline.vocab import MET, SOSA, STATION_NS, OntologyIndex
from tests.test_real_pipeline import needs_duck, needs_ontop

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent


class FakeBackend:
    """Responde como o Ontop responderia; `fail` simula uma consulta que falha."""
    def __init__(self, stations=("SBGR", "SBBE"), fail=None):
        self.stations, self.fail = stations, fail

    def select(self, query, timeout_s=0, max_rows=0):
        if self.fail and self.fail in query:
            return ExecResult(False, "timeout", "estourou")
        if query.startswith("ASK"):
            return ExecResult(True, results={"boolean": True})
        if "WeatherStation" in query:
            return ExecResult(True, results={"results": {"bindings": [
                {"s": {"value": STATION_NS + s}, "l": {"value": s}} for s in self.stations]}})
        return ExecResult(True, results={"results": {"bindings": [
            {"a": {"value": "2016-01-01"}, "b": {"value": "2025-12-31"}}]}})


# ---------- sem Ontop ----------

def test_index_from_a_backend_fills_stations_coverage_and_properties():
    idx = OntologyIndex.from_ontop(FakeBackend())
    assert set(idx.entities) == {STATION_NS + "SBGR", STATION_NS + "SBBE"}
    assert idx.entities[STATION_NS + "SBGR"] == ["SBGR"] and "SBGR" in idx.labels
    assert idx.coverage == (date(2016, 1, 1), date(2025, 12, 31))
    assert idx.properties_with_data == set(idx.properties)


def test_index_ignores_the_synthetic_graph():
    idx = OntologyIndex.from_ontop(FakeBackend(stations=("SBGR",)))
    assert not any(e.endswith(("EST-A", "EST-B", "EST-C")) for e in idx.entities)


@pytest.mark.parametrize("fail", ["WeatherStation", "localDate", "observedProperty"])
def test_index_fails_loudly_when_a_graph_query_fails(fail):
    """Um índice sem estações faria toda estação virar 'desconhecida' e a pipeline recusaria tudo, sem dizer por quê."""
    with pytest.raises(RuntimeError, match="índice real"):
        OntologyIndex.from_ontop(FakeBackend(fail=fail))


def test_index_refuses_a_graph_without_stations():
    with pytest.raises(RuntimeError, match="nenhuma estação"):
        OntologyIndex.from_ontop(FakeBackend(stations=()))


def test_synthetic_index_is_unchanged():
    idx = OntologyIndex.load()
    assert len(idx.entities) == 3                                    # EST-A, EST-B, EST-C
    assert idx.coverage[0] == date(2026, 3, 2) and idx.coverage[1] >= date(2026, 3, 8)


# ---------- com o Ontop real ----------

@needs_ontop
def test_real_index_has_the_real_graph_profile():
    idx = OntologyIndex.from_ontop(OntopBackend())
    assert len(idx.entities) == 178 and STATION_NS + "SBGR" in idx.entities
    assert idx.coverage == (date(2016, 1, 1), date(2025, 12, 31))
    # no grafo sintético vento e pressão não tinham dados (PROPERTY_WITHOUT_DATA); no real têm
    assert {MET + "WindSpeed", MET + "PressureQNH"} <= idx.properties_with_data
    assert idx.link_entities("Quanto choveu em SBBE em 2019?") == {STATION_NS + "SBBE": "SBBE"}


@needs_ontop
@needs_duck
def test_pipeline_answers_a_real_question_end_to_end_and_matches_the_oracle():
    """Pergunta -> interpretação -> consulta -> Ontop -> PostgreSQL -> resposta, com LLM roteirizado (custo zero)."""
    from eval import oracle_real
    q = next(x for x in yaml.safe_load((ROOT / "eval" / "questions_real.yaml").read_text(encoding="utf-8"))["questions"]
             if x["id"] == "RD02")
    interp = {"status": "ok", "properties": ["met:Precipitation"], "entities": [{"text": "SBBE", "iri": "st:SBBE"}],
              "filters": [], "period": {"start": "2019-01-01", "end": "2019-12-31", "tz": "-03:00", "inclusive_end": True},
              "aggregation": "sum", "record_kind": "observation"}
    llm = ScriptedLLM({"interpret": [json.dumps(interp)], "generate": [json.dumps({"sparql": q["sparql"]})],
                       "answer": ["Em SBBE, em 2019, choveu 3196 mm em 8760 medições."]})
    res = run_pipeline(q["question"], llm, OntopBackend(), OntologyIndex.from_ontop(OntopBackend()), timeout_s=60,
                       prompts_version="v4")
    assert res.response.status.value == "answered"
    # a consulta de referência (met:localDate) passa pelas regras e é executada como veio: o compilador de reserva NÃO foi usado
    assert "COMPILED_QUERY" not in {d.code for d in res.response.diagnostics}
    assert res.response.sparql.strip() == q["sparql"].strip()
    row = res.response.results["results"]["bindings"][0]
    (total, n), = oracle_real.expected("RD02")
    assert float(row["total"]["value"]) == pytest.approx(float(total)) and int(row["n"]["value"]) == int(n)
    assert next(t for t in res.trace if t["event"] == "end")["status"] == "answered"


@needs_ontop
@needs_duck
def test_a_per_runway_question_is_answerable_end_to_end_and_matches_the_oracle():
    """RT01: 'cada cabeceira de SBGR'. Antes o contexto não mencionava met:runwayDesignator, então o LLM não tinha como escrevê-la."""
    from eval import oracle_real
    q = next(x for x in yaml.safe_load((ROOT / "eval" / "questions_real.yaml").read_text(encoding="utf-8"))["questions"]
             if x["id"] == "RT01")
    idx = OntologyIndex.from_ontop(OntopBackend())
    interp = {"status": "ok", "properties": ["met:WindSpeed"], "entities": [{"text": "SBGR", "iri": "st:SBGR"}], "filters": [],
              "period": {"start": "2019-01-01", "end": "2019-12-31", "tz": "-03:00", "inclusive_end": True},
              "aggregation": "count", "record_kind": "observation"}
    llm = ScriptedLLM({"interpret": [json.dumps(interp)], "generate": [json.dumps({"sparql": q["sparql"]})], "answer": ["x"]})
    res = run_pipeline(q["question"], llm, OntopBackend(), idx, timeout_s=60, prompts_version="v4")
    assert res.response.status.value == "answered" and "COMPILED_QUERY" not in {d.code for d in res.response.diagnostics}
    got = {b["runway"]["value"]: int(b["n"]["value"]) for b in res.response.results["results"]["bindings"]}
    assert got == {r: int(n) for r, n in oracle_real.expected("RT01")}
    stage2 = next(c for c in llm.calls if c["stage"] == "generate")["user"]
    assert "met:runwayDesignator" in stage2 and "met:localDate" in stage2        # o LLM agora SABE que isso existe
