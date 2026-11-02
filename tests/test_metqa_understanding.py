"""Entendimento (plano, Fase 3): conservação da evidência, releitura isolada do tempo, evidência tolerante na forma, diálogo sem rodadas
inúteis. LLM roteirizado e fonte com linhas fixas; sem Ontop e sem custo. As perguntas do novo_b (E87, E94, E112, E141) estão reescritas
com estações do perfil de teste."""
import json

from metqa.domain.contract import Status
from metqa.dialogue.replies import ScriptedUser
from metqa.llm.client import LLMError, ScriptedLLM
from tests.test_metqa import nir
from tests.test_metqa_shapes import CAT, Rows, XD, lit, table
from metqa.app import MetQA, Settings
from metqa.knowledge import ExemplarStore, OntologyLexicon

T = "met:AirTemperature"
AVG_ROW = table({"value": lit(25.1, XD), "n": lit(24)})


def run(script: dict, q: str, *tables, user=None, **settings):
    llm = ScriptedLLM({k: [json.dumps(x, ensure_ascii=False) if isinstance(x, dict) else x for x in v] for k, v in script.items()})
    app = MetQA(CAT, OntologyLexicon(CAT), llm, Rows(*tables), Settings(**settings), ExemplarStore(None))
    return app.ask(q, user=user).response, llm


def both(ir, **extra):
    return {"interpret_A": [ir], "interpret_B": [ir], **extra}


def reasons(r):
    return next(d for d in r.diagnostics if d.code == "CONFIRMATION_REQUIRED").details["reasons"]


# ---------------- conservação da evidência ----------------

DAY3 = "Qual foi a temperatura média em SBGL no dia 3 de março de 2021?"


def test_dia_que_virou_o_mes_nas_duas_leituras_e_sinal_forte():
    """As duas leituras concordam no erro: a concordância não pega, a conservação pega (o 3 do trecho não está na janela)."""
    wrong = nir(T, ["st:SBGL"], "avg", "2021-03-01", "2021-03-31",
                evidence={"measure": "temperatura", "stations": "SBGL", "calc": "média", "time": "no dia 3 de março de 2021"})
    r, _ = run(both(wrong), DAY3)
    assert r.status == Status.NEEDS_CLARIFICATION and any("'3'" in x and "período normalizado" in x for x in reasons(r))


def test_dia_certo_passa():
    right = nir(T, ["st:SBGL"], "avg", "2021-03-03",
                evidence={"measure": "temperatura", "stations": "SBGL", "calc": "média", "time": "no dia 3 de março de 2021"})
    r, _ = run(both(right), DAY3, AVG_ROW)
    assert r.status == Status.ANSWERED, [d.message for d in r.diagnostics]


def test_limiar_trocado_e_sinal_forte():
    q = "Quantas leituras de temperatura acima de 35 °C houve em SBGL em 2020?"
    ir = nir(T, ["st:SBGL"], "count", "2020-01-01", "2020-12-31", count_of="readings", conditions=[{"op": ">", "value": 30, "unit": "unit:DEG_C"}],
             evidence={"measure": "temperatura", "stations": "SBGL", "calc": "Quantas leituras", "conditions": "acima de 35 °C", "time": "em 2020"})
    r, _ = run(both(ir), q)
    assert any("'35'" in x and "condições" in x for x in reasons(r))


# ---------------- releitura isolada do trecho de tempo ----------------

MARCH = "Qual a temperatura média de SBGL em março de 2021?"
MARCH_IR = nir(T, ["st:SBGL"], "avg", "2021-03-01", "2021-03-31",
               evidence={"measure": "temperatura", "stations": "SBGL", "calc": "média", "time": "em março de 2021"})


