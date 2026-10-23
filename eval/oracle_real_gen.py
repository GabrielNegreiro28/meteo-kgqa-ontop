"""Oráculo do conjunto de GENERALIZAÇÃO (`questions_real_gen.yaml`, RG01–RG24).

Escrito para NÃO favorecer o prompt v6: a maioria das perguntas são formas simples ou cobradas de jeitos que as regras de linguagem
não foram desenhadas para reconhecer; há sondas deliberadas de buracos conhecidos do v6 (superlativo no SINGULAR sobre grupos:
RG17 e RG18) e uma comparação entre estações (RG09). Mesmo caminho independente dos outros oráculos (pandas sobre a camada limpa).
NUNCA use este conjunto para ajustar regra ou prompt.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from eval.oracle_real import between, load, utc

Y = lambda y: (date(y, 1, 1), date(y, 12, 31))


def RG01():       # temperatura média de SBGL em janeiro de 2022
    d = between(load("obs_air_temp", "SBGL"), date(2022, 1, 1), date(2022, 1, 31))
    return [(d.value.mean(), len(d))]


def RG02():       # maior rajada de SBPA em 2021
    d = between(load("obs_wind_gust", "SBPA"), *Y(2021))
    return [(d.value.max(), len(d))]


def RG03():       # menor pressão QNH de SBBR em 2020
    d = between(load("obs_qnh", "SBBR"), *Y(2020))
    return [(d.value.min(), len(d))]


def RG04():       # chuva total de SBFZ em 2018
    d = between(load("obs_precip", "SBFZ"), *Y(2018))
    return [(d.value.sum(), len(d))]


def RG05():       # temperatura de SBPA em 10/03/2021 às 15h
    d = load("obs_air_temp", "SBPA")
    x = d[d.t_local == pd.Timestamp("2021-03-10 15:00:00")]
    return [(v,) for v in x.value]


def RG06():       # medições de temperatura acima de 35 graus em SBCY em 2019
    d = between(load("obs_air_temp", "SBCY"), *Y(2019))
    return [(int((d.value > 35).sum()),)]


def RG07():       # umidade relativa média de SBRF entre 01/06/2022 e 30/06/2022
    d = between(load("obs_rel_humidity", "SBRF"), date(2022, 6, 1), date(2022, 6, 30))
    return [(d.value.mean(), len(d))]


def RG08():       # temperatura máxima de SBSV em 25/12/2023
    d = between(load("obs_air_temp", "SBSV"), date(2023, 12, 25), date(2023, 12, 25))
    return [(d.value.max(), len(d))]


def RG09():       # qual choveu mais em 2020, SBRF ou SBSV (os dois totais)
    out = []
    for s in ("SBRF", "SBSV"):
        d = between(load("obs_precip", s), *Y(2020))
        out.append((s, d.value.sum(), len(d)))
    return out


def RG10():       # quando foi registrada a menor temperatura de SBCT em 2019
    d = between(load("obs_air_temp", "SBCT"), *Y(2019))
    m = d.value.min()
    return [(m, utc(r.t_utc)) for r in d[d.value == m].itertuples()]


def RG11():       # quantas vezes o vento passou de 25 nós em SBGL em 2020
    d = between(load("obs_wind_speed", "SBGL"), *Y(2020))
    return [(int((d.value > 25).sum()),)]


def RG12():       # pressão média de SBKP em 2022
    d = between(load("obs_qnh", "SBKP"), *Y(2022))
    return [(d.value.mean(), len(d))]


def RG13():       # precipitação mensal de SBCT em 2019
    d = between(load("obs_precip", "SBCT"), *Y(2019))
    d = d.copy()
    d["month"] = [x.month for x in d.local_date]
    g = d.groupby("month").value.agg(["sum", "count"])
    return [(int(m), r["sum"], int(r["count"])) for m, r in g.iterrows()]


def RG14():       # temperatura média anual de SBSV de 2016 a 2025
    d = load("obs_air_temp", "SBSV").copy()
    d["year"] = [x.year for x in d.local_date]
    g = d.groupby("year").value.agg(["mean", "count"])
    return [(int(y), r["mean"], int(r["count"])) for y, r in g.iterrows()]


def RG15():       # as 5 estações com maior velocidade média do vento em 2021
    d = between(load("obs_wind_speed"), *Y(2021))
    g = d.groupby("sigla").value.agg(["mean", "count"]).sort_values("mean", ascending=False).head(5)
    return [(s, r["mean"], int(r["count"])) for s, r in g.iterrows()]


def RG16():       # medições de vento de cada cabeceira de SBCF em 2022
    d = between(load("obs_wind_speed", "SBCF", ", runway"), *Y(2022))
    d = d[d.runway.notna()]
    return [(k, int(v)) for k, v in d.groupby("runway").size().items()]


def RG17():       # a direção de vento mais frequente em SBRJ em 2020 (SINGULAR, sem número)
    d = between(load("obs_wind_dir", "SBRJ"), *Y(2020))
    c = d.groupby("value").size().sort_values(ascending=False, kind="stable")
    return [(int(c.index[0]), int(c.iloc[0]))]


def RG18():       # o dia mais chuvoso de 2022 em SBPA (SINGULAR, sem número)
    d = between(load("obs_precip", "SBPA"), *Y(2022))
    g = d.groupby("local_date").value.agg(["sum", "count"]).sort_values("sum", ascending=False, kind="stable")
    return [(g.index[0].isoformat(), g.iloc[0]["sum"], int(g.iloc[0]["count"]))]


def RG24():       # ponto de orvalho médio de SBEG em 2021
    d = between(load("obs_dew_point", "SBEG"), *Y(2021))
    return [(d.value.mean(), len(d))]


def expected(qid: str):
    fn = globals().get(qid)
    return fn() if fn else None
