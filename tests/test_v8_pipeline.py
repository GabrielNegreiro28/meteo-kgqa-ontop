"""Prompt v8 de ponta a ponta com LLM roteirizado (custo zero): o LLM só cita trechos, o tempo vem da leitura determinística e a consulta
só do compilador. A etapa de geração de SPARQL nunca é chamada."""
import json

from eval import oracle
from kgqa.contract import Status
from pipeline.llm import ScriptedLLM
from pipeline.orchestrator import run_pipeline
from tests.test_pipeline import BACKEND, INDEX


def run(question, interp, answer="ok"):
    llm = ScriptedLLM({"interpret": [json.dumps(interp, ensure_ascii=False)], "answer": [answer]})
    return run_pipeline(question, llm, BACKEND, INDEX, timeout_s=20, prompts_version="v8"), llm


STATION_AVG = {"status": "ok", "properties": [{"iri": "met:AirTemperature", "span": "temperatura"}], "entities": [],
               "aggregation": {"value": "avg", "span": "média"}, "group_by": [{"dim": "station", "span": "por estação"}]}


def test_media_por_estacao_igual_ao_oraculo_sem_gerar_sparql():
    # o grafo sintético não tem met:localDate: período só se testa no grafo real (tests/test_v8_real.py); aqui, todo o histórico
    res, llm = run("Qual foi a temperatura média por estação?", STATION_AVG)
    r = res.response
    assert r.status == Status.ANSWERED, [d.code for d in r.diagnostics]
    assert "generate" not in {c["stage"] for c in llm.calls}
    rows = [(b["station"]["value"].rsplit("/", 1)[-1], round(float(b["value"]["value"]), 2), int(b["n"]["value"]))
            for b in r.results["results"]["bindings"]]
    groups = {}
    for o in oracle.sel(oracle.load_obs(), "AirTemperature"):
        groups.setdefault(o["station"], []).append(o["value"])
    assert rows == [(s, round(float(oracle.avg(v)), 2), len(v)) for s, v in sorted(groups.items())]


def test_periodo_vem_da_leitura_e_sem_dia_local_vira_unsupported_nao_sparql_livre():
    """Com período, o v8 exige o dia local no grafo (o sintético não tem): diz `unsupported` em vez de pedir SPARQL ao LLM, e o período
    registrado é o que a leitura determinística deu."""
    res, llm = run("Qual foi a temperatura média por estação entre 03/03/2026 e 05/03/2026?", STATION_AVG)
    r = res.response
    assert r.status == Status.UNSUPPORTED and "generate" not in {c["stage"] for c in llm.calls}


def test_periodo_vago_pede_esclarecimento_sem_consultar():
    res, llm = run("Qual foi a temperatura média da Estação Vale Verde em toda a semana?",
                   {"status": "ok", "properties": [{"iri": "met:AirTemperature", "span": "temperatura"}],
                    "entities": [{"iri": "st:EST-B", "span": "Estação Vale Verde"}], "aggregation": {"value": "avg", "span": "média"}})
    assert res.response.status == Status.NEEDS_CLARIFICATION
    assert {c["stage"] for c in llm.calls} == {"interpret"}


def test_trecho_errado_tem_uma_rodada_de_reparo():
    bad = {"status": "ok", "properties": [{"iri": "met:AirTemperature", "span": "calor"}], "entities": [],
           "aggregation": {"value": "avg", "span": "média"}, "group_by": [{"dim": "station", "span": "por estação"}]}
    good = {**bad, "properties": [{"iri": "met:AirTemperature", "span": "temperatura"}]}
    llm = ScriptedLLM({"interpret": [json.dumps(bad), json.dumps(good)], "answer": ["ok"]})
    res = run_pipeline("Qual foi a temperatura média por estação?", llm, BACKEND, INDEX, timeout_s=20, prompts_version="v8")
    assert res.response.status == Status.ANSWERED
    assert sum(c["stage"] == "interpret" for c in llm.calls) == 2
    assert "SPAN_NOT_IN_QUESTION" in llm.calls[1]["user"] or "não está na pergunta" in llm.calls[1]["user"]


def test_json_do_v7_com_periodo_e_recusado_no_v8():
    """O v8 não aceita período vindo do LLM: a chave nem existe no esquema (a saída é inválida e vai para reparo)."""
    v7 = {"status": "ok", "properties": ["met:AirTemperature"], "entities": [], "filters": [], "aggregation": "avg",
          "period": {"start": "2026-03-01", "end": "2026-03-31", "tz": "-03:00", "inclusive_end": True}, "record_kind": "observation"}
    res, _ = run("Qual foi a temperatura média por estação entre 03/03/2026 e 05/03/2026?", v7)
    assert res.response.status == Status.EXECUTION_ERROR
