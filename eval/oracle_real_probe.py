"""Oráculo do conjunto-sonda das correções do Codex (`questions_real_probe.yaml`, RP01–RP08).

Escrito DEPOIS das correções D-67/D-68/D-53..D-58 e ANTES de rodar qualquer LLM nele, para ver se as regras novas barram perguntas BOAS
(falso positivo) e se as recusas esperadas acontecem. É pequeno (8 perguntas) porque o saldo do ledger é de US$ 0,40: serve para achar
um problema, não para medir taxa de acerto. Mesmo autor das regras (viés conhecido). NUNCA use para ajustar regra ou prompt depois de medido.
Mesmo caminho independente dos outros oráculos (pandas sobre a camada limpa).
"""
from __future__ import annotations

from datetime import date

from eval.oracle_real import between, load


def RP01():       # temperatura média de SBCT em fevereiro de 2021
    d = between(load("obs_air_temp", "SBCT"), date(2021, 2, 1), date(2021, 2, 28))
    return [(d.value.mean(), len(d))]


def RP02():       # chuva total de SBGL no primeiro semestre de 2022
    d = between(load("obs_precip", "SBGL"), date(2022, 1, 1), date(2022, 6, 30))
    return [(d.value.sum(), len(d))]


def RP03():       # quantas vezes a temperatura passou de 35 graus em SBPA em 2019
    d = between(load("obs_air_temp", "SBPA"), date(2019, 1, 1), date(2019, 12, 31))
    return [(int((d.value > 35).sum()),)]


def RP05():       # o mês mais chuvoso de 2019 em SBFZ (SINGULAR, sem número)
    d = between(load("obs_precip", "SBFZ"), date(2019, 1, 1), date(2019, 12, 31)).copy()
    d["month"] = [x.month for x in d.local_date]
    g = d.groupby("month").value.agg(["sum", "count"]).sort_values("sum", ascending=False, kind="stable")
    return [(int(g.index[0]), g.iloc[0]["sum"], int(g.iloc[0]["count"]))]


def RP07():       # chuva total de SBPA entre março e maio de 2021
    d = between(load("obs_precip", "SBPA"), date(2021, 3, 1), date(2021, 5, 31))
    return [(d.value.sum(), len(d))]


def RP08():       # umidade relativa média de SBGL em 2018 (controle: ano inteiro, sem recorte)
    d = between(load("obs_rel_humidity", "SBGL"), date(2018, 1, 1), date(2018, 12, 31))
    return [(d.value.mean(), len(d))]


def expected(qid: str):
    fn = globals().get(qid)
    return fn() if fn else None
