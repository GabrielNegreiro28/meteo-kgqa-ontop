"""Exporta a camada limpa do DuckDB (schema clean) para o PostgreSQL consultado pelo Ontop.

Cada tabela ganha `tmin` = minutos desde 1970-01-01 UTC (inteiro), usado nos templates de IRI do
mapeamento: junções entre observação, boletim e instante viram igualdade de inteiros.
Toda tabela de observação ganha também a hora e o dia da semana locais (UTC−3, D-85), colunas geradas a partir de `tmin` e `local_date`,
que o mapeamento expõe como met:localHour e met:localWeekday.
Uso: python ingest/export_pg.py <duckdb> "<conninfo postgres>"
     python ingest/export_pg.py --local-time ["<conninfo>"]      # só acrescenta as colunas locais a um banco já carregado
"""
import os, sys, time
from pathlib import Path

import duckdb, psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ontology.catalog import quantities, tables  # noqa: E402

DUCK = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MET_HOME", "/home/claude/metdata") + "/met.duckdb"
PG = sys.argv[2] if len(sys.argv) > 2 else "host=127.0.0.1 port=5433 user=postgres dbname=met"
TMP = os.environ.get("MET_HOME", "/home/claude/metdata") + "/_export.csv"

WIND = ["wind_speed", "wind_dir", "wind_gust"]          # com cabeceira (e condição, na velocidade)
# instantâneas de tabela própria e sem cabeceira, do catálogo de grandezas
SCALAR = [q.sensor for q in quantities().values() if q.table == f"obs_{q.sensor}" and not q.accumulated and q.sensor not in WIND]
T = "epoch(t_utc)::BIGINT // 60 AS tmin, strftime(t_utc, '%Y-%m-%d %H:%M:%S+00') AS t_utc"
TABLES = {
    "station": ("sigla text PRIMARY KEY", "SELECT sigla FROM clean.station"),
    "report": ("sigla text, tmin integer, t_utc timestamptz, local_date date, is_hourly boolean",
               f"SELECT sigla, {T}, local_date, is_hourly FROM clean.report"),
    **{f"obs_{n}": ("sigla text, tmin integer, t_utc timestamptz, local_date date, value numeric, seq smallint, multi boolean, src_row bigint",
                    f"SELECT sigla, {T}, local_date, value, seq, multi, src_row FROM clean.obs_{n}") for n in SCALAR},
    "obs_wind_speed": ("sigla text, tmin integer, t_utc timestamptz, local_date date, runway text, value numeric, condition text, seq smallint, multi boolean, src_row bigint",
                       f"SELECT sigla, {T}, local_date, runway, value, condition, seq, multi, src_row FROM clean.obs_wind_speed"),
    **{f"obs_{n}": ("sigla text, tmin integer, t_utc timestamptz, local_date date, runway text, value numeric, seq smallint, multi boolean, src_row bigint",
                    f"SELECT sigla, {T}, local_date, runway, value, seq, multi, src_row FROM clean.obs_{n}") for n in WIND[1:]},
    **{f"obs_{n}": ("sigla text, tmin integer, t_utc timestamptz, start_utc timestamptz, local_date date, value numeric, seq smallint, multi boolean, src_row bigint",
                    f"SELECT sigla, {T}, strftime(start_utc, '%Y-%m-%d %H:%M:%S+00'), local_date, value, seq, multi, src_row FROM clean.obs_{n}")
       for n in [q.sensor for q in quantities().values() if q.accumulated]},
    "obs_cloud_layer": ("sigla text, tmin integer, t_utc timestamptz, local_date date, okta smallint, sky_obscured boolean, base_m integer, genus text, cloud_movement text, seq smallint, src_row bigint",
                        f"SELECT sigla, {T}, local_date, okta, sky_obscured, base_m, genus, movement AS cloud_movement, seq, src_row FROM clean.obs_cloud_layer"),
    "quarantine": ("source text, row_id bigint, sigla text, t_local timestamp, col text, raw text, reason text",
                   "SELECT * FROM clean.quarantine"),
}
assert {t for t in TABLES if t.startswith("obs_")} == set(tables()), "tabelas de observação fora do catálogo de grandezas"

# hora local do instante da leitura (fim do intervalo, nos acumulados) e dia da semana de local_date: 0 = segunda (1970-01-05) ... 6 = domingo
LOCAL_TIME = ("local_hour smallint GENERATED ALWAYS AS (((tmin - 180) / 60) % 24) STORED",
              "local_weekday smallint GENERATED ALWAYS AS ((local_date - DATE '1970-01-05') % 7) STORED")


def add_local_time(pg, name):
    pg.execute(f"ALTER TABLE {name} " + ", ".join(f"ADD COLUMN IF NOT EXISTS {c}" for c in LOCAL_TIME))


def main():
    if sys.argv[1:2] == ["--local-time"]:
        with psycopg.connect(sys.argv[2] if len(sys.argv) > 2 else PG, autocommit=True) as pg:
            for name in (n for n in TABLES if n.startswith("obs_")):
                t0 = time.time()
                add_local_time(pg, name)
                pg.execute(f"ANALYZE {name}")
                print(f"{name}: colunas locais em {time.time()-t0:.0f}s", flush=True)
        return
    only = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
    duck = duckdb.connect(DUCK, read_only=True)
    with psycopg.connect(PG, autocommit=True) as pg:
        pg.execute("SET TIME ZONE 'UTC'")
        for name, (ddl, select) in TABLES.items():
            if only and name not in only:
                continue
            t0 = time.time()
            duck.execute(f"COPY ({select}) TO '{TMP}' (FORMAT CSV, HEADER false)")
            pg.execute(f"DROP TABLE IF EXISTS {name} CASCADE")
            pg.execute(f"CREATE UNLOGGED TABLE {name} ({ddl})")
            with pg.cursor() as cur, cur.copy(f"COPY {name} FROM STDIN (FORMAT CSV)") as cp, open(TMP, "rb") as fh:
                while chunk := fh.read(1 << 22):
                    cp.write(chunk)
            n = pg.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            expected = duck.execute(f"SELECT COUNT(*) FROM ({select})").fetchone()[0]
            assert n == expected, (name, n, expected)
            if name in ("obs_precip", "obs_precip_duration"):
                pg.execute(f"ALTER TABLE {name} ADD COLUMN tmin_start integer GENERATED ALWAYS AS (tmin - 60) STORED")
            if name.startswith("obs_"):
                add_local_time(pg, name)
            if name.startswith("obs_") or name == "report":
                # padrão dominante das consultas: estação + período de dias locais (PK cobre estação + instante)
                pg.execute(f"CREATE INDEX ON {name} (sigla, local_date)")
                pg.execute(f"CREATE INDEX ON {name} USING brin (t_utc)")
            pg.execute(f"ALTER TABLE {name} SET LOGGED")
            pg.execute(f"ANALYZE {name}")
            print(f"{name}: {n:,} linhas em {time.time()-t0:.0f}s", flush=True)
    os.remove(TMP)


if __name__ == "__main__":
    main()
