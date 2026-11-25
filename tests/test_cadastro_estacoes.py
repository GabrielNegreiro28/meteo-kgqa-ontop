"""Cadastro das estações (data/estacoes.csv) e hora civil de cada estação (R1 corrigida, D-115). Sem rede e sem Ontop."""
import copy
import csv
import json
from pathlib import Path

from metqa.app import MetQA, Settings
from metqa.domain.contract import Status
from metqa.knowledge import DomainCatalog, ExemplarStore, OntologyLexicon
from metqa.knowledge.index import STATION_NS
from metqa.llm.client import ScriptedLLM
from metqa.planning import compile_query
from metqa.understanding import parse
from ingest.stations import fuso
from tests.helpers import IDX
from tests.test_metqa import nir
from tests.test_metqa_shapes import XD, Rows, lit, table

ROOT = Path(__file__).resolve().parent.parent
REG = {r["sigla"]: r for r in csv.DictReader(open(ROOT / "data" / "estacoes.csv", encoding="utf-8"))}
T = "met:AirTemperature"


def _catalog() -> DomainCatalog:
    """Índice de teste com o cadastro de verdade de algumas estações (cópia: o índice compartilhado não muda)."""
    idx = copy.deepcopy(IDX)
    codes = ("SBGL", "SBRJ", "SBJR", "SBAF", "SBSC", "SIHL", "SBGR", "SBSP", "SBMT", "SBEG", "SBRB", "SBCT", "SBBI", "SBDB",
             "SBCY", "SBFL", "SBNT", "SBSG", "SBBE", "SBJC", "SBMM", "SBFZ", "SBKP")
    idx.entities = {STATION_NS + c: [c] for c in codes}
    idx.aliases = {STATION_NS + c: [a for a in REG[c]["apelidos"].split(";") if a] for c in codes}
    idx.places = {STATION_NS + c: {"municipio": REG[c]["municipio"], "uf": REG[c]["uf"], "estado": REG[c]["estado"],
                                   "regiao": REG[c]["regiao"], "tz": REG[c]["fuso_iana"],
                                   **({"cidade": REG[c]["cidade_atendida"]} if REG[c]["cidade_atendida"] else {})} for c in codes}
    return DomainCatalog(idx)


CAT = _catalog()
ST = lambda c: STATION_NS + c


def run(ir, q, *tables, b=None):
    raw = json.dumps(ir, ensure_ascii=False)
    llm = ScriptedLLM({"interpret_A": [raw], "interpret_B": [json.dumps(b, ensure_ascii=False) if b else raw]})
    app = MetQA(CAT, OntologyLexicon(CAT), llm, Rows(*tables), Settings(reread=False), ExemplarStore(None))
    return app.ask(q).response


# ---------------- o cadastro ----------------

def test_cadastro_cobre_todas_as_siglas_e_todo_fuso_vem_da_regra():
    assert len(REG) == 178
    for r in REG.values():
        assert r["fuso_iana"] and r["fuso_legal"]
        if r["lon"]:
            assert int(r["fuso_legal"]) == fuso(r["uf"], float(r["lon"]))[0]


def test_fusos_conferidos_contra_metar():
    """Os fusos do cadastro são os que a comparação com o METAR achou no relógio antigo (data/fuso_metar_resultado.json)."""
    got = json.loads((ROOT / "data" / "fuso_metar_resultado.json").read_text(encoding="utf-8"))
    for key, v in got.items():
        sigla, per = key.split("_")
        if per == "20181":
            assert -v["melhor_k"] == int(REG[sigla]["fuso_legal"]), key
        if per == "20237":
            assert v["melhor_k"] == 0, key                     # depois de abril de 2021 o relógio é UTC


def test_municipio_e_o_do_aeroporto_e_nao_o_da_cidade_atendida():
    assert REG["SBGR"]["municipio"] == "Guarulhos" and REG["SBCF"]["municipio"] == "Confins"


# ---------------- reconhecimento por lugar ----------------

def test_apelido_e_municipio_unico_identificam_a_estacao():
    assert set(CAT.stations_in("Quanto choveu em Guarulhos em 2020?")) == {ST("SBGR")}
    assert set(CAT.stations_in("temperatura em Congonhas")) == {ST("SBSP")}
    assert set(CAT.stations_in("vento no Galeão")) == {ST("SBGL")}


def test_estado_e_regiao_cobrem_varias_estacoes():
    assert set(CAT.stations_in("chuva no Paraná")) == {ST("SBCT"), ST("SBBI")}
    assert {ST("SBEG"), ST("SBRB")} <= set(CAT.stations_in("na região Norte"))


def test_nome_mais_longo_vence_e_palavra_comum_nao_vira_estacao():
    assert set(CAT.stations_in("Foi bonito o dia")) == set()                 # Bonito (MS) é palavra comum
    assert CAT.index.station_display(ST("SBGR")) == "SBGR (Guarulhos/SP)"


def test_nome_que_cobre_varias_e_escolha_de_uma_so_e_ambiguidade():
    amb = CAT.index.ambiguous_mentions("temperatura no Rio de Janeiro", {ST("SBGL")})
    assert amb and "rio de janeiro" in amb[0]
    assert not CAT.index.ambiguous_mentions("temperatura no Galeão, Rio de Janeiro", {ST("SBGL")})      # outra menção identifica
    every = {i for i in CAT.index.entities if CAT.index.places[i]["estado"] == "Rio de Janeiro"}
    assert not CAT.index.ambiguous_mentions("temperatura no Rio de Janeiro", every)                    # todas: um valor por estação


