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
    codes = ("SBGL", "SBRJ", "SBJR", "SBAF", "SBSC", "SIHL", "SBGR", "SBSP", "SBMT", "SBEG", "SBRB", "SBCT", "SBBI", "SBDB")
    idx.entities = {STATION_NS + c: [c] for c in codes}
    idx.aliases = {STATION_NS + c: [a for a in REG[c]["apelidos"].split(";") if a] for c in codes}
    idx.places = {STATION_NS + c: {"municipio": REG[c]["municipio"], "uf": REG[c]["uf"], "estado": REG[c]["estado"],
                                   "regiao": REG[c]["regiao"], "tz": REG[c]["fuso_iana"]} for c in codes}
    return DomainCatalog(idx)


CAT = _catalog()
ST = lambda c: STATION_NS + c


def run(ir, q, *tables):
    raw = json.dumps(ir, ensure_ascii=False)
    llm = ScriptedLLM({"interpret_A": [raw], "interpret_B": [raw]})
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
