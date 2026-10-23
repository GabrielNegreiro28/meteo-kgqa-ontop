#!/usr/bin/env bash
# Sobe o endpoint SPARQL do Ontop em 127.0.0.1:8080 (grafo virtual sobre o PostgreSQL).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Duser.timezone=UTC"
MET_HOME=${MET_HOME:-/home/claude/metdata}
ONTOP=${ONTOP_HOME:-/home/claude/tools/ontop}/ontop     # precisa de Java 17+ (JAVA_HOME ou java no PATH)
LOG=${ONTOP_LOG:-$MET_HOME/ontop.log}
PY=${PY:-python3}
case "${1:-start}" in
  start)
    "$PY" "$ROOT/mapping/build_mapping.py" > "$ROOT/mapping/met.obda"
    # O Ontop lê os caminhos como URI: espaço ou acento no caminho do projeto ("Área de Trabalho") dá "Illegal character in path".
    # Por isso a configuração é copiada para um diretório sem espaços e o Ontop aponta para a cópia.
    CFG="$MET_HOME/ontop_cfg"; mkdir -p "$CFG"
    cp "$ROOT/ontology/met.ttl" "$ROOT/mapping/met.obda" "$ROOT/mapping/met.properties" "$CFG/"
    # O endpoint NÃO tem autenticação e responde sobre todo o banco: escutar só no loopback. Sem isto o Ontop (Spring Boot) escutava em
    # *:8080 (todas as interfaces), ao contrário do que este cabeçalho dizia. Verificado com `ss -ltn` (ver tests/test_infra.py).
    export SERVER_ADDRESS="${ONTOP_BIND:-127.0.0.1}"
    # --dev habilita /ontop/reformulate: o SQL gerado (procedência) e a checagem prévia da consulta pelo PRÓPRIO motor
    # (pipeline/orchestrator.py::_engine_check). Ligado por padrão; ONTOP_DEV=0 desliga e a pipeline segue sem essa checagem.
    # Efeito colateral do --dev: expõe /ontop/restart e o actuator, sem autenticação, o que só é aceitável porque o endpoint
    # escuta apenas no loopback (SERVER_ADDRESS acima).
    DEVFLAG=""; [ "${ONTOP_DEV:-1}" = "1" ] && DEVFLAG="--dev"
    nohup "$ONTOP" endpoint -t "$CFG/met.ttl" -m "$CFG/met.obda" -p "$CFG/met.properties" \
      --port 8080 --cors-allowed-origins=http://127.0.0.1 $DEVFLAG > "$LOG" 2>&1 &
    echo $! > "$MET_HOME/ontop.pid"
    for i in $(seq 1 60); do curl -s -o /dev/null http://127.0.0.1:8080/sparql && { echo "ontop pronto"; exit 0; }; sleep 2; done
    echo "ontop não respondeu; ver $LOG"; exit 1 ;;
  stop)
    # O PID gravado é o do script `ontop`; o java filho sobrevive a ele e segura a porta. Primeiro os filhos (enquanto o pai existe), depois o pai,
    # e por fim só o que é DESTE Ontop (instalação em $ONTOP_HOME, comando endpoint): outro java ou outro Ontop não é tocado.
    PID=$(cat "$MET_HOME/ontop.pid" 2>/dev/null || true)
    if [[ "$PID" =~ ^[0-9]+$ ]] && [ "$PID" -gt 1 ]; then        # nunca `kill 0`/`kill 1`: derrubaria o grupo do próprio script
      pkill -P "$PID" 2>/dev/null || true
      kill "$PID" 2>/dev/null || true
    fi
    pkill -f "${ONTOP_HOME:-/home/claude/tools/ontop}.*endpoint" 2>/dev/null || true
    rm -f "$MET_HOME/ontop.pid" ;;
esac
