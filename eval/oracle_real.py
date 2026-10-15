"""Oráculo para as perguntas sobre dados reais.

Caminho independente do que está sendo avaliado:
  avaliado: SPARQL → Ontop (mapeamento .obda) → SQL gerado → PostgreSQL
  oráculo : pandas sobre a camada limpa no DuckDB (sem SPARQL, sem mapeamento, sem PostgreSQL)
Detecta erros de mapeamento, unidades, tempo/fuso, semântica SPARQL e exportação.
NÃO detecta erros nas regras de limpeza (ambos partem da camada limpa); para isso há as âncoras
conferidas contra o CSV bruto (tests/test_real_anchors.py) e a reconciliação bruto = limpo + quarentena.

Os valores vêm como DOUBLE: o DuckDB 1.5.6 ordena DECIMAL errado em ORDER BY … LIMIT (D-18).
Todo filtro, ordenação e agregação é feito em pandas.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from functools import lru_cache

import duckdb
import pandas as pd

DB = "/home/claude/metdata/met.duckdb"


@lru_cache(maxsize=None)
def _con():
    return duckdb.connect(DB, read_only=True)


def load(table: str, sigla: str | None = None, extra: str = "") -> pd.DataFrame:
    where = f"WHERE sigla = '{sigla}'" if sigla else ""
    df = _con().execute(
        f"SELECT sigla, t_local, t_utc, local_date, CAST(value AS DOUBLE) AS value {extra} FROM clean.{table} {where}"
    ).df()
    df["local_date"] = pd.to_datetime(df["local_date"]).dt.date
    return df


def between(df, a: date, b: date):
    return df[(df.local_date >= a) & (df.local_date <= b)]


def utc(ts) -> datetime:
    return pd.Timestamp(ts).to_pydatetime().replace(tzinfo=timezone.utc)


def RD01():
    s = _con().execute("SELECT DISTINCT sigla FROM clean.obs_runway_temp").df()
    return [(x,) for x in sorted(s.sigla)]

def RD02():
    d = between(load("obs_precip", "SBBE"), date(2019, 1, 1), date(2019, 12, 31))
    return [(d.value.sum(), len(d))]

def RD03():
    d = load("obs_air_temp")
    m = d.value.max()
    r = d[d.value == m]
    return [(row.sigla, m, utc(row.t_utc)) for row in r.itertuples()]

def RD04():
    d = between(load("obs_precip", "SBGR"), date(2024, 1, 1), date(2024, 12, 31))
    s = d.groupby("local_date").value.sum()
    return [(k.isoformat(),) for k, v in s.items() if v > 50]

def RD08():
    d = between(load("obs_air_temp", "SBGR"), date(2015, 1, 1), date(2015, 12, 31))
    return [(len(d),)]

def RT01():
    d = between(load("obs_wind_speed", "SBGR", ", runway"), date(2019, 1, 1), date(2019, 12, 31))
    d = d[d.runway.notna()]
    return sorted(d.groupby("runway").size().items())

def RT02():
    d = between(load("obs_wind_gust", "SBGR", ", runway"), date(2019, 1, 1), date(2019, 12, 31))
    m = d.value.max()
    return [(row.runway, m, utc(row.t_utc)) for row in d[d.value == m].itertuples()]

def RT03():
    d = between(load("obs_visibility", "SBRF"), date(2022, 1, 1), date(2022, 12, 31))
    return [(d[d.value < 1000].t_local.nunique(),)]

def RT04():
    d = _con().execute("""SELECT t_local, local_date, genus FROM clean.obs_cloud_layer WHERE sigla = 'SBGL'""").df()
    d["local_date"] = pd.to_datetime(d["local_date"]).dt.date
    d = between(d, date(2023, 1, 1), date(2023, 12, 31))
    return [(d[d.genus == "CB"].t_local.nunique(),)]

def RT05():
    d = load("obs_air_temp", "SBBR")
    d["year"] = [x.year for x in d.local_date]
    g = d.groupby("year").value.agg(["mean", "count"]).sort_index()
    return [(int(y), r["mean"], int(r["count"])) for y, r in g.iterrows()]

def RT06():
    d = between(load("obs_qnh"), date(2020, 1, 1), date(2020, 12, 31))
    g = d.groupby("sigla").value.agg(["mean", "count"]).sort_values("mean", ascending=False).head(5)
    return [(s, r["mean"], int(r["count"])) for s, r in g.iterrows()]

def RT07():
    d = load("obs_precip", "SBGR")
    d = d[d.local_date == date(2024, 1, 19)]
    return [(d.value.sum(), len(d))]

def RT08():
    d = between(load("obs_rel_humidity", "SBBR"), date(2024, 9, 1), date(2024, 9, 30))
    return [(d.value.min(), len(d))]

def RT09():
    d = between(load("obs_dew_point", "SBEG"), date(2021, 1, 1), date(2021, 12, 31))
    return [(d.value.mean(), len(d))]

def RT12():
    d = between(load("obs_wind_dir", "SBGR"), date(2019, 1, 1), date(2019, 12, 31))
    c = d.groupby("value").size().sort_values(ascending=False)
    return [(int(k), int(v)) for k, v in c.head(3).items()]


def expected(qid: str):
    fn = globals().get(qid)
    return fn() if fn else None
