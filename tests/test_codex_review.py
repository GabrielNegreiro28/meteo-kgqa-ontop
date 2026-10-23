"""Achados da avaliação independente do Codex (docs/AVALIACAO_CODEX.md) que viraram correção. Cada teste reproduz a falha original.

Os números C01..C20 são os da tabela daquele relatório. As reproduções do Codex usaram o grafo real; aqui, o grafo sintético e o validador.
"""
import copy
import json

import pytest

from kgqa.verify import result_status
from kgqa.contract import Status
from pipeline.grounding import check_answer, render_fallback
from pipeline.llm import ScriptedLLM
from pipeline.orchestrator import run_pipeline
from pipeline.validators import PipelineInterpretation as I, validate_interpretation, validate_query
from pipeline.vocab import STATION_NS
from tests.test_pipeline import BACKEND, D04_INTERP, D04_Q, INDEX, J

PERIOD_2019 = {"start": "2019-01-01", "end": "2019-12-31", "tz": "-03:00", "inclusive_end": True}
SBGR = {"text": "SBGR", "iri": "st:SBGR"}


def codes(findings):
    return {f.diag.code for f in findings}


# ---------- C01: a consulta tem de dizer o que a interpretação diz, não só citar os mesmos termos ----------

def _query(filter_expr, agg="AVG(?v)", extra=""):
    return f"""SELECT ({agg} AS ?value) (COUNT(?v) AS ?n) WHERE {{
  ?obs a met:InstantaneousObservation ; sosa:observedProperty met:AirTemperature ; sosa:hasResult/qudt:numericValue ?v .
  ?obs sosa:phenomenonTime/time:inXSDDateTime ?t . {extra}
  FILTER({filter_expr})
}}"""


T_AND = '?t >= "2019-01-01T00:00:00-03:00"^^xsd:dateTime && ?t < "2020-01-01T00:00:00-03:00"^^xsd:dateTime'
INTERP_2019 = I(properties=["met:AirTemperature"], entities=[], period=PERIOD_2019, aggregation="avg", filters=[], record_kind="observation")


def _l2l3(q):
    return codes(validate_query(q, INTERP_2019, INDEX)[1])


def test_conjunctive_period_still_passes():
    assert _l2l3(_query(T_AND)) == set()


@pytest.mark.parametrize("expr", [T_AND.replace("&&", "||"), f"!({T_AND})", f"({T_AND}) || ?v > 100",
                                  T_AND + " && !EXISTS { ?obs met:inReport ?r }"])
def test_or_not_exists_in_a_filter_are_refused(expr):
    """`a >= x || b < y` amplia o período (medido no grafo real: média de 2019 virava 2016–2025) e passa na conferência de operadores."""
    assert "FILTER_NOT_CONJUNCTIVE" in _l2l3(_query(expr))


def test_a_filter_inside_optional_is_refused():
    q = _query("?v > -100", extra=f"OPTIONAL {{ ?obs sosa:resultTime ?rt . FILTER({T_AND}) }}")
    assert "FILTER_NOT_CONJUNCTIVE" in _l2l3(q)


@pytest.mark.parametrize("agg", ["AVG(?v * 0)", "AVG(?v + 1)", "SUM(1)", "MAX(?t)", "AVG(DISTINCT ?obs)"])
def test_aggregate_over_anything_but_the_measured_value_is_refused(agg):
    """`AVG(?v * 0)` devolve 0 com n correto: um número que parece resposta."""
    assert "AGGREGATE_ARGUMENT" in _l2l3(_query(T_AND, agg))


def test_aggregating_the_measured_value_distinct_or_not_is_accepted():
    assert _l2l3(_query(T_AND, "AVG(DISTINCT ?v)")) == set()


# ---------- C02: restrição que a pergunta traz e a interpretação deixou cair ----------

def _interp(**kw):
    base = dict(properties=["met:AirTemperature"], entities=[SBGR], period=PERIOD_2019, aggregation="avg", filters=[], record_kind="observation")
    return I(**{**base, **kw})


def _l4(q, interp):
    return codes(validate_interpretation(interp, INDEX_WITH_SBGR, q, (), True))


INDEX_WITH_SBGR = copy.copy(INDEX)                      # cópia: o índice compartilhado dos outros testes não ganha SBGR
INDEX_WITH_SBGR.entities = {**INDEX.entities, STATION_NS + "SBGR": ["SBGR"]}