def test_pipeline_pergunta_quando_a_cidade_tem_varias_estacoes():
    ir = nir(T, ["st:SBGL"], "avg", "2021-03-01", "2021-03-31",
             evidence={"measure": "temperatura", "stations": "Rio de Janeiro", "calc": "média", "time": "em março de 2021"})
    r = run(ir, "Qual foi a temperatura média no Rio de Janeiro em março de 2021?")
    assert r.status == Status.NEEDS_CLARIFICATION, r.answer_text


def test_pipeline_responde_pelo_apelido_e_mostra_o_lugar():
    ir = nir(T, ["st:SBGR"], "avg", "2021-03-01", "2021-03-31",
             evidence={"measure": "temperatura", "stations": "Guarulhos", "calc": "média", "time": "em março de 2021"})
    r = run(ir, "Qual foi a temperatura média em Guarulhos em março de 2021?", table({"value": lit(23.4, XD), "n": lit(700)}))
    assert r.status == Status.ANSWERED and "SBGR (Guarulhos/SP)" in r.answer_text, r.answer_text


# ---------------- hora civil da estação ----------------

def _instant_sparql(code, instant):
    p = parse(nir(T, [f"st:{code}"], instant=instant))
    app = MetQA(CAT, OntologyLexicon(CAT), ScriptedLLM({}), Rows(), Settings(), ExemplarStore(None))
    app._localize(p)
    return compile_query(p.parts[0][1], CAT).sparql


def test_horario_pontual_usa_o_fuso_da_estacao():
    assert '"2018-07-10T18:00:00Z"' in _instant_sparql("SBEG", "2018-07-10T14:00")          # Manaus, UTC−4
    assert '"2018-07-10T19:00:00Z"' in _instant_sparql("SBRB", "2018-07-10T14:00:00-03:00")  # Rio Branco, UTC−5: o fuso do LLM é descartado
    assert '"2018-01-10T16:00:00Z"' in _instant_sparql("SBGR", "2018-01-10T14:00")          # São Paulo em horário de verão, UTC−2


# ---------------- correções do estudo_20261125 e diretrizes gerais (D-119, D-121, D-122) ----------------

def test_cidade_atendida_e_dado_do_cadastro():
    assert set(CAT.stations_in("temperatura em Cuiabá em 2019")) == {ST("SBCY")}           # SBCY fica em Várzea Grande
    assert set(CAT.stations_in("chuva em Natal em 2020")) == {ST("SBNT"), ST("SBSG")}      # duas estações: continua ambíguo
    assert CAT.index.ambiguous_mentions("chuva em Natal em 2020", {ST("SBNT")})


def test_diretorio_vai_ao_llm_com_os_fatos_do_cadastro():
    menu = CAT.menu({}, {})
    assert "SBCY | Várzea Grande (atende Cuiabá) | MT | Centro-Oeste" in menu and "SBFL |" in menu


def test_estacao_escolhida_pelo_modelo_com_as_duas_leituras_de_acordo_e_nota_visivel():
    ir = nir("met:Precipitation", ["st:SBFL"], "sum", "2020-01-01", "2020-12-31",
             evidence={"measure": "choveu", "stations": "Floripa", "calc": "Quanto", "time": "em 2020"})
    r = run(ir, "Quanto choveu em Floripa em 2020?", table({"value": lit(1500, XD), "n": lit(8000)}))
    assert r.status == Status.ANSWERED and "entendido como SBFL (Florianópolis/SC)" in r.answer_text, r.answer_text


def test_leituras_que_divergem_na_estacao_perguntam():
    a = nir("met:Precipitation", ["st:SBFL"], "sum", "2020-01-01", "2020-12-31",
            evidence={"measure": "choveu", "stations": "Floripa", "calc": "Quanto", "time": "em 2020"})
    b = {**a, "stations": ["st:SBJA"]}
    r = run(a, "Quanto choveu em Floripa em 2020?", b=b)
    assert r.status == Status.NEEDS_CLARIFICATION


def test_aeroporto_identificado_e_cidade_inteira_escolhida_e_sinal_forte():
    over = CAT.index.ambiguous_mentions("QNH em Curitiba (Afonso Pena) em 2022", {ST("SBCT"), ST("SBBI")})
    assert over and "não foi pedida" in over[0]


def test_minutos_do_horario_nao_sao_restricao():
    from metqa.understanding.evidence import conservation
    p = parse(nir(T, ["st:SBGR"], "avg", "2023-01-01", "2023-12-31", hours=[0, 1, 2, 3, 4, 5]))
    assert not conservation({"time": "das 0h às 5h59 em 2023"}, [cq for _, cq in p.parts])
    assert conservation({"time": "das 0h às 5h59 em 2024"}, [cq for _, cq in p.parts])       # o ano continua conferido


EV = {"measure": "temperatura", "stations": "SBGR", "calc": "média", "time": "em março de 2021"}


def test_leitura_que_declara_nao_suportado_nao_trava_a_que_respondeu():
    ok = nir(T, ["st:SBGR"], "avg", "2021-03-01", "2021-03-31", evidence=EV)
    no = {**ok, "status": "unsupported", "reason": "o formato não representa isso"}
    r = run(ok, "Qual foi a temperatura média em SBGR em março de 2021?", table({"value": lit(23.4, XD), "n": lit(700)}), b=no)
    assert r.status == Status.ANSWERED and "fora do que o sistema faz" in r.answer_text, r.answer_text


def test_esclarecimento_com_alternativas_continua_perguntando():
    ok = nir(T, ["st:SBGR"], "avg", "2021-03-01", "2021-03-31", evidence=EV)
    ask = {**ok, "status": "needs_clarification", "reason": "média ou máxima?", "alternatives": ["média", "máxima"]}
    r = run(ok, "Qual foi a temperatura média em SBGR em março de 2021?", b=ask)
    assert r.status == Status.NEEDS_CLARIFICATION
