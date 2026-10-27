"""MVP (`metqa/`) com adaptadores falsos: LLM roteirizado, grafo sintético local. Sem rede, custo zero.

Cobre o contrato de cada estágio e a pipeline linear de ponta a ponta: a consulta só sai do compilador, o tempo só da leitura, toda parada
diz o motivo, e a trilha alimenta a evolução.
"""
import json

import pytest

from eval import oracle
from kgqa.contract import Status
from kgqa.store import LocalRdflibBackend
from metqa.app import MetQA, Settings
from metqa.domain import CanonicalQuery, TimeScope
from metqa.knowledge import DomainCatalog, EvoLexicon, OntologyLexicon
from metqa.planning import compile_query, plan, to_interp
from metqa.presentation.render import num
from metqa.understanding import read_question, split_windows, understand
from pipeline.llm import ScriptedLLM
from pipeline.validators import validate_query
from tests.test_reconcile import IDX as REAL_IDX
from tests.test_reconcile import ir

SYNTH = DomainCatalog.from_ontology()
REAL = DomainCatalog(REAL_IDX)                 # perfil do grafo real (estações, cobertura), sem precisar do Ontop
BACKEND = LocalRdflibBackend()

STATION_AVG = {"status": "ok", "properties": [{"iri": "met:AirTemperature", "span": "temperatura"}], "entities": [],
               "aggregation": {"value": "avg", "span": "média"}, "group_by": [{"dim": "station", "span": "por estação"}]}


def app(*answers, catalog=SYNTH):
    llm = ScriptedLLM({"interpret": [a if isinstance(a, str) else json.dumps(a, ensure_ascii=False) for a in answers]})
    return MetQA(catalog, OntologyLexicon(catalog), llm, BACKEND, Settings(timeout_s=20)), llm


# ---------------- ponta a ponta no grafo sintético ----------------

def test_media_por_estacao_igual_ao_oraculo_com_texto_deterministico():
    qa, llm = app(STATION_AVG)
    res = qa.ask("Qual foi a temperatura média por estação?")
    r = res.response
    assert r.status == Status.ANSWERED, [d.code for d in r.diagnostics]
    assert {c["stage"] for c in llm.calls} == {"interpret"}                 # um LLM só: SPARQL e texto saem de código
    groups = {}
    for o in oracle.sel(oracle.load_obs(), "AirTemperature"):
        groups.setdefault(o["station"], []).append(o["value"])
    for station, values in groups.items():
        assert f"- {station}: {num(oracle.avg(values))} °C (n = {len(values)})" in r.answer_text
    assert "a pergunta não citou estação" not in r.answer_text                # "por estação" não é falta de estação
    assert r.provenance.versions["system"] == "metqa-mvp" and r.provenance.prov_turtle
    assert r.units == {"value": "http://qudt.org/vocab/unit/DEG_C"}
    assert [e["event"] for e in res.trace][-1] == "end"


def test_data_relativa_pede_a_data_sem_gastar_llm():
    qa, llm = app(STATION_AVG)
    r = qa.ask("Qual a temperatura média ontem?").response
    assert r.status == Status.NEEDS_CLARIFICATION and "RELATIVE_DATE" in {d.code for d in r.diagnostics}
    assert llm.calls == []


def test_trecho_errado_tem_uma_rodada_de_reparo_e_depois_responde():
    bad = {**STATION_AVG, "properties": [{"iri": "met:AirTemperature", "span": "calor"}]}
    qa, llm = app(bad, STATION_AVG)
    r = qa.ask("Qual foi a temperatura média por estação?").response
    assert r.status == Status.ANSWERED
    assert len(llm.calls) == 2 and "SPAN_NOT_IN_QUESTION" in llm.calls[1]["user"]


def test_saida_invalida_duas_vezes_falha_fechada():
    qa, _ = app("isto não é json", "nem isto")
    r = qa.ask("Qual foi a temperatura média por estação?").response
    assert r.status == Status.EXECUTION_ERROR and r.results is None


def test_previsao_e_dita_fora_do_alcance():
    qa, _ = app({**STATION_AVG, "record_kind": "forecast"})
    assert qa.ask("Qual a temperatura prevista por estação?").response.status == Status.UNSUPPORTED