def test_a_named_month_must_become_that_month():
    assert "PERIOD_MONTH_MISMATCH" in _l4("Qual a temperatura média de SBGR em janeiro de 2019?", _interp())      # ano inteiro
    jan = {**PERIOD_2019, "end": "2019-01-31"}
    assert _l4("Qual a temperatura média de SBGR em janeiro de 2019?", _interp(period=jan)) == set()
    fev = {**PERIOD_2019, "start": "2019-02-01", "end": "2019-02-28"}
    assert "PERIOD_MONTH_MISMATCH" in _l4("Qual a temperatura média de SBGR em janeiro de 2019?", _interp(period=fev))
    assert "PERIOD_MONTH_MISMATCH" in _l4("Qual a temperatura média de SBGR em janeiro de 2019?", _interp(period={**PERIOD_2019, "end": "2019-01-15"}))


def test_a_month_without_period_is_not_all_time():
    assert "PERIOD_OMITTED" in _l4("Qual a temperatura média de SBGR em janeiro?", _interp(period=None))


def test_a_year_only_question_needs_the_whole_year():
    q = "Qual a temperatura média de SBGR em 2019?"
    assert _l4(q, _interp()) == set()
    assert "PERIOD_PARTIAL_YEAR" in _l4(q, _interp(period={**PERIOD_2019, "end": "2019-01-31"}))
    assert "PERIOD_PARTIAL_YEAR" in _l4(q, _interp(period={**PERIOD_2019, "start": "2019-07-01"}))


def test_sub_year_cues_do_not_trigger_the_whole_year_rule():
    jul = {**PERIOD_2019, "start": "2019-07-01"}
    assert "PERIOD_PARTIAL_YEAR" not in _l4("Qual a temperatura média de SBGR no segundo semestre de 2019?", _interp(period=jul))


def test_a_threshold_in_the_question_needs_a_filter():
    q = "Qual a temperatura média de SBGR acima de 30 graus em 2019?"
    assert "FILTER_OMITTED" in _l4(q, _interp())
    assert "FILTER_OMITTED" not in _l4(q, _interp(filters=[{"op": ">", "value": 30}]))
    assert "FILTER_OMITTED" not in _l4("Qual a temperatura média de SBGR em 2019?", _interp())


def test_day_part_is_not_silently_the_whole_day():
    for q in ("Qual a temperatura média de SBGR durante o dia em 2019?", "Qual a temperatura média de SBGR à noite em 2019?"):
        assert "DAYPART_UNSUPPORTED" in _l4(q, _interp()), q


# ---------- C03: ASK ----------

def test_ask_true_is_an_answer_not_an_absence():
    assert result_status({"head": {}, "boolean": True})[0] == Status.ANSWERED
    assert result_status({"head": {}, "boolean": False})[0] == Status.ANSWERED          # "Não" também é resposta
    assert render_fallback(Status.ANSWERED, {"head": {}, "boolean": False}) == "Não."


def test_ask_through_the_whole_pipeline_says_yes():
    ask = "ASK { ?obs a met:InstantaneousObservation ; sosa:observedProperty met:AirTemperature . }"
    interp = {**D04_INTERP, "period": None, "aggregation": None}
    llm = ScriptedLLM({"interpret": [json.dumps(interp)], "generate": [J(sparql=ask)], "answer": [J(answer="Não há registros.")]})
    r = run_pipeline("Há leituras de temperatura do ar?", llm, BACKEND, INDEX, prompts_version="v4").response
    assert r.results["boolean"] is True
    assert r.status == Status.ANSWERED
    assert r.answer_text.startswith("Sim")


# ---------- C04: unidade errada no texto ----------

UNITS = {"value": "http://qudt.org/vocab/unit/DEG_C"}
RESULTS = {"head": {"vars": ["value", "n"]}, "results": {"bindings": [
    {"value": {"type": "literal", "value": "20.4147"}, "n": {"type": "literal", "value": "9473"}}]}}


def _units(text):
    return codes(check_answer(text, "Qual a temperatura média?", RESULTS, Status.ANSWERED, False, UNITS, {}, set()))


