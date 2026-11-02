"""Defeitos achados na medição final (novo_c_20261102, docs/julgamento_novo_c_20261102_veredictos.yaml), reescritos com o LLM roteirizado e
estações do perfil de teste. Corrigidos depois da medição: o efeito não foi medido com o LLM real (sem verba)."""
from metqa.domain.contract import Status
from tests.test_metqa import nir
from tests.test_metqa_shapes import XD, lit, table
from tests.test_metqa_understanding import AVG_ROW, both, reasons, run

T, W = "met:AirTemperature", "met:WindSpeed"
NONE = {"local_hours": None, "weekdays": None, "instant": None}


def test_releitura_sem_os_dias_da_semana_nao_e_alarme_E250():
    ir = nir(W, ["st:SBGL"], "avg", "2017-01-01", "2017-12-31", weekdays=[6],
             evidence={"measure": "velocidade média do vento", "stations": "SBGL", "calc": "média", "time": "de 2017"})
    r, _ = run(both(ir, reread_time=[{"ranges": [{"start": "2017-01-01", "end": "2017-12-31"}], **NONE}]),
               "Aos domingos de 2017, qual foi a velocidade média do vento em SBGL, em nós?", AVG_ROW)
    assert r.status == Status.ANSWERED, r.answer_text


def test_releitura_de_cada_mes_em_doze_janelas_nao_e_alarme_E193():
    ir = nir(W, ["st:SBGL"], "max", "2023-01-01", "2023-12-31", group_by=["month"],
             evidence={"measure": "vento", "stations": "SBGL", "calc": "máxima", "time": "em cada mês de 2023"})
    months = [{"start": f"2023-{m:02d}-01", "end": f"2023-{m:02d}-28"} for m in range(1, 12)] + [{"start": "2023-12-01", "end": "2023-12-31"}]
    r, _ = run(both(ir, reread_time=[{"ranges": months, **NONE}]), "Qual foi a velocidade máxima do vento de SBGL em cada mês de 2023?",
               table({"year": lit(2023), "month": lit(1), "value": lit(30, XD), "n": lit(700)}))
    assert r.status == Status.ANSWERED, r.answer_text


def test_so_o_maior_de_cada_ano_numa_comparacao_nao_diverge_E212():
    a = nir("met:DewPointTemperature", ["st:SBGL"], "min", evidence={"measure": "ponto de orvalho", "stations": "SBGL", "calc": "mínimo",
                                                                      "time": "Em agosto ... em 2019 ou em 2025"})
    a["time"]["ranges"] = [{"start": "2019-08-01", "end": "2019-08-31"}, {"start": "2025-08-01", "end": "2025-08-31"}]
    b = {**a, "shape": {"group_by": ["year"], "order": {"direction": "desc", "limit": 1}, "attributes": []}}
    r, _ = run({"interpret_A": [a], "interpret_B": [b]}, "Em agosto, o ponto de orvalho mínimo de SBGL foi maior em 2019 ou em 2025?",
               AVG_ROW, table({"value": lit(12, XD), "n": lit(700)}), reread=False)
    assert r.status == Status.ANSWERED, r.answer_text


def test_sem_estacao_e_sem_periodo_pergunta_E228():
    ir = nir(T, [], "avg", evidence={"measure": "temperatura", "calc": "média"})
    r, _ = run(both(ir), "Qual foi a temperatura média?", reread=False)
    assert r.status == Status.NEEDS_CLARIFICATION and any("nem período" in x for x in reasons(r))


def test_empate_no_ranking_e_dito_E208():
    ir = nir("met:PrevailingVisibility", ["st:SBGL", "st:SBSP"], "min", "2018-07-01", "2018-07-31", group_by=["station"],
             order={"direction": "asc", "limit": 1},
             evidence={"measure": "visibilidade", "stations": "SBGL e SBSP", "calc": "menor", "time": "em julho de 2018"})
    st = lambda c: {"type": "uri", "value": f"https://example.org/kgqa-met/data/station/{c}"}
    r, _ = run(both(ir), "Entre SBGL e SBSP, qual teve a menor visibilidade predominante em julho de 2018?",
                 table({"station": st("SBSP"), "value": lit(100), "n": lit(779)}, {"station": st("SBGL"), "value": lit(100), "n": lit(700)}),
                 reread=False)
    assert "empate" in r.answer_text and "- SBSP: 100 m" in r.answer_text and "- SBGL: 100 m" in r.answer_text


def _vis_km(unit):
    ir = nir("met:PrevailingVisibility", ["st:SBGL"], "avg", "2021-10-01", "2021-10-31",
             evidence={"measure": "visibilidade predominante", "stations": "SBGL", "calc": "média", "time": "em outubro de 2021"})
    ir["shape"]["unit"] = unit
    return run(both(ir), "Qual foi a visibilidade predominante média de SBGL em outubro de 2021, em quilômetros?",
               table({"value": lit(18166.8, XD), "n": lit(700)}), reread=False)[0]


def test_resultado_na_unidade_pedida_E156():
    r = _vis_km("unit:KiloM")
    assert r.status == Status.ANSWERED and "18,17 km" in r.answer_text, r.answer_text
    assert r.units.get("value", "").endswith("/KiloM")


def test_unidade_pedida_de_outra_dimensao_nao_responde():
    assert _vis_km("unit:DEG_C").status != Status.ANSWERED


def test_estacao_citada_sem_registros_e_dita_E205():
    ir = nir("met:WindGust", ["st:SBGL", "st:SBSP"], "max", "2022-06-01", "2022-06-30",
             evidence={"measure": "rajada", "stations": "SBGL e SBSP", "calc": "máxima", "time": "em junho de 2022"})
    st = {"type": "uri", "value": "https://example.org/kgqa-met/data/station/SBGL"}
    r, _ = run(both(ir), "Compare a rajada máxima de SBGL e SBSP em junho de 2022.", table({"station": st, "value": lit(23, XD), "n": lit(2)}),
               reread=False)
    assert "- SBGL: 23 kt" in r.answer_text and "- SBSP: sem registros" in r.answer_text