def test_releitura_que_da_outro_periodo_e_sinal_forte():
    other = {"ranges": [{"start": "2021-03-01", "end": "2021-03-03"}], "local_hours": None, "weekdays": None, "instant": None}
    r, llm = run(both(MARCH_IR, reread_time=[other]), MARCH)
    assert r.status == Status.NEEDS_CLARIFICATION and any("relido sozinho" in x for x in reasons(r))
    call = next(c for c in llm.calls if c["stage"] == "reread_time")
    assert "<tempo>em março de 2021</tempo>" == call["user"]                    # só o trecho: sem a pergunta, sem exemplos


def test_releitura_igual_segue():
    same = {"ranges": [{"start": "2021-03-01", "end": "2021-03-31"}], "local_hours": None, "weekdays": None, "instant": None}
    r, llm = run(both(MARCH_IR, reread_time=[same]), MARCH, AVG_ROW)
    assert r.status == Status.ANSWERED and "reread_time" in {c["stage"] for c in llm.calls}


def test_releitura_desligada_nao_chama():
    r, llm = run(both(MARCH_IR), MARCH, AVG_ROW, reread=False)
    assert r.status == Status.ANSWERED and "reread_time" not in {c["stage"] for c in llm.calls}


# ---------------- evidência tolerante na forma (alarmes falsos do novo_b) ----------------

def test_evidencia_entre_aspas_E141():
    q = "Em SBGL, no dia cinco de fevereiro de 2022, qual foi a média de bulbo úmido?"
    ir = nir("met:WetBulbTemperature", ["st:SBGL"], "avg", "2022-02-05",
             evidence={"measure": '"bulbo úmido"', "stations": '"SBGL"', "time": '"no dia cinco de fevereiro de 2022"', "calc": '"média"'})
    r, _ = run(both(ir), q, AVG_ROW)
    assert r.status == Status.ANSWERED, [d.message for d in r.diagnostics]


def test_evidencia_com_reticencias_E87():
    q = "Em quantos dias de 2018 a mínima de temperatura do ar de SBGL ficou abaixo de 12 °C?"
    ir = nir(T, ["st:SBGL"], "count", "2018-01-01", "2018-12-31", count_of="days",
             daily={"agg": "min", "op": "<", "value": 12, "unit": "unit:DEG_C"},
             evidence={"measure": "temperatura do ar", "stations": "SBGL", "calc": "Em quantos dias ... a mínima",
                       "conditions": "abaixo de 12 °C", "time": "de 2018"})
    r, _ = run(both(ir), q, table({"value": lit(3), "n": lit(365)}))
    assert r.status == Status.ANSWERED, [d.message for d in r.diagnostics]


def test_duracao_da_chuva_com_palavra_no_meio_E94():
    q = "Qual foi a duração máxima da chuva em um boletim de SBGL em cada mês de 2019?"
    ir = nir("met:PrecipitationDuration", ["st:SBGL"], "max", "2019-01-01", "2019-12-31", group_by=["month"],
             evidence={"measure": "duração da chuva", "stations": "SBGL", "calc": "máxima", "shape": "em cada mês", "time": "de 2019"})
    r, _ = run(both(ir), q, table({"year": lit(2019), "month": lit(1), "value": lit(60, XD), "n": lit(700)}))
    assert r.status == Status.ANSWERED, [d.message for d in r.diagnostics]


def test_grandeza_por_sinonimo_do_lexico():
    """O trecho da grandeza é paráfrase do LLM, mas o léxico liga um trecho da pergunta ao mesmo IRI: não é alarme."""
    ir = nir("met:WetBulbTemperature", ["st:SBGL"], "avg", "2021-03-01", "2021-03-31",
             evidence={"measure": "temperatura de bulbo úmido", "stations": "SBGL", "calc": "média", "time": "em março de 2021"})
    r, _ = run(both(ir), "Qual a média de bulbo úmido em SBGL em março de 2021?", AVG_ROW, reread=False)
    assert r.status == Status.ANSWERED, [d.message for d in r.diagnostics]
    wrong = {**ir, "measure": T}                                                # outro IRI com o mesmo trecho: continua alarme
    r, _ = run(both(wrong), "Qual a média de bulbo úmido em SBGL em março de 2021?", reread=False)
    assert any("'temperatura de bulbo úmido'" in x for x in reasons(r))