def test_a_number_with_the_wrong_unit_is_an_error():
    for wrong in ("20.4147 K", "20.4147 kelvin", "20.4147 °F", "20.4147 F"):
        assert "WRONG_UNIT" in _units(f"A temperatura média foi {wrong} (9473 leituras)."), wrong


def test_the_right_unit_and_unrelated_k_words_pass():
    assert "WRONG_UNIT" not in _units("A temperatura média foi 20.4147 °C (9473 leituras).")
    assert "WRONG_UNIT" not in _units("A temperatura média foi 20.4147 °C (9473 leituras), em 2019 no Km 5.")


def test_the_pressure_unit_hpa_is_not_taken_for_pa():
    units = {"value": "http://qudt.org/vocab/unit/HectoPA"}
    res = {"head": {"vars": ["value"]}, "results": {"bindings": [{"value": {"type": "literal", "value": "1013.2"}}]}}
    assert "WRONG_UNIT" not in codes(check_answer("A pressão foi 1013.2 hPa.", "Qual a pressão?", res, Status.ANSWERED, False, units, {}, set()))
    assert "WRONG_UNIT" in codes(check_answer("A pressão foi 1013.2 Pa.", "Qual a pressão?", res, Status.ANSWERED, False, units, {}, set()))


# ---------- C08: met:localDate também é propriedade do boletim ----------

def test_report_local_date_is_not_a_type_clash():
    """O mapeamento emite met:localDate em WeatherReport, mas o domínio declarado era só Observation (disjunta de WeatherReport)."""
    q = "SELECT ?d WHERE { ?r a met:WeatherReport ; met:reportOf ?s ; met:localDate ?d } LIMIT 1"
    for order in (q, "SELECT ?d WHERE { ?r met:localDate ?d ; a met:WeatherReport ; met:reportOf ?s } LIMIT 1"):
        found = codes(validate_query(order, None, INDEX)[1])
        assert not found & {"TYPE_CLASH", "DISJOINT_TYPES"}, found


def test_observation_local_date_still_types_the_subject():
    q = "SELECT ?d WHERE { ?o met:localDate ?d ; a met:WeatherStation } LIMIT 1"      # estação com localDate: continua incompatível
    assert codes(validate_query(q, None, INDEX)[1]) & {"TYPE_CLASH", "DISJOINT_TYPES"}


# ---------- C16: o teto é reservado antes da chamada ----------

class _Priced:
    """Cliente com preço: US$ 10 por milhão de tokens de entrada e de saída; a chamada de verdade custa US$ 0,001."""
    price_in = price_out = 10.0

    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    def complete(self, stage, system, user, max_tokens, **kw):
        from pipeline.llm import LLMResponse
        self.calls += 1
        if self.fail:
            raise RuntimeError("rede caiu depois do envio")
        return LLMResponse(text="{}", cost_usd=0.001, usage={"in": 10, "out": 10})


def test_ledger_refuses_a_call_that_could_cross_the_cap(tmp_path):
    """Antes: com 0,39 gastos e teto 0,40, uma chamada de 0,05 era aceita e o total chegava a 0,44."""
    from pipeline.ledger import Ledger, LedgerLLM
    from pipeline.llm import BudgetExceeded
    ledger = Ledger(tmp_path / "spend.jsonl")
    ledger.record(0.39, run="antes")
    client = _Priced()
    llm = LedgerLLM(client, ledger, base_cap_usd=0.40, run="t")
    with pytest.raises(BudgetExceeded):
        llm.complete("x", "s" * 100, "u" * 100, max_tokens=5000)          # pode custar até ~0,05
    assert client.calls == 0 and ledger.total() == 0.39                   # nada foi chamado nem anotado


def test_ledger_reconciles_the_reservation_with_the_real_cost(tmp_path):
    from pipeline.ledger import Ledger, LedgerLLM
    ledger = Ledger(tmp_path / "spend.jsonl")
    llm = LedgerLLM(_Priced(), ledger, base_cap_usd=1.0, run="t")
    llm.complete("x", "s", "u", max_tokens=1000)
    assert ledger.total() == pytest.approx(0.001, abs=1e-6)
    assert llm.spent_usd == pytest.approx(0.001)


