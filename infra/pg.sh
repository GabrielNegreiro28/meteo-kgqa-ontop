#!/usr/bin/env bash
# Sobe/para o PostgreSQL local (binários do pacote pgserver) escutando só em 127.0.0.1:5433.
set -euo pipefail
BIN=$(python3 -c "import pgserver,os;print(os.path.join(os.path.dirname(pgserver.__file__),'pginstall','bin'))")
DATA=${PGDATA_DIR:-/home/claude/metdata/pg}
case "${1:-start}" in
  start) runuser -u pgserver -- "$BIN/pg_ctl" -D "$DATA" -o "-h 127.0.0.1 -p 5433 -k $DATA -c shared_buffers=1GB -c work_mem=256MB -c max_parallel_workers_per_gather=2 -c statement_timeout=0 -c timezone=UTC" -l "$DATA/server.log" -w start ;;
  stop)  runuser -u pgserver -- "$BIN/pg_ctl" -D "$DATA" -m fast -w stop ;;
  status) runuser -u pgserver -- "$BIN/pg_ctl" -D "$DATA" status ;;
esac
