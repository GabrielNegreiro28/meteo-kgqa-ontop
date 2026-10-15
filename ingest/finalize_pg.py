"""Passos finais no PostgreSQL depois da exportação: sensores virtuais e usuário somente leitura.
Uso: python ingest/finalize_pg.py ["conninfo"]
"""
import sys
import psycopg

PG = sys.argv[1] if len(sys.argv) > 1 else "host=127.0.0.1 port=5433 user=postgres dbname=met"
OBS = {"air_temp": "air_temp", "wet_bulb": "wet_bulb", "dew_point": "dew_point", "rel_humidity": "rel_humidity",
       "runway_temp": "runway_temp", "qnh": "qnh", "visibility": "visibility", "wind_speed": "wind_speed",
       "wind_dir": "wind_dir", "wind_gust": "wind_gust", "precip": "precip", "precip_duration": "precip_duration",
       "cloud_layer": "cloud"}

with psycopg.connect(PG, autocommit=True) as c:
    # Sensores virtuais: um por (estação, variável) que tenha ao menos uma observação.
    c.execute("DROP TABLE IF EXISTS station_sensor")
    sel = " UNION ALL ".join(f"SELECT DISTINCT sigla, '{var}' AS var FROM obs_{t}" for t, var in OBS.items())
    c.execute(f"CREATE TABLE station_sensor AS {sel}")
    c.execute("ALTER TABLE station_sensor ADD PRIMARY KEY (sigla, var)")
    print("station_sensor:", c.execute("SELECT COUNT(*) FROM station_sensor").fetchone()[0])
    # Usuário do Ontop: só leitura, com teto de tempo por comando.
    c.execute("""DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kgqa_reader')
                 THEN CREATE ROLE kgqa_reader LOGIN; END IF; END $$""")
    c.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    c.execute("GRANT USAGE ON SCHEMA public TO kgqa_reader")
    c.execute("ALTER ROLE kgqa_reader SET default_transaction_read_only = on")
    c.execute("ALTER ROLE kgqa_reader SET statement_timeout = '60s'")
    print("kgqa_reader configurado (as permissões de leitura são aplicadas por constraints.py)")
