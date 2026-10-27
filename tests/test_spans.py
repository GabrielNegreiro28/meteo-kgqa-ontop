"""Analisadores determinísticos da pergunta (pipeline/spans.py): o que tem gramática fechada é lido por código, sem LLM."""
import glob
import re
from datetime import date
from decimal import Decimal

import pytest
import yaml

from pipeline.spans import MONTHS, read

D = date


@pytest.mark.parametrize("q, windows", [
    # o defeito medido no novo_a (E07, E11, E43): dia por extenso virava o mês inteiro
    ("Qual foi a visibilidade mínima, em metros, em SBGL no dia 15 de fevereiro de 2024?", [(D(2024, 2, 15), D(2024, 2, 15))]),
    ("Qual foi a temperatura máxima do ar em SBGO em 14 de outubro de 2019?", [(D(2019, 10, 14), D(2019, 10, 14))]),
    ("qual a temperatua maxima em sbpv no dia 13 de março de 2021?", [(D(2021, 3, 13), D(2021, 3, 13))]),
    ("Quanto choveu em SBGR no dia 19/01/2024?", [(D(2024, 1, 19), D(2024, 1, 19))]),
    ("Qual foi a temperatura média por estação entre 03/03/2026 e 05/03/2026?", [(D(2026, 3, 3), D(2026, 3, 5))]),
    ("Preciso da média do QNH de SBCF entre 1º e 15 de setembro de 2022.", [(D(2022, 9, 1), D(2022, 9, 15))]),
    ("Quantas horas de agosto de 2024 em SBBR tiveram umidade relativa abaixo de 20%?", [(D(2024, 8, 1), D(2024, 8, 31))]),
    ("Qual foi a chuva total de SBPA entre março e maio de 2021?", [(D(2021, 3, 1), D(2021, 5, 31))]),
    ("Qual foi a chuva total de SBGL no primeiro semestre de 2022?", [(D(2022, 1, 1), D(2022, 6, 30))]),
    ("Qual foi a temperatura média de SBCF no primeiro trimestre de 2023?", [(D(2023, 1, 1), D(2023, 3, 31))]),
    # verão austral meteorológico (D-93): o de 2022 começa em dezembro de 2021; a paráfrase explícita dá a MESMA janela
    ("Qual foi a temperatura média em SBSP no verão de 2022?", [(D(2021, 12, 1), D(2022, 2, 28))]),
    ("Qual foi a temperatura média do ar em SBBR no verão de 2022, considerando dezembro de 2021 a fevereiro de 2022?",
     [(D(2021, 12, 1), D(2022, 2, 28))]),
    ("Como variou o QNH médio anual de SBME de 2016 a 2025?", [(D(2016, 1, 1), D(2025, 12, 31))]),
    ("Qual foi a temperatura média anual de SBSV entre 2016 e 2025?", [(D(2016, 1, 1), D(2025, 12, 31))]),
    ("Em quantos dias de 2020 a temperatura máxima em SBBR chegou a 33 °C ou mais?", [(D(2020, 1, 1), D(2020, 12, 31))]),
    # comparação: janelas disjuntas ficam separadas
    ("SBPA esteve mais quente em janeiro de 2016 ou em janeiro de 2025?", [(D(2016, 1, 1), D(2016, 1, 31)), (D(2025, 1, 1), D(2025, 1, 31))]),
    ("A mediana da visibilidade em SBSC foi maior em abril ou em outubro de 2021?", [(D(2021, 4, 1), D(2021, 4, 30)), (D(2021, 10, 1), D(2021, 10, 31))]),
])
def test_janelas_de_calendario(q, windows):
    assert read(q).windows == windows


def test_parte_do_dia_fim_de_semana_instante_e_data_relativa():
    r = read("Em SBJV, qual foi a visibilidade média de madrugada, entre meia-noite e antes das seis, ao longo de 2023?")
    assert r.hours == (0, 6) and r.windows == [(D(2023, 1, 1), D(2023, 12, 31))]       # "meia-noite" não é a parte do dia "noite"
    assert read("Qual a temperatura média de SBGR durante a noite em 2019?").hours == (18, 24)
    assert read("Qual a velocidade média do vento em SBNT nos fins de semana de 2024?").weekdays == frozenset({5, 6})
    inst = next(f for f in read("Qual era a temperatura na Estação Vale Verde em 05/03/2026 às 12h?").time if f.kind == "instant")
    assert inst.start == D(2026, 3, 5) and inst.hour == (12, 0)
    assert read("Vai chover em SBSP amanhã?").relative
    assert not read("Qual foi a maior rajada de vento registrada em SBPA em 2021?").relative