def test_ledger_records_a_failed_call_after_sending(tmp_path):
    from pipeline.ledger import Ledger, LedgerLLM
    ledger = Ledger(tmp_path / "spend.jsonl")
    llm = LedgerLLM(_Priced(fail=True), ledger, base_cap_usd=1.0, run="t")
    with pytest.raises(RuntimeError):
        llm.complete("x", "s" * 250, "u" * 250, max_tokens=1000)
    assert 0 < ledger.total() < 0.01                                      # a entrada pode ter sido cobrada: fica no registro


def test_ledger_lock_is_released_and_a_stale_lock_is_broken(tmp_path):
    import os, time
    from pipeline.ledger import Ledger
    ledger = Ledger(tmp_path / "spend.jsonl")
    ledger.reserve(0.01, 1.0, run="a")
    lock = tmp_path / "spend.jsonl.lock"
    assert not lock.exists()
    lock.write_text("")
    os.utime(lock, (time.time() - 120, time.time() - 120))                # trava deixada por processo morto
    ledger.reserve(0.01, 1.0, run="b")
    assert ledger.total() == pytest.approx(0.02)


# ---------- C18: comentário depois do LIMIT ----------

def test_cap_rows_keeps_the_query_valid_with_a_trailing_comment():
    from kgqa.store import cap_rows, check_policy, PREFIXES
    for q in ("SELECT ?s WHERE { ?s ?p ?o } LIMIT 2 # comentário", "SELECT ?s WHERE { ?s ?p ?o } LIMIT 2\n# fim",
              "SELECT ?s WHERE { ?s ?p ?o } # nada", "SELECT ?s WHERE { ?s ?p ?o } LIMIT 500 # grande"):
        out = cap_rows(q, 10)
        check_policy(PREFIXES + out)                                      # não levanta SyntaxError
        assert out.upper().count("LIMIT") == 1, out
    assert cap_rows("SELECT ?s WHERE { ?s ?p ?o } LIMIT 2 # c", 10).endswith("LIMIT 2 # c")
    assert cap_rows("SELECT ?s WHERE { ?s ?p ?o } LIMIT 500 # c", 10).endswith("LIMIT 11")


# ---------- C09: sensor travado só em horas consecutivas ----------

def _qc(rows):
    """Roda o controle de qualidade num DuckDB em memória com `rows` = [(sigla, 'AAAA-MM-DD HH:MM', mm)] de chuva; devolve (quarentena Q2, restantes)."""
    duckdb = pytest.importorskip("duckdb")
    from ingest import transform
    con = duckdb.connect()
    con.execute("CREATE SCHEMA clean")
    con.execute("CREATE TABLE clean.quarantine (src_file VARCHAR, src_row BIGINT, sigla VARCHAR, t_local TIMESTAMP, col VARCHAR, value VARCHAR, reason VARCHAR)")
    for t in ("obs_precip", "obs_precip_duration", "obs_air_temp", "obs_dew_point", "obs_qnh", "obs_wind_gust", "obs_wind_speed"):
        con.execute(f"CREATE TABLE clean.{t} (sigla VARCHAR, t_local TIMESTAMP, value DOUBLE, seq SMALLINT, src_row BIGINT, runway VARCHAR)")
    for i, (sigla, t, v) in enumerate(rows):
        con.execute("INSERT INTO clean.obs_precip VALUES (?, ?, ?, 0, ?, NULL)", [sigla, t, v, i])
    out = transform.quality_control(con)
    return out["Q2"], con.execute("SELECT COUNT(*) FROM clean.obs_precip").fetchone()[0]


def test_stuck_sensor_needs_consecutive_hours():
    """Antes: três leituras iguais de 25 mm em 01/01/2019, 01/06/2019 e 01/01/2020 eram marcadas como sensor travado."""
    sparse = [("SBXX", "2019-01-01 00:00", 25.0), ("SBXX", "2019-06-01 00:00", 25.0), ("SBXX", "2020-01-01 00:00", 25.0)]
    moved, left = _qc(sparse)
    assert moved == 0 and left == 3


def test_stuck_sensor_three_hours_in_a_row_is_still_caught():
    rows = [("SBXX", f"2019-01-01 0{h}:00", 25.0) for h in range(3)]
    moved, left = _qc(rows)
    assert moved == 3 and left == 0


