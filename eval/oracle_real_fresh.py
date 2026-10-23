"""Oráculo do conjunto NOVO de perguntas reais (`questions_real_fresh.yaml`), escrito depois de todas as correções e antes de rodar qualquer LLM.

Mesmo caminho independente de eval/oracle_real.py (pandas sobre a camada limpa do DuckDB, sem SPARQL, sem mapeamento, sem
PostgreSQL). As perguntas exercitam a forma do resultado do prompt v6 (agrupamento, atributo, ranking), formas simples que já
funcionavam e recusas. NUNCA use este conjunto para ajustar regra ou prompt: ele existe para uma medida limpa.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from eval.oracle_real import between, load, utc

Y = lambda y: (date(y, 1, 1), date(y, 12, 31))


def _month_year(d):
    d = d.copy()
    d["year"] = [x.year for x in d.local_date]
    d["month"] = [x.month for x in d.local_date]
    return d


def RF01():       # precipitação total de SBSP em cada mês de 2021
    d = _month_year(between(load("obs_precip", "SBSP"), *Y(2021)))
    g = d.groupby(["year", "month"]).value.agg(["sum", "count"])
    return [(int(y), int(m), r["sum"], int(r["count"])) for (y, m), r in g.iterrows()]


def RF02():       # as 3 estações com maior temperatura média em 2022
    d = between(load("obs_air_temp"), *Y(2022))
    g = d.groupby("sigla").value.agg(["mean", "count"]).sort_values("mean", ascending=False).head(3)
    return [(s, r["mean"], int(r["count"])) for s, r in g.iterrows()]


def RF03():       # velocidade média do vento em cada cabeceira de SBPA em 2020
    d = between(load("obs_wind_speed", "SBPA", ", runway"), *Y(2020))
    d = d[d.runway.notna()]
    g = d.groupby("runway").value.agg(["mean", "count"])
    return [(k, r["mean"], int(r["count"])) for k, r in g.iterrows()]


def RF04():       # maior velocidade do vento em SBCT em 2020 e em qual cabeceira
    d = between(load("obs_wind_speed", "SBCT", ", runway"), *Y(2020))
    m = d.value.max()
    return [(row.runway, m, utc(row.t_utc)) for row in d[d.value == m].itertuples()]


def RF05():       # precipitação total de SBRJ por dia em março de 2022
    d = between(load("obs_precip", "SBRJ"), date(2022, 3, 1), date(2022, 3, 31))
    g = d.groupby("local_date").value.agg(["sum", "count"])
    return [(k.isoformat(), r["sum"], int(r["count"])) for k, r in g.iterrows()]


def RF06():       # quantas medições de pressão SBCF registrou em cada ano
    d = load("obs_qnh", "SBCF")
    d["year"] = [x.year for x in d.local_date]
    return [(int(y), int(n)) for y, n in d.groupby("year").size().items()]


def RF07():       # as duas direções de vento mais frequentes em SBFZ em 2021 (sem empate entre o 2º e o 3º lugar: verificado)
    d = between(load("obs_wind_dir", "SBFZ"), *Y(2021))
    c = d.groupby("value").size().sort_values(ascending=False, kind="stable")
    return [(int(k), int(v)) for k, v in c.head(2).items()]


def RF08():       # umidade relativa mínima de SBRJ, SBGL e SBSP em 2019, por estação
    d = pd.concat([between(load("obs_rel_humidity", s), *Y(2019)) for s in ("SBRJ", "SBGL", "SBSP")])
    g = d.groupby("sigla").value.agg(["min", "count"])
    return [(s, r["min"], int(r["count"])) for s, r in g.iterrows()]


def RF09():       # temperatura média de SBKP em 2019
    d = between(load("obs_air_temp", "SBKP"), *Y(2019))
    return [(d.value.mean(), len(d))]


def RF10():       # quanto choveu em SBSV no dia 11/05/2022
    d = between(load("obs_precip", "SBSV"), date(2022, 5, 11), date(2022, 5, 11))
    return [(d.value.sum(), len(d))]


def RF11():       # quantas medições de visibilidade abaixo de 800 m SBSP teve em 2019
    d = between(load("obs_visibility", "SBSP"), *Y(2019))
    return [(int((d.value < 800).sum()),)]


def expected(qid: str):
    fn = globals().get(qid)
    return fn() if fn else None