def test_leitura_que_falhou_no_llm_nao_e_divergencia():
    ir = MARCH_IR
    r, _ = run({"interpret_A": [ir], "interpret_B": [LLMError("fora do ar")]}, MARCH, AVG_ROW, reread=False)
    assert r.status == Status.ANSWERED and "só uma das duas leituras foi válida" in r.answer_text


def test_agrupar_por_ano_dentro_de_um_ano_nao_e_divergencia_E112():
    q = "Compare a temperatura média de SBGL em novembro de 2019 e novembro de 2024."
    a = nir(T, ["st:SBGL"], "avg", evidence={"measure": "temperatura", "stations": "SBGL", "calc": "média",
                                             "time": "em novembro de 2019 e novembro de 2024"})
    a["time"]["ranges"] = [{"start": "2019-11-01", "end": "2019-11-30"}, {"start": "2024-11-01", "end": "2024-11-30"}]
    b = json.loads(json.dumps(a))
    b["shape"]["group_by"] = ["year"]
    r, _ = run({"interpret_A": [a], "interpret_B": [b]}, q, AVG_ROW, table({"value": lit(26, XD), "n": lit(700)}), reread=False)
    assert r.status == Status.ANSWERED, r.answer_text


# ---------------- diálogo ----------------

Q_AMB = "Qual foi a temperatura de SBGL em 2020?"
MEAN = nir(T, ["st:SBGL"], "avg", "2020-01-01", "2020-12-31", evidence={"measure": "temperatura", "stations": "SBGL", "time": "em 2020"})
MAX = nir(T, ["st:SBGL"], "max", "2020-01-01", "2020-12-31", evidence={"measure": "temperatura", "stations": "SBGL", "time": "em 2020"})


def test_sim_diante_de_opcoes_pede_o_numero_sem_chamar_o_llm():
    user = ScriptedUser(["sim", "2"])
    r, llm = run({"interpret_A": [MEAN], "interpret_B": [MAX]}, Q_AMB, table({"value": lit(39, XD), "n": lit(8000)}), user=user, reread=False)
    assert r.status == Status.ANSWERED and "Qual delas?" in user.shown[1]
    assert [c["stage"] for c in llm.calls] == ["interpret_A", "interpret_B"] or sorted(c["stage"] for c in llm.calls) == ["interpret_A", "interpret_B"]


def test_correcao_repetida_nao_gera_nova_rodada():
    user = ScriptedUser(["quero a máxima", "quero a máxima", "cancelar"])
    r, llm = run({"interpret_A": [MEAN, MEAN], "interpret_B": [MAX, MAX]}, Q_AMB, user=user, reread=False)
    assert r.status == Status.NEEDS_CLARIFICATION and "já foi aplicada" in user.shown[2]
    assert len(llm.calls) == 4                                                   # duas rodadas, não três


# ---------------- memória de exemplos versionada ----------------

def test_memoria_versionada_substitui_remove_e_ignora_outro_catalogo(tmp_path):
    from metqa.knowledge import ExemplarStore
    (tmp_path / "active.json").write_text('{"active_version": "v9"}', encoding="utf-8")
    s = ExemplarStore.in_workspace(tmp_path, catalog="cat-1")
    assert s.path == tmp_path / "versions" / "v9" / "exemplars.jsonl"
    assert s.add("Quanto choveu em SBGL?", {"x": 1}, "user") and not s.add("quanto choveu em sbgl?", {"x": 1}, "user")
    assert s.add("Quanto choveu em SBGL?", {"x": 2}, "user")                      # correção posterior substitui
    assert [e["ir"] for e in s.items] == [{"x": 2}]
    again = ExemplarStore.in_workspace(tmp_path, catalog="cat-1")                  # o registro reaplicado dá o mesmo estado
    assert [e["ir"] for e in again.items] == [{"x": 2}] and again.search("Quanto choveu em SBGL?")
    assert ExemplarStore.in_workspace(tmp_path, catalog="cat-2").search("Quanto choveu em SBGL?") == []
    assert again.remove(again.items[0]["id"], "interpretação errada", "revisor") and again.items == []
    assert [e.get("event") for e in ExemplarStore.in_workspace(tmp_path).log] == ["added", "added", "superseded", "removed"]


