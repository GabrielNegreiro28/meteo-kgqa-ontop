"""MVP (`metqa/`) de ponta a ponta no GRAFO REAL (Ontop), com o LLM roteirizado devolvendo a interpretação NORMALIZADA (as duas leituras
concordam): a pipeline inteira (memória, leituras, validação no mundo fechado, concordância, risco, plano, compilação, motor, verificação, texto)
tem de dar o número do oráculo pandas. Inclui os dois casos de borda que derrubaram o leitor por regex na medição de 2026-10-28
("no ano de 2018." e "das 18h às 6h"): aqui eles não dependem de regra nenhuma. Não mede o LLM real (isso exige verba)."""
import json

import pytest

from kgqa.contract import Status
from kgqa.store import OntopBackend
from metqa.app import MetQA, Settings
from metqa.knowledge import DomainCatalog, ExemplarStore, OntologyLexicon
from metqa.presentation.render import num
from pipeline.llm import ScriptedLLM
from tests.test_metqa import nir
from tests.test_real_pipeline import needs_ontop

E = lambda **kw: kw
NIGHT = list(range(18, 24)) + list(range(0, 6))
CASES = {   # pergunta, interpretação normalizada, valor esperado (oráculo pandas; ver eval/frozen/*)
    "dia_por_extenso": ("Qual foi a visibilidade mínima, em metros, em SBGL no dia 15 de fevereiro de 2024?",
                        nir("met:PrevailingVisibility", ["st:SBGL"], "min", "2024-02-15",
                            evidence=E(measure="visibilidade", stations="SBGL", calc="mínima", time="no dia 15 de fevereiro de 2024")), 1000),
    "minutos_de_chuva": ("Quantos minutos de chuva, somando todas as horas, foram registrados em SBFZ em 2020?",
                         nir("met:PrecipitationDuration", ["st:SBFZ"], "sum", "2020-01-01", "2020-12-31",
                             evidence=E(measure="minutos de chuva", stations="SBFZ", calc="somando", time="em 2020")), 13959),
    "horas_com_chuva": ("Quantas horas com chuva houve em SBCY em 2022?",
                        nir("met:Precipitation", ["st:SBCY"], "count", "2022-01-01", "2022-12-31", count_of="hours",
                            conditions=[{"op": ">", "value": 0, "unit": "unit:MilliM"}],
                            evidence=E(measure="chuva", stations="SBCY", calc="Quantas horas", conditions="com chuva", time="em 2022")), 360),
    "quantos_mm": ("sbcg, quantos mm choveu em janeiro de 2024?",
                   nir("met:Precipitation", ["st:SBCG"], "sum", "2024-01-01", "2024-01-31",
                       evidence=E(measure="choveu", stations="sbcg", calc="quantos mm", time="em janeiro de 2024")), 64.1),
    "fins_de_semana": ("Qual a velocidade média do vento em SBNT nos fins de semana de 2024?",
                       nir("met:WindSpeed", ["st:SBNT"], "avg", "2024-01-01", "2024-12-31", weekdays=[5, 6],
                           evidence=E(measure="velocidade média do vento", stations="SBNT", calc="média", time="nos fins de semana de 2024")), 8.81),
    "madrugada": ("Quanto choveu em SBBE de madrugada em 2019?",
                  nir("met:Precipitation", ["st:SBBE"], "sum", "2019-01-01", "2019-12-31", hours=list(range(0, 6)),
                      evidence=E(measure="choveu", stations="SBBE", calc="Quanto", time="de madrugada em 2019")), 180.8),
    # casos de borda da medição de 2026-10-28 (novo_a_20261028, E03 e E48), sem regra nenhuma para eles
    "ano_antes_do_ponto": ("Quero a menor pressão QNH registrada em SBCR no ano de 2018.",
                           nir("met:PressureQNH", ["st:SBCR"], "min", "2018-01-01", "2018-12-31",
                               evidence=E(measure="pressão QNH", stations="SBCR", calc="menor", time="no ano de 2018")), 1002.9),
}


@pytest.fixture(scope="module")
def real():
    source = OntopBackend()
    return source, DomainCatalog.from_ontop(source)


def ask(real, question, ir, **kw):
    source, catalog = real
    a = json.dumps(ir, ensure_ascii=False)
    qa = MetQA(catalog, OntologyLexicon(catalog), ScriptedLLM({"interpret_A": [a], "interpret_B": [a]}), source, Settings(timeout_s=120),
               ExemplarStore(None))
    return qa.ask(question, **kw)


