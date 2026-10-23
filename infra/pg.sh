#!/usr/bin/env bash
# Sobe/para o PostgreSQL local (binários do pacote pgserver) escutando só em 127.0.0.1:5433.
#   MET_HOME  diretório dos dados (padrão: /home/claude/metdata; no WSL use $HOME/metdata, FORA do OneDrive)
#   PY        Python que tem o pacote pgserver (padrão: python3)
# Como root, o PostgreSQL recusa subir: usa runuser -u pgserver. Como usuário comum, roda direto.
set -euo pipefail
MET_HOME=${MET_HOME:-/home/claude/metdata}
PY=${PY:-python3}
BIN=$("$PY" -c "import pgserver,os;print(os.path.join(os.path.dirname(pgserver.__file__),'pginstall','bin'))")
DATA=${PGDATA_DIR:-$MET_HOME/pg}
if [ "$(id -u)" = 0 ]; then RUN="runuser -u pgserver --"; else RUN=""; fi
case "${1:-start}" in
  init)  # cria o cluster uma vez (confiança local: só escuta em 127.0.0.1)
    if [ ! -f "$DATA/PG_VERSION" ]; then mkdir -p "$DATA"; $RUN "$BIN/initdb" -D "$DATA" -U postgres -A trust -E UTF8 >/dev/null; echo "cluster criado em $DATA"; fi ;;
  start) "$0" init
         $RUN "$BIN/pg_ctl" -D "$DATA" -o "-h 127.0.0.1 -p 5433 -k $DATA -c shared_buffers=1GB -c work_mem=256MB -c max_parallel_workers_per_gather=2 -c statement_timeout=0 -c timezone=UTC" -l "$DATA/server.log" -w start ;;
  stop)  $RUN "$BIN/pg_ctl" -D "$DATA" -m fast -w stop ;;
  status) $RUN "$BIN/pg_ctl" -D "$DATA" status ;;
esac
