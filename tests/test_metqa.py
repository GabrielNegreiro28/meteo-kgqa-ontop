"""MVP (`metqa/`): entendimento verificado por concordância e pelo usuário. Adaptadores falsos (LLM roteirizado, grafo sintético, usuário
roteirizado). Sem rede, custo zero.

Não há gramática de regex no caminho: o LLM normaliza; a dúvida é detectada por mecanismos genéricos (leituras divergem, evidência fora da
pergunta, número ignorado) e resolvida pelo usuário — ou devolvida como pedido de esclarecimento quando não há usuário.
"""
import json
import subprocess
import sys
from datetime import date

import pytest

from eval import oracle
from metqa.domain.contract import Status
from metqa.execution.store import LocalRdflibBackend
from metqa.app import MetQA, Settings
from metqa.domain import TimeScope
from metqa.domain.types import hour_ranges
from metqa.knowledge import DomainCatalog, EvoLexicon, ExemplarStore, OntologyLexicon
from metqa.planning import compile_query, plan, to_interp
from metqa.presentation.render import num
from metqa.understanding import parse
from metqa.dialogue.replies import ScriptedUser
from metqa.llm.client import ScriptedLLM
from metqa.verification.rules import validate_query
from tests.helpers import IDX as REAL_IDX

SYNTH = DomainCatalog.from_ontology()
REAL = DomainCatalog(REAL_IDX)                 # perfil do grafo real (estações, cobertura), sem precisar do Ontop
BACKEND = LocalRdflibBackend()


def nir(measure, stations=(), agg=None, start=None, end=None, *, hours=None, weekdays=None, instant=None, conditions=(), count_of=None,
        daily=None, group_by=(), order=None, attributes=(), evidence=None, status="ok", **extra):
    """Interpretação NORMALIZADA, como o LLM devolve no formato do MVP."""
    ranges = [] if start is None else [{"start": start, "end": end or start}]
    return {"status": status, "measure": measure, "stations": list(stations),
            "time": {"ranges": ranges, "local_hours": hours, "weekdays": weekdays, "instant": instant},
            "calc": {"aggregation": agg, "count_of": count_of, "daily": daily}, "conditions": list(conditions),
            "shape": {"group_by": list(group_by), "order": order, "attributes": list(attributes)},
            "evidence": evidence or {}, "assumptions": [], "alternatives": [], "reason": "", **extra}


def llm(*a_then_b):
    """Roteiro das duas leituras: cada item é (leitura A, leitura B) de uma volta."""
    A = [json.dumps(x[0], ensure_ascii=False) for x in a_then_b]
    B = [json.dumps(x[1], ensure_ascii=False) for x in a_then_b]
    return ScriptedLLM({"interpret_A": A, "interpret_B": B})


def app(script, catalog=SYNTH, store=None, **settings):
    return MetQA(catalog, OntologyLexicon(catalog), script, BACKEND, Settings(timeout_s=20, **settings), store or ExemplarStore(None))


AVG = nir("met:AirTemperature", agg="avg", group_by=["station"], evidence={"measure": "temperatura", "calc": "média", "shape": "por estação"})


# ---------------- concordância: segue sem perguntar ----------------

def test_leituras_concordam_responde_igual_ao_oraculo_sem_perguntar():
    script = llm((AVG, AVG))
    user = ScriptedUser([])
    r = app(script).ask("Qual foi a temperatura média por estação?", user=user).response
    assert r.status == Status.ANSWERED, [d.message for d in r.diagnostics]
    assert user.shown == []                                                     # sem risco: não incomoda o usuário
    assert {c["stage"] for c in script.calls} == {"interpret_A", "interpret_B"}  # SPARQL e texto saem de código
    groups = {}
    for o in oracle.sel(oracle.load_obs(), "AirTemperature"):
        groups.setdefault(o["station"], []).append(o["value"])
    for station, values in groups.items():
        assert f"- {station}: {num(oracle.avg(values))} °C (n = {len(values)})" in r.answer_text
    assert "Entendi assim: a média de temperatura do ar em todas as estações" in r.answer_text and "diga o que corrigir" in r.answer_text


def test_uma_leitura_so_quando_configurado():
    script = ScriptedLLM({"interpret_A": [json.dumps(AVG)]})
    r = app(script, readings=1).ask("Qual foi a temperatura média por estação?").response
    assert r.status == Status.ANSWERED and {c["stage"] for c in script.calls} == {"interpret_A"}


# ---------------- divergência: pergunta ao usuário pelo que difere ----------------

Q_AMB = "Qual foi a temperatura da Estação Vale Verde?"
MEAN = nir("met:AirTemperature", ["st:EST-B"], "avg", evidence={"measure": "temperatura", "stations": "Estação Vale Verde"})
MAX = nir("met:AirTemperature", ["st:EST-B"], "max", evidence={"measure": "temperatura", "stations": "Estação Vale Verde"})


