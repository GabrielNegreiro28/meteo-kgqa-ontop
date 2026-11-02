"""ResultShape: verificação e texto leem o papel de cada coluna declarado pelo compilador (plano, D3).

Perfil do grafo real (estações, cobertura) sem o Ontop: o LLM é roteirizado e a fonte devolve linhas fixas. Cada teste reproduz um defeito
encontrado na revisão de 2026-10-31 ou na rodada do novo_b (E78, E84, E95, E99...)."""
import json

from kgqa.contract import Status
from kgqa.store import ExecResult
from metqa.app import MetQA, Settings
from metqa.knowledge import DomainCatalog, ExemplarStore, OntologyLexicon
from pipeline.llm import ScriptedLLM
from tests.test_metqa import nir
from tests.test_reconcile import IDX

CAT = DomainCatalog(IDX)
XI, XD = "http://www.w3.org/2001/XMLSchema#integer", "http://www.w3.org/2001/XMLSchema#decimal"
T, P, W, V = "met:AirTemperature", "met:Precipitation", "met:WindSpeed", "met:PrevailingVisibility"
Y20, Y21 = ("2020-01-01", "2020-12-31"), ("2021-01-01", "2021-12-31")
HOT = {"agg": "max", "op": ">", "value": 35, "unit": "unit:DEG_C"}


def lit(v, dt=XI):
    return {"type": "literal", "value": str(v), "datatype": dt}


def table(*bindings):
    return {"head": {"vars": sorted({k for b in bindings for k in b})}, "results": {"bindings": list(bindings)}}


class Rows:
    """Fonte falsa: devolve as tabelas na ordem das consultas e guarda o SPARQL recebido."""
    source_id = "fake"

    def __init__(self, *tables):
        self.tables, self.queries = list(tables), []

    def select(self, query, timeout_s=0, max_rows=0):
        self.queries.append(query)
        return ExecResult(ok=True, results=self.tables.pop(0))


def ask(ir, *tables, q="pergunta"):
    raw = json.dumps(ir)
    src = Rows(*tables)
    app = MetQA(CAT, OntologyLexicon(CAT), ScriptedLLM({"interpret_A": [raw], "interpret_B": [raw]}), src, Settings(), ExemplarStore(None))
    return app.ask(q).response, src


def two(ir, a, b):
    ir["time"]["ranges"] = [{"start": a[0], "end": a[1]}, {"start": b[0], "end": b[1]}]
    return ir


def test_comparar_dias_usa_os_dias_que_cumprem_e_nao_os_dias_com_dados():
    ir = two(nir(T, ["st:SBGL"], "count", count_of="days", daily=HOT), Y20, Y21)
    r, _ = ask(ir, table({"value": lit(10), "n": lit(366)}), table({"value": lit(40), "n": lit(300)}))
    assert r.status == Status.ANSWERED
    assert "Maior em 01/01/2021 a 31/12/2021: 40 contra 10 (diferença de 30)." in r.answer_text


def test_diferenca_de_contagem_nao_tem_unidade():
    ir = two(nir(T, ["st:SBGL"], "count", count_of="readings"), Y20, Y21)
    r, _ = ask(ir, table({"n": lit(100)}), table({"n": lit(90)}))
    assert "(diferença de 10)." in r.answer_text and "°C)" not in r.answer_text


def test_periodo_sem_dados_na_comparacao_nao_vira_zero():
    ir = two(nir(P, ["st:SBGL"], "sum"), Y20, Y21)
    r, _ = ask(ir, table({"value": lit(1200, XD), "n": lit(8000)}), table({"value": lit(0, XD), "n": lit(0)}))
    assert "Não dá para comparar" in r.answer_text and "contra 0" not in r.answer_text
    assert "Não há registros de precipitação em SBGL, de 01/01/2021" in r.answer_text


def test_soma_sobre_conjunto_vazio_e_sem_registros():
    r, _ = ask(nir(P, ["st:SBGL"], "sum", *Y20), table({"value": lit(0, XD), "n": lit(0)}))
    assert r.status == Status.NO_RESULTS and "0 mm" not in r.answer_text