def test_estado_ou_cidade_vira_unsupported_pelo_llm():
    qa, _ = app({"status": "unsupported", "reason": "Não há nome de cidade nos dados."})
    r = qa.ask("Qual a temperatura média em Curitiba?").response
    assert r.status == Status.UNSUPPORTED and "cidade" in r.answer_text


def test_periodo_fora_da_cobertura_nao_consulta():
    qa, _ = app(ir("met:AirTemperature", "temperatura", "SBGL", "avg", "média"), catalog=REAL)
    r = qa.ask("Qual foi a temperatura média em SBGL em 2012?").response
    assert r.status == Status.NO_RESULTS and "OUT_OF_COVERAGE" in {d.code for d in r.diagnostics}
    assert r.sparql is None


# ---------------- estágios ----------------

def test_comparacao_de_dois_periodos_vira_duas_subconsultas():
    q = "SBGL esteve mais quente em janeiro de 2016 ou em janeiro de 2025?"
    r = read_question(q)
    assert [label for label, _ in split_windows(r)] == ["janeiro de 2016", "janeiro de 2025"]
    u = understand(q, ir("met:AirTemperature", "quente", "SBGL", "avg", "mais quente"), r, REAL)
    assert not u.findings and u.stop is None
    p = plan(u.parts)
    assert p.combine == "compare" and [x.query.scope.start.year for x in p.parts] == [2016, 2025]
    for part in p.parts:
        sparql = compile_query(part.query, REAL)
        assert sparql and not validate_query(sparql, to_interp(part.query), REAL.index, True)[1]


def test_varias_estacoes_sem_agrupar_viram_um_valor_por_estacao():
    q = "SBGL ou SBGO teve a maior temperatura média em 2020?"
    raw = {**ir("met:AirTemperature", "temperatura", None, "avg", "média"),
           "entities": [{"iri": "st:SBGL", "span": "SBGL"}, {"iri": "st:SBGO", "span": "SBGO"}]}
    u = understand(q, raw, read_question(q), REAL)
    p = plan(u.parts)
    cq = p.parts[0].query
    assert cq.group_by == ["station"] and cq.intent == "series" and any("várias estações" in a for a in cq.assumptions)
    assert compile_query(cq, REAL)


def test_instante_compila_e_passa_nas_regras_de_consulta():
    q = "Qual era a temperatura do ar em SBGL em 10/03/2021 às 15h?"
    u = understand(q, {**ir("met:AirTemperature", "temperatura do ar", "SBGL"), "aggregation": None}, read_question(q), REAL)
    assert not u.findings and u.stop is None, (u.findings, u.stop)
    cq = u.parts[0][1]
    assert cq.intent == "instant"
    sparql = compile_query(cq, REAL)
    assert '"2021-03-10T18:00:00Z"^^xsd:dateTime' in sparql                   # 15h local = 18h UTC
    assert not validate_query(sparql, to_interp(cq), REAL.index, True)[1]


def test_numeros_em_portugues():
    assert num(1234.5) == "1.234,5" and num(25.0) == "25" and num(0.125) == "0,13" and num(None) == "n/d"


def test_escopo_descrito_ao_usuario():
    from datetime import date
    assert TimeScope(date(2024, 1, 1), date(2024, 12, 31), weekdays=(5, 6)).describe() == "de 01/01/2024 a 31/12/2024, só fins de semana"
    assert TimeScope(date(2024, 2, 15), date(2024, 2, 15)).describe() == "em 15/02/2024"


# ---------------- léxico: a EvoOntology no caminho de toda pergunta ----------------

def test_lexico_evo_reconhece_o_sinonimo_aprendido_e_o_formal_nao():
    from pathlib import Path
    ws = Path(__file__).resolve().parent.parent / ".evoontology"
    pytest.importorskip("evoontology")
    q = "Quanto choveu em SBGL em 2020?"
    evo = EvoLexicon(REAL, ws, "ontology_v2").lookup(q)
    formal = OntologyLexicon(REAL).lookup(q)
    prec = "https://example.org/kgqa-met/ontology#Precipitation"
    assert evo.measures.get(prec) == "choveu"                                 # aceito pelo ciclo de evolução (ontology_v2)
    assert prec not in formal.measures                                        # a ontologia formal não tem "choveu"
    assert "citada na pergunta como 'choveu'" in REAL.menu(evo.measures, {})