def test_a_gap_inside_the_run_breaks_it_and_low_values_are_never_stuck():
    gap = [("SBXX", "2019-01-01 00:00", 25.0), ("SBXX", "2019-01-01 01:00", 25.0), ("SBXX", "2019-01-01 03:00", 25.0)]
    assert _qc(gap)[0] == 0                                                   # 00h, 01h, 03h: só duas horas seguidas
    low = [("SBXX", f"2019-01-01 0{h}:00", 5.0) for h in range(4)]
    assert _qc(low)[0] == 0                                                   # abaixo de 20 mm


# ---------- C13: procedência da consulta enviada e dos artefatos; falha não é silenciosa ----------

def test_artifact_versions_fingerprint_mapping_cleaning_and_code():
    from pipeline.provenance import artifact_versions
    v = artifact_versions()
    assert {"mapping", "cleaning", "structure", "bfo_alignment", "code"} <= set(v)
    assert all(len(x) == 12 for x in v.values())


def test_a_failure_while_building_provenance_is_flagged_not_swallowed(monkeypatch):
    import pipeline.orchestrator as orch
    monkeypatch.setattr(orch, "prov_turtle", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    llm = ScriptedLLM({"interpret": [json.dumps(D04_INTERP)], "generate": [J(sparql=__import__("tests.test_pipeline", fromlist=["QS"]).QS["D04"]["sparql"])],
                       "answer": [J(answer="x")]})
    r = run_pipeline(D04_Q, llm, BACKEND, INDEX, prompts_version="v4").response
    assert r.status in (Status.ANSWERED, Status.NO_RESULTS) and r.provenance.complete is False
    assert "PROVENANCE_INCOMPLETE" in {d.code for d in r.diagnostics}


# ---------- C12: Evidência do EvoOntology ligada a PROV-O (§7.4 r.3) ----------

def test_every_evidence_resolves_to_a_prov_entity_with_activity_and_source():
    from rdflib import RDF, URIRef
    from rdflib.namespace import PROV
    from semantics.build import build_records, evidence_iri, evidence_prov
    records = build_records()
    g = evidence_prov(records)
    assert len(records["evidence"]) == 42
    for ev in records["evidence"]:
        e = URIRef(ev["query"])
        assert ev["query"] == evidence_iri(ev["id"])
        assert (e, RDF.type, PROV.Entity) in g
        assert g.value(e, PROV.wasGeneratedBy) is not None and g.value(e, PROV.wasDerivedFrom) is not None
    activity = g.value(URIRef(records["evidence"][0]["query"]), PROV.wasGeneratedBy)
    assert any(True for _ in g.objects(activity, PROV.used))                      # a atividade usou arquivos de ontologia com impressão


# ---------- C14: a checagem do motor é consultiva por padrão, e o modo estrito a exige ----------

def _engine_run(verdict, **kw):
    from tests.test_engine_check import FakeEngine, run
    from kgqa.store import Reformulation
    engine = FakeEngine([verdict])
    llm_and_res = run(engine) if not kw else None
    if kw:
        from tests.test_engine_check import script
        from tests.test_pipeline import D04_Q
        llm = ScriptedLLM(script([__import__("tests.test_pipeline", fromlist=["QS"]).QS["D04"]["sparql"]]))
        return run_pipeline(D04_Q, llm, engine, INDEX, timeout_s=20, **kw)
    return llm_and_res[0]


def test_engine_down_is_said_out_loud_but_does_not_block_by_default():
    from kgqa.store import Reformulation
    res = _engine_run(Reformulation("unavailable", detail="sem --dev"))
    assert res.response.status == Status.ANSWERED
    assert "ENGINE_CHECK_UNAVAILABLE" in {d.code for d in res.response.diagnostics}


def test_strict_mode_refuses_to_execute_without_the_engine_check():
    from kgqa.store import Reformulation
    res = _engine_run(Reformulation("unavailable", detail="sem --dev"), require_engine=True)
    assert res.response.status == Status.EXECUTION_ERROR and res.response.results is None
    assert "ENGINE_CHECK_REQUIRED" in {d.code for d in res.response.diagnostics}


def test_strict_mode_runs_normally_when_the_engine_accepts():
    from kgqa.store import Reformulation
    res = _engine_run(Reformulation("ok", sql="SELECT 1"), require_engine=True)
    assert res.response.status == Status.ANSWERED