def test_leituras_divergem_sem_usuario_devolve_as_opcoes_e_nao_chuta():
    r = app(llm((MEAN, MAX))).ask(Q_AMB).response
    assert r.status == Status.NEEDS_CLARIFICATION and r.results is None
    d = next(x for x in r.diagnostics if x.code == "CONFIRMATION_REQUIRED")
    paras = [o["paraphrase"] for o in d.details["options"]]
    assert len(paras) == 2 and paras[0].startswith("a média") and paras[1].startswith("a máxima")
    assert "muda: cálculo" in r.answer_text


def test_cliente_reenvia_a_opcao_escolhida_e_executa_sem_chamar_o_llm():
    first = app(llm((MEAN, MAX)), secret=b"k").ask(Q_AMB).response
    option = next(x for x in first.diagnostics if x.code == "CONFIRMATION_REQUIRED").details["options"][1]
    chosen, token = option["interpretation"], option["confirmation_token"]
    script = ScriptedLLM({})
    r = app(script, secret=b"k").ask(Q_AMB, confirmed=chosen, confirmation=token).response
    assert r.status == Status.ANSWERED and script.calls == []
    expected = max(o["value"] for o in oracle.sel(oracle.load_obs(), "AirTemperature", "EST-B"))
    assert num(expected) in r.answer_text and "(confirmado por você)" in r.answer_text


def test_confirmacao_sem_o_token_da_opcao_e_recusada():
    """Sem o token, um cliente gravaria qualquer interpretação como verificada (plano, D7)."""
    forged = {**MAX, "calc": {"aggregation": "min", "count_of": None, "daily": None}}
    store = ExemplarStore(None)
    a = app(ScriptedLLM({}), store=store, secret=b"k")
    for token in (None, "0" * 64, a.confirmation_token(Q_AMB, MAX)):
        r = a.ask(Q_AMB, confirmed=forged, confirmation=token).response
        assert r.status == Status.REJECTED and "CONFIRMATION_TOKEN_INVALID" in {d.code for d in r.diagnostics}
    assert store.items == []


def test_usuario_escolhe_a_opcao_e_vira_exemplo_verificado():
    store = ExemplarStore(None)
    user = ScriptedUser(["2"])
    r = app(llm((MEAN, MAX)), store=store).ask(Q_AMB, user=user).response
    assert r.status == Status.ANSWERED and "1. a média" in user.shown[0] and "2. a máxima" in user.shown[0]
    assert len(store.items) == 1 and store.items[0]["verified_by"] == "user" and store.items[0]["ir"]["calc"]["aggregation"] == "max"
    # a próxima pergunta parecida leva o exemplo às leituras do LLM (o caso de borda virou DADO, não regra)
    script = llm((MAX, MAX))
    app(script, store=store).ask("Qual foi a temperatura da Estação Serra Azul?", user=ScriptedUser([]))
    assert "<exemplos>" in script.calls[0]["user"] and "Vale Verde" in script.calls[0]["user"]


def test_usuario_corrige_em_texto_livre_e_a_correcao_volta_ao_llm():
    user = ScriptedUser(["na verdade quero a máxima"])
    script = llm((MEAN, MAX), (MAX, MAX))
    r = app(script).ask(Q_AMB, user=user).response
    assert r.status == Status.ANSWERED
    assert "na verdade quero a máxima" in script.calls[-1]["user"] and "<interpretacao_anterior>" in script.calls[-1]["user"]


def test_usuario_cancela():
    r = app(llm((MEAN, MAX))).ask(Q_AMB, user=ScriptedUser(["cancelar"])).response
    assert r.status == Status.NEEDS_CLARIFICATION and "USER_CANCELLED" in {d.code for d in r.diagnostics}


# ---------------- sinais fortes de uma leitura só ----------------

def test_numero_da_pergunta_ignorado_pede_confirmacao():
    q = "Quantas leituras de temperatura acima de 30 °C por estação?"
    dropped = nir("met:AirTemperature", agg="count", group_by=["station"], evidence={"measure": "temperatura", "calc": "Quantas leituras"})
    r = app(llm((dropped, dropped))).ask(q).response
    d = next(x for x in r.diagnostics if x.code == "CONFIRMATION_REQUIRED")
    assert any("'30'" in reason for reason in d.details["reasons"])


def test_evidencia_que_nao_esta_na_pergunta_pede_confirmacao():
    bad = {**AVG, "evidence": {"measure": "temperatura", "calc": "média móvel"}}
    r = app(llm((bad, bad))).ask("Qual foi a temperatura média por estação?").response
    assert any("'média móvel'" in x for x in next(d for d in r.diagnostics if d.code == "CONFIRMATION_REQUIRED").details["reasons"])


def test_o_proprio_llm_diz_que_nao_da():
    out = nir(None, status="unsupported", reason="Não há nome de cidade nos dados.")
    r = app(llm((out, out))).ask("Qual a temperatura média em Curitiba?").response
    assert r.status == Status.UNSUPPORTED and "cidade" in r.answer_text


# ---------------- mundo fechado: valores, não frases ----------------

