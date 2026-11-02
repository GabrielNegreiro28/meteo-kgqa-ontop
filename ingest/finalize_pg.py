"""Passos finais no PostgreSQL depois da exportação: sensores virtuais e usuário somente leitura.
Uso: python ingest/finalize_pg.py ["conninfo"]
"""
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ontology.catalog import quantities  # noqa: E402

PG = sys.argv[1] if len(sys.argv) > 1 else "host=127.0.0.1 port=5433 user=postgres dbname=met"

with psycopg.connect(PG, autocommit=True) as c:
    # Sensores virtuais: um por (estação, variável) que tenha ao menos uma observação.
    c.execute("DROP TABLE IF EXISTS station_sensor")
    # do catálogo de grandezas; nas camadas de nuvem, só as estações em que a coluna da grandeza tem valor
    sel = " UNION ALL ".join(f"SELECT DISTINCT sigla, '{q.sensor}' AS var FROM {q.table}"
                             + ("" if q.column == "value" else f" WHERE {q.column} IS NOT NULL") for q in quantities().values())
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