# ---------------- planejador de N partes (plano, D5) ----------------

def test_o_mesmo_mes_em_dois_anos_com_agrupamento_por_ano_compara_E111():
    """E111/E113/E114 do novo_b: 'junho ... em 2018 e em 2023' vinha com group_by year em cada janela (COMPARISON_SHAPE)."""
    q = "O QNH mínimo de SBGL em junho foi quanto em 2018 e em 2023?"
    ir = nir("met:PressureQNH", ["st:SBGL"], "min", group_by=["year"],
             evidence={"measure": "QNH", "stations": "SBGL", "calc": "mínimo", "time": "em junho foi quanto em 2018 e em 2023"})
    ir["time"]["ranges"] = [{"start": "2018-06-01", "end": "2018-06-30"}, {"start": "2023-06-01", "end": "2023-06-30"}]
    r, _ = run(both(ir), q, table({"value": lit(1006.7, XD), "n": lit(700)}), table({"value": lit(1010.7, XD), "n": lit(700)}), reread=False)
    assert r.status == Status.ANSWERED, r.answer_text
    assert "Maior em 01/06/2023 a 30/06/2023: 1.010,7 contra 1.006,7 (diferença de 4 hPa)." in r.answer_text


def test_quatro_periodos():
    q = "Qual foi a temperatura média de SBGL em 2016, 2017, 2018 e 2019?"
    ir = nir(T, ["st:SBGL"], "avg", evidence={"measure": "temperatura", "stations": "SBGL", "calc": "média", "time": "em 2016, 2017, 2018 e 2019"})
    ir["time"]["ranges"] = [{"start": f"{y}-01-01", "end": f"{y}-12-31"} for y in (2016, 2017, 2018, 2019)]
    rows = [table({"value": lit(v, XD), "n": lit(8000)}) for v in (25.1, 25.9, 24.8, 25.0)]
    r, _ = run(both(ir), q, *rows, reread=False)
    assert r.status == Status.ANSWERED and "Maior em 01/01/2017 a 31/12/2017: 25,9; menor em 01/01/2018 a 31/12/2018: 24,8 (diferença de 1,1 °C)." in r.answer_text


def test_dias_com_condicao_em_duas_estacoes_viram_duas_partes():
    q = "Em 2020, SBGL ou SBSP teve mais dias com máxima acima de 35 °C?"
    ir = nir(T, ["st:SBGL", "st:SBSP"], "count", "2020-01-01", "2020-12-31", count_of="days",
             daily={"agg": "max", "op": ">", "value": 35, "unit": "unit:DEG_C"},
             evidence={"measure": "máxima", "stations": "SBGL ou SBSP", "calc": "mais dias", "conditions": "acima de 35 °C", "time": "Em 2020"})
    r, _ = run(both(ir), q, table({"value": lit(12), "n": lit(366)}), table({"value": lit(3), "n": lit(366)}), reread=False)
    assert r.status == Status.ANSWERED, r.answer_text
    assert "- SBGL: 12 dias em SBGL" in r.answer_text and "Maior em SBGL: 12 contra 3 (diferença de 9)." in r.answer_text


def test_cinco_periodos_e_demais():
    ir = nir(T, ["st:SBGL"], "avg", evidence={"measure": "temperatura", "stations": "SBGL", "calc": "média"})
    ir["time"]["ranges"] = [{"start": f"{y}-01-01", "end": f"{y}-12-31"} for y in range(2016, 2021)]
    r, _ = run(both(ir), "Temperatura média de SBGL em 2016, 2017, 2018, 2019 e 2020?", reread=False)
    assert r.status in (Status.REJECTED, Status.UNSUPPORTED)