def test_contagem_zero_com_dados_e_resposta_e_diz_a_base():
    """E78/E84 do novo_b: 0 boletins acima do limiar é resposta, não 'sem registros'."""
    ir = nir(T, ["st:SBGL"], "count", *Y20, count_of="readings", conditions=[{"op": ">", "value": 60, "unit": "unit:DEG_C"}])
    r, src = ask(ir, table({"value": lit(0), "n": lit(8700)}))
    assert r.status == Status.ANSWERED, [d.message for d in r.diagnostics]
    assert r.answer_text.startswith("0 leituras de temperatura do ar em SBGL") and "(de 8.700 leituras no recorte)" in r.answer_text
    assert "AS ?value)" in src.queries[0] and src.queries[0].count("SELECT") == 3       # o que cumpre e a base, em subconsultas


def test_contagem_com_condicao_sem_dados_e_sem_registros():
    ir = nir(T, ["st:SBGL"], "count", *Y20, count_of="readings", conditions=[{"op": ">", "value": 60, "unit": "unit:DEG_C"}])
    r, _ = ask(ir, table({"value": lit(0), "n": lit(0)}))
    assert r.status == Status.NO_RESULTS


def test_limiar_aparece_na_unidade_em_que_foi_dito():
    ir = nir(V, ["st:SBGL"], "count", *Y20, count_of="days", daily={"agg": "min", "op": "<", "value": 5, "unit": "unit:KiloM"})
    r, src = ask(ir, table({"value": lit(12), "n": lit(300)}))
    assert "abaixo de 5 km (de 300 dias com dados)" in r.answer_text and "abaixo de 5 km" in r.answer_text.split("Entendi assim:")[1]
    assert "HAVING (MIN(?v1) < 5000)" in src.queries[0]


def test_ano_sem_separador_de_milhar():
    """E99/E102 do novo_b: 'por ano' saía como 2.016."""
    ir = nir(T, ["st:SBGL"], "max", "2016-01-01", "2017-12-31", group_by=["year"])
    r, _ = ask(ir, table({"year": lit(2016), "value": lit(35.2, XD), "n": lit(3279)},
                         {"year": lit(2017), "value": lit(37.8, XD), "n": lit(2923)}))
    assert "- 2016: 35,2 °C (n = 3.279)" in r.answer_text and "2.016" not in r.answer_text


def test_mes_e_ano():
    ir = nir(T, ["st:SBGL"], "avg", "2020-01-01", "2020-12-31", group_by=["month"])
    r, _ = ask(ir, table({"year": lit(2020), "month": lit(2), "value": lit(25.5, XD), "n": lit(212)}))
    assert "- 02/2020: 25,5 °C (n = 212)" in r.answer_text


def test_cada_atributo_mostra_o_proprio_valor():
    ir = nir(W, ["st:SBGL"], "max", *Y20, attributes=["met:runwayDesignator", "met:windCondition"])
    b = {"runway": {"type": "literal", "value": "09"}, "condition": {"type": "literal", "value": "VRB"}, "value": lit(40, XD),
         "t": {"type": "literal", "value": "2020-02-03T12:00:00Z"}, "n": lit(99)}
    r, _ = ask(ir, table(b))
    assert "(runwayDesignator: 09, windCondition: VRB)" in r.answer_text


def test_ranking_de_um_so_e_o_maior():
    ir = nir(W, [], "max", *Y20, group_by=["station"], order={"direction": "desc", "limit": 1})
    r, _ = ask(ir, table({"station": {"type": "uri", "value": "https://example.org/kgqa-met/data/station/SBCH"}, "value": lit(50, XD),
                          "n": lit(7715)}))
    assert "(só o maior):" in r.answer_text and "só os 1" not in r.answer_text and "- SBCH: 50 kt" in r.answer_text


def test_periodo_alem_da_cobertura_e_dito():
    r, _ = ask(nir(T, ["st:SBGL"], "avg", "2010-01-01", "2016-01-31"), table({"value": lit(25, XD), "n": lit(700)}))
    assert r.status == Status.ANSWERED and "vai além dos dados, que cobrem de 01/01/2016 a 31/12/2025" in r.answer_text


def test_paráfrase_concorda_o_artigo():
    r, _ = ask(nir(P, ["st:SBGL"], "sum", *Y20), table({"value": lit(1200, XD), "n": lit(8000)}))
    assert "Entendi assim: o total de precipitação" in r.answer_text


def test_todas_as_horas_sao_o_dia_todo():
    from metqa.domain.types import hour_ranges
    assert hour_ranges(range(24)) == "o dia todo"