@needs_ontop
@pytest.mark.parametrize("case", sorted(CASES))
def test_mvp_answers_with_the_oracle_number(real, case):
    question, ir, expected = CASES[case]
    res = ask(real, question, ir)
    r = res.response
    assert r.status == Status.ANSWERED, (case, [d.message for d in r.diagnostics])
    assert num(expected) in r.answer_text, (case, r.answer_text)
    assert r.provenance.generated_sql                                          # o SQL que o Ontop gerou, para a procedência
    from semantics.trajectories import to_trajectory
    assert to_trajectory(res)["pipeline_status"] == "answered"                  # a trilha alimenta a evolução


@needs_ontop
def test_night_across_midnight_matches_the_oracle(real):
    """'das 18h às 6h' = horas locais {18..23, 0..5}. O oráculo (novo_a_20261028, E48) faz a média das leituras duplicadas de cada instante;
    o sistema mantém leituras distintas (D-87): diferença de limpeza já conhecida, de centésimos."""
    q = "Durante a noite, das 18h às 6h, qual foi a umidade relativa média de SBNF em julho de 2020?"
    ir = nir("met:RelativeHumidity", ["st:SBNF"], "avg", "2020-07-01", "2020-07-31", hours=NIGHT,
             evidence=E(measure="umidade relativa", stations="SBNF", calc="média", time="Durante a noite, das 18h às 6h … em julho de 2020"))
    ir["evidence"]["time"] = "das 18h às 6h"
    ir["evidence"]["period"] = "julho de 2020"
    r = ask(real, q, ir).response
    assert r.status == Status.ANSWERED, [d.message for d in r.diagnostics]
    value = float(r.results["results"]["bindings"][0]["value"]["value"])
    assert abs(value - 86.622) < 0.3 and "das 18h às 6h" in r.answer_text


@needs_ontop
def test_mvp_compares_two_periods(real):
    ir = nir("met:AirTemperature", ["st:SBPA"], "avg", evidence=E(measure="quente", stations="SBPA", calc="mais quente",
                                                                     time="janeiro de 2016 ou em janeiro de 2025"))
    ir["time"]["ranges"] = [{"start": "2016-01-01", "end": "2016-01-31"}, {"start": "2025-01-01", "end": "2025-01-31"}]
    r = ask(real, "SBPA esteve mais quente em janeiro de 2016 ou em janeiro de 2025?", ir).response
    assert r.status == Status.ANSWERED, [d.message for d in r.diagnostics]
    assert "25,63" in r.answer_text and "25,44" in r.answer_text and "Maior em" in r.answer_text


@needs_ontop
def test_zero_count_with_data_is_an_answer(real):
    """E84 do novo_b: nenhum boletim de SBMO com QNH < 1005 hPa em 2025 (oráculo: 0). É resposta, com a base, não 'sem registros'."""
    ir = nir("met:PressureQNH", ["st:SBMO"], "count", "2025-01-01", "2025-12-31", count_of="reports",
             conditions=[{"op": "<", "value": 1005, "unit": "unit:HectoPA"}],
             evidence=E(measure="QNH", stations="SBMO", calc="quantos boletins", conditions="abaixo de 1005 hPa", time="Em 2025"))
    r = ask(real, "Em 2025, quantos boletins de SBMO apresentaram QNH abaixo de 1005 hPa?", ir).response
    assert r.status == Status.ANSWERED, [d.message for d in r.diagnostics]
    assert r.answer_text.startswith("0 boletins de pressão QNH em SBMO") and "boletins no recorte)" in r.answer_text


@needs_ontop
def test_mvp_reads_the_value_at_an_instant(real):
    # 14/10/2019 14h local em SBGO: 35,4 °C no CSV original
    ir = nir("met:AirTemperature", ["st:SBGO"], instant="2019-10-14T14:00:00-03:00",
             evidence=E(measure="temperatura do ar", stations="SBGO", time="em 14/10/2019 às 14h"))
    r = ask(real, "Qual era a temperatura do ar em SBGO em 14/10/2019 às 14h?", ir).response
    assert r.status == Status.ANSWERED, [d.message for d in r.diagnostics]
    assert "35,4 °C" in r.answer_text and "14/10/2019 14:00" in r.answer_text