def test_mes_sem_ano_e_lido_mas_nao_vira_janela():
    r = read("Me passa a média da umidade relativa de julho.")
    assert r.windows == [] and [f.kind for f in r.time] == ["month_any"]


def test_maior_nao_e_maio_e_ano_nao_e_limiar():
    r = read("Quais foram as 3 estações com maior temperatura média em 2022?")
    assert [f.kind for f in r.time] == ["year"]
    assert [q.value for q in r.quantities] == [Decimal(3)]                             # 2022 é ano, não número da pergunta


@pytest.mark.parametrize("q, expected", [
    ("Em quantas horas a visibilidade em SBSP ficou abaixo de 1000 metros em 2018?", [(Decimal(1000), "M")]),
    ("Quantas horas de agosto de 2024 em SBBR tiveram umidade relativa abaixo de 20%?", [(Decimal(20), "PERCENT")]),
    ("Em quantos dias de 2020 a temperatura máxima em SBBR chegou a 33 °C ou mais?", [(Decimal(33), "DEG_C")]),
    ("Quantas vezes o vento passou de 15 nós em SBNF em 2017?", [(Decimal(15), "KN")]),
    ("Quantas horas o QNH em SBVT ficou abaixo de 1010 hPa em 2019?", [(Decimal(1010), "HectoPA")]),
    ("Em quantas horas a visibilidade ficou abaixo de 1,5 km?", [(Decimal("1.5"), "KiloM")]),
    # unidade SEM número: é ela que confere a grandeza (minutos -> duração; mm -> soma de chuva; metros -> visibilidade em m)
    ("Quantos minutos de chuva, somando todas as horas, foram registrados em SBFZ em 2020?", [(None, "MIN")]),
    ("sbcg, quantos mm choveu em janeiro de 2024?", [(None, "MilliM")]),
    ("Qual foi a visibilidade mínima, em metros, em SBGL no dia 15 de fevereiro de 2024?", [(None, "M")]),
])
def test_quantidades_e_unidades(q, expected):
    assert [(x.value, x.unit) for x in read(q).quantities] == expected


def test_trecho_aponta_para_o_texto_da_pergunta():
    r = read("Qual foi a visibilidade mínima, em metros, em SBGL no dia 15 de fevereiro de 2024?")
    for f in [*r.time, *r.quantities]:
        assert r.text[f.pos[0]:f.pos[1]].strip() == f.span


_TIME_WORD = re.compile(r"\b(?:" + "|".join(MONTHS) + r"|(?:19|20)\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?|verao|inverno|outono|primavera|trimestre|"
                        r"semestre|madrugada|manha|tarde|noite|sabados?|domingos?)\b")
# o que fica SEM leitura de propósito: vago demais para virar janela (vai pedir esclarecimento, não chutar)
_UNREAD_ON_PURPOSE = {"Qual foi a temperatura média da Estação Vale Verde em toda a semana?"}


def _all_questions() -> list[str]:
    out = []
    for f in sorted(glob.glob("eval/questions*.yaml") + glob.glob("eval/frozen/*/questions.yaml")):
        data = yaml.safe_load(open(f, encoding="utf-8"))
        items = data.get("questions", data) if isinstance(data, dict) else data
        out += [q["question"] for q in items if isinstance(q, dict) and q.get("question")]
    return list(dict.fromkeys(out))


def test_toda_palavra_de_tempo_de_todas_as_perguntas_e_lida():
    """Varredura das perguntas de TODOS os conjuntos: nenhuma palavra de tempo sobra sem leitura (sobrar é o que virava erro silencioso)."""
    qs = _all_questions()
    assert len(qs) > 200
    left = {}
    for q in qs:
        r = read(q)
        cov = r.covered()
        miss = [m.group() for m in _TIME_WORD.finditer(r.text) if not any(a <= m.start() and m.end() <= b for a, b in cov)]
        if miss and q not in _UNREAD_ON_PURPOSE:
            left[q] = miss
    assert not left
