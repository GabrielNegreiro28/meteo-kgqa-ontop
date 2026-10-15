#!/usr/bin/env bash
# Reconstrói o grafo virtual a partir dos arquivos .npz verificados (gerados por prof/pack.py no computador de origem).
# Pré-requisitos: Python com requirements.txt + pgserver + psycopg; Java 17+; Ontop CLI em $ONTOP_HOME
# com o driver postgresql-*.jar em $ONTOP_HOME/jdbc.
#   PACK=/caminho/para/pack ./infra/rebuild.sh
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PACK=${PACK:-/home/claude/metdata/pack}
DUCK=${DUCK:-/home/claude/metdata/met.duckdb}
PG="host=127.0.0.1 port=5433 user=postgres dbname=met"

echo "1/7 tabelas brutas (DuckDB)";        python3 "$ROOT/ingest/load_raw.py" "$PACK" "$DUCK"
echo "2/7 camada limpa + quarentena";      python3 "$ROOT/ingest/transform.py" "$DUCK"
echo "3/7 PostgreSQL";                     "$ROOT/infra/pg.sh" start || true
python3 -c "import psycopg; c=psycopg.connect('host=127.0.0.1 port=5433 user=postgres dbname=postgres', autocommit=True)
if not c.execute(\"SELECT 1 FROM pg_database WHERE datname='met'\").fetchone(): c.execute('CREATE DATABASE met')"
echo "4/7 exportação";                     python3 "$ROOT/ingest/export_pg.py" "$DUCK" "$PG"
echo "5/7 sensores virtuais e usuário";    python3 "$ROOT/ingest/finalize_pg.py" "$PG"
echo "6/7 chaves e permissões";            python3 "$ROOT/ingest/constraints.py" "$PG"
echo "7/7 Ontop";                          "$ROOT/infra/ontop.sh" stop; sleep 2; "$ROOT/infra/ontop.sh" start
echo "verificação:"; cd "$ROOT" && python3 -m pytest -q
