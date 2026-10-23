#!/usr/bin/env bash
# Instala, SEM sudo, o ambiente do grafo real: uv, JDK 17, Ontop CLI 5.5.0, driver JDBC, Python 3.12 e as dependências do projeto.
# Reproduz o que foi montado à mão em 22/10/2026 (DECISOES.md, D-31 e D-32). Idempotente: o que já existe é pulado.
#
#   bash infra/setup_wsl.sh                 # instala em $HOME (tools em ~/tools, dados e venv em ~/metdata)
#   PREFIX=/tmp/teste bash infra/setup_wsl.sh   # instala num prefixo isolado (para testar o próprio script)
#
# Checksums: cada download é conferido contra o SHA-256 registrado abaixo. Os valores foram registrados na PRIMEIRA instalação (confiança no
# primeiro uso), não vêm de uma fonte independente: protegem contra mudança posterior do arquivo, não contra um download já comprometido.
# Se um valor mudar de propósito (nova versão), atualize-o aqui na mesma alteração que muda a versão.
set -euo pipefail

PREFIX=${PREFIX:-$HOME}
TOOLS="$PREFIX/tools"; MET_HOME="$PREFIX/metdata"
ROOT=$(cd "$(dirname "$0")/.." && pwd)
UV_VERSION=0.13.5
ONTOP_VERSION=5.5.0
JDK_VERSION=17.0.21+9
JDBC_VERSION=42.7.4

UV_URL="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz"
ONTOP_URL="https://github.com/ontop/ontop/releases/download/ontop-$ONTOP_VERSION/ontop-cli-$ONTOP_VERSION.zip"
JDK_URL="https://api.adoptium.net/v3/binary/version/jdk-${JDK_VERSION/+/%2B}/linux/x64/jdk/hotspot/normal/eclipse"
JDBC_URL="https://repo1.maven.org/maven2/org/postgresql/postgresql/$JDBC_VERSION/postgresql-$JDBC_VERSION.jar"

# SHA-256 registrados (vazio = ainda não registrado: o script imprime o valor para você registrar)
UV_SHA="f68d291c75783122dad58ab77def0e13f3233f358731db5d6d7e8715603b928f"
ONTOP_SHA="430dff312e68e8ad41d26e6113160ca2365c28c4fe911926193000a33299458f"
JDK_SHA="8b9b611d917e3dfd8419d3566b5949226f69b052fed7e109c1368add1dfe8711"
JDBC_SHA="188976721ead8e8627eb6d8389d500dccc0c9bebd885268a3047180274a6031e"

mkdir -p "$TOOLS" "$MET_HOME" "$PREFIX/.local/bin"
fetch() {   # fetch <url> <arquivo> <sha-esperado> <rótulo>
  curl -fsSL -L -o "$2" "$1"
  local got; got=$(sha256sum "$2" | cut -d' ' -f1)
  if [ -n "$3" ] && [ "$got" != "$3" ]; then echo "ERRO: SHA-256 de $4 difere do registrado ($got)" >&2; rm -f "$2"; exit 1; fi
  [ -z "$3" ] && echo "  registrar em $(basename "$0"): $4 = $got"
  return 0
}

echo "== uv $UV_VERSION"
if [ ! -x "$PREFIX/.local/bin/uv" ]; then
  fetch "$UV_URL" "$TOOLS/uv.tgz" "$UV_SHA" UV_SHA
  tar -xzf "$TOOLS/uv.tgz" --strip-components=1 -C "$PREFIX/.local/bin" && rm "$TOOLS/uv.tgz"
fi
UV="$PREFIX/.local/bin/uv"; "$UV" --version

echo "== JDK $JDK_VERSION"
if [ ! -x "$TOOLS/jdk17/bin/java" ]; then
  fetch "$JDK_URL" "$TOOLS/jdk.tgz" "$JDK_SHA" JDK_SHA
  mkdir -p "$TOOLS/jdk17" && tar -xzf "$TOOLS/jdk.tgz" --strip-components=1 -C "$TOOLS/jdk17" && rm "$TOOLS/jdk.tgz"
fi
"$TOOLS/jdk17/bin/java" -version 2>&1 | head -1

echo "== Ontop $ONTOP_VERSION"
if [ ! -x "$TOOLS/ontop/ontop" ]; then
  fetch "$ONTOP_URL" "$TOOLS/ontop.zip" "$ONTOP_SHA" ONTOP_SHA
  "$UV" run --no-project python -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$TOOLS/ontop.zip" "$TOOLS/ontop"
  rm "$TOOLS/ontop.zip"; chmod +x "$TOOLS/ontop/ontop"
fi
echo "== driver JDBC $JDBC_VERSION"
if [ ! -f "$TOOLS/ontop/jdbc/postgresql-$JDBC_VERSION.jar" ]; then
  fetch "$JDBC_URL" "$TOOLS/ontop/jdbc/postgresql-$JDBC_VERSION.jar" "$JDBC_SHA" JDBC_SHA
fi
# Artefatos que JÁ existiam não são confiáveis só por existirem: o driver (um arquivo) é conferido pelo SHA-256 e os demais pela versão.
GOT_JDBC=$(sha256sum "$TOOLS/ontop/jdbc/postgresql-$JDBC_VERSION.jar" | cut -d' ' -f1)
[ -z "$JDBC_SHA" ] || [ "$GOT_JDBC" = "$JDBC_SHA" ] || { echo "ERRO: driver JDBC instalado difere do SHA-256 registrado ($GOT_JDBC); apague-o e rode de novo" >&2; exit 1; }
"$TOOLS/jdk17/bin/java" -version 2>&1 | grep -q "${JDK_VERSION%%+*}" || echo "AVISO: o JDK instalado não é o $JDK_VERSION registrado" >&2
"$TOOLS/ontop/ontop" --version 2>&1 | grep -q "$ONTOP_VERSION" || echo "AVISO: o Ontop instalado não parece ser o $ONTOP_VERSION registrado" >&2

echo "== Python 3.12 e dependências"
[ -d "$MET_HOME/venv" ] || "$UV" venv --python 3.12 "$MET_HOME/venv" >/dev/null
grep -v '^evoontology' "$ROOT/requirements.txt" | tr -d '\r' > "$MET_HOME/requirements.txt"
"$UV" pip install --python "$MET_HOME/venv/bin/python" -q -r "$MET_HOME/requirements.txt"
EVO=$(grep '^evoontology' "$ROOT/requirements.txt" | tr -d '\r')
"$UV" pip install --python "$MET_HOME/venv/bin/python" -q "$EVO"

echo "== env.sh"
sed -e "s#\$HOME#$PREFIX#g" "$ROOT/infra/env.example.sh" > "$MET_HOME/env.sh"
echo "pronto. Próximos passos:  source $MET_HOME/env.sh  &&  PACK=<pasta dos .npz> bash infra/rebuild.sh"