def test_unidade_de_outra_dimensao_e_recusada_por_analise_dimensional():
    wrong = nir("met:AirTemperature", ["st:EST-B"], agg="count", conditions=[{"op": "<", "value": 40, "unit": "unit:PERCENT"}],
                evidence={"measure": "temperatura", "conditions": "abaixo de 40%"})
    r = app(llm((wrong, wrong), (wrong, wrong))).ask("Quantas leituras de temperatura abaixo de 40% na Estação Vale Verde?").response
    assert r.status == Status.UNSUPPORTED and "UNIT_DIMENSION_MISMATCH" in {d.code for d in r.diagnostics}


def test_datas_e_horas_invalidas_voltam_para_reparo():
    p = parse(nir("met:AirTemperature", ["st:SBGL"], "avg", "2024-02-30", hours=[18, 24]))
    assert any("data inválida" in e for e in p.errors) and any("local_hours" in e for e in p.errors)


def test_periodo_fora_da_cobertura_encerra_sem_consultar():
    ir = nir("met:AirTemperature", ["st:SBGL"], "avg", "2012-01-01", "2012-12-31", evidence={"time": "2012"})
    r = app(llm((ir, ir)), catalog=REAL).ask("Qual foi a temperatura média em SBGL em 2012?").response
    assert r.status == Status.NO_RESULTS and "OUT_OF_COVERAGE" in {d.code for d in r.diagnostics} and r.sparql is None


# ---------------- forma da consulta ----------------

def test_horas_que_atravessam_a_meia_noite_viram_um_conjunto():
    hours = list(range(18, 24)) + list(range(0, 6))
    assert hour_ranges(hours) == "das 18h às 6h (antes das 6h)"
    p = parse(nir("met:RelativeHumidity", ["st:SBNF"], "avg", "2020-07-01", "2020-07-31", hours=hours))
    cq = plan(p.parts).parts[0].query
    sparql = compile_query(cq, REAL).sparql
    assert "FILTER(?h IN (0, 1, 2, 3, 4, 5, 18, 19, 20, 21, 22, 23))" in sparql          # 18h–6h local
    assert not validate_query(sparql, to_interp(cq), REAL.index, True)[1]


def test_duas_faixas_sao_uma_comparacao():
    ir = nir("met:AirTemperature", ["st:SBGL"], "avg")
    ir["time"]["ranges"] = [{"start": "2016-01-01", "end": "2016-01-31"}, {"start": "2025-01-01", "end": "2025-01-31"}]
    p = plan(parse(ir).parts)
    assert p.combine == "compare" and [x.query.scope.start.year for x in p.parts] == [2016, 2025]
    for part in p.parts:
        assert not validate_query(compile_query(part.query, REAL).sparql, to_interp(part.query), REAL.index, True)[1]


def test_instante_compila_em_utc():
    p = parse(nir("met:AirTemperature", ["st:SBGL"], instant="2021-03-10T15:00:00-03:00"))
    cq = p.parts[0][1]
    assert cq.intent == "instant"
    sparql = compile_query(cq, REAL).sparql
    assert '"2021-03-10T18:00:00Z"^^xsd:dateTime' in sparql and not validate_query(sparql, to_interp(cq), REAL.index, True)[1]


def test_numeros_em_portugues_e_escopo_descrito():
    assert num(1234.5) == "1.234,5" and num(25.0) == "25" and num(0.125) == "0,13" and num(None) == "n/d"
    assert TimeScope(date(2024, 1, 1), date(2024, 12, 31), weekdays=(5, 6)).describe() == "de 01/01/2024 a 31/12/2024, só fins de semana"


# ---------------- memória e léxico ----------------

def test_memoria_so_aceita_exemplo_verificado_e_recupera_por_semelhanca():
    store = ExemplarStore(None)
    with pytest.raises(ValueError):
        store.add("Qual a temperatura?", {}, "llm")
    store.add("Qual foi a umidade média de SBNF durante a noite, das 18h às 6h, em julho de 2020?", {"x": 1}, "user")
    store.add("Quantos boletins de SBGL em 2019 tiveram chuva?", {"x": 2}, "oracle")
    hit = store.search("Qual a umidade média de SBGL de noite, das 19h às 5h, em 2021?")
    assert hit and hit[0]["ir"] == {"x": 1}


def test_lexico_evo_reconhece_o_sinonimo_aprendido_e_o_formal_nao():
    from pathlib import Path
    pytest.importorskip("evoontology")
    ws = Path(__file__).resolve().parent.parent / ".evoontology"
    q = "Quanto choveu em SBGL em 2020?"
    prec = "https://example.org/kgqa-met/ontology#Precipitation"
    assert EvoLexicon(REAL, ws, "ontology_v2").lookup(q).measures.get(prec) == "choveu"
    assert prec not in OntologyLexicon(REAL).lookup(q).measures


def test_o_caminho_da_pergunta_nao_tem_gramatica_de_regex():
    """`metqa` não carrega o leitor por regex nem a conciliação por trechos (ficam só para o legado)."""
    code = ("import sys, metqa.app.pipeline, metqa.app.cli; "
            "bad=[m for m in ('pipeline.spans','pipeline.reconcile') if m in sys.modules]; print(bad); sys.exit(1 if bad else 0)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
