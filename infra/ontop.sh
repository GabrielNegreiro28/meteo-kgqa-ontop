#!/usr/bin/env bash
# Sobe o endpoint SPARQL do Ontop em 127.0.0.1:8080 (grafo virtual sobre o PostgreSQL).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Duser.timezone=UTC"
ONTOP=${ONTOP_HOME:-/home/claude/tools/ontop}/ontop
LOG=${ONTOP_LOG:-/home/claude/metdata/ontop.log}
case "${1:-start}" in
  start)
    python3 "$ROOT/mapping/build_mapping.py" > "$ROOT/mapping/met.obda"
    nohup "$ONTOP" endpoint -t "$ROOT/ontology/met.ttl" -m "$ROOT/mapping/met.obda" -p "$ROOT/mapping/met.properties" \
      --port 8080 --cors-allowed-origins=http://127.0.0.1 > "$LOG" 2>&1 &
    echo $! > /home/claude/metdata/ontop.pid
    for i in $(seq 1 60); do curl -s -o /dev/null http://127.0.0.1:8080/sparql && { echo "ontop pronto"; exit 0; }; sleep 2; done
    echo "ontop não respondeu; ver $LOG"; exit 1 ;;
  stop) kill "$(cat /home/claude/metdata/ontop.pid)" 2>/dev/null || true ;;
esac
