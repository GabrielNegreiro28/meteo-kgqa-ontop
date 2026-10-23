#!/usr/bin/env bash
# Verificação de ponta a ponta no WSL: sobe o que estiver parado e roda a suíte inteira contra o Ontop/PostgreSQL REAIS.
# No Windows, `pytest` sozinho pula os testes que precisam do grafo real (34 a 47 pulados); este é o comando que os executa.
#   source ~/metdata/env.sh && bash infra/verify.sh
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
: "${MET_HOME:?rode antes: source ~/metdata/env.sh}"; : "${PY:?rode antes: source ~/metdata/env.sh}"
cd "$ROOT"

up() { curl -s -m 5 -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/sparql -d 'query=ASK{}' 2>/dev/null || true; }
if [ "$(up)" != "200" ]; then
  echo "Ontop fora do ar: subindo PostgreSQL e Ontop..."
  bash infra/pg.sh start 2>&1 | tail -1 || true
  bash infra/ontop.sh start 2>&1 | tail -1
fi
echo "Ontop em 127.0.0.1:8080 | reformulação: $(curl -s -m 5 -o /dev/null -w '%{http_code}' -G --data-urlencode 'query=ASK{}' http://127.0.0.1:8080/ontop/reformulate) (400/500 = rota existe)"
exec "$PY" -m pytest -q -p no:cacheprovider -rs "$@"
