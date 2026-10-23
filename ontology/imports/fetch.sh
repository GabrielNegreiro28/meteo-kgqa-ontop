#!/bin/bash
# Reinstala a ferramenta de verificação formal (ROBOT) em ~/tools/onto e confere o SHA-256 (ver SOURCES.md).
# Os arquivos de ontologia já estão no repositório; só o .jar (95 MB) fica de fora.
set -euo pipefail
DEST="${ONTO_TOOLS:-$HOME/tools/onto}"
mkdir -p "$DEST"
URL=https://github.com/ontodev/robot/releases/download/v1.9.7/robot.jar
SHA=91890c2e83d0f092dd08731376f154b36610544cfbe8685337a1bf7244ccaa2d
if [ ! -f "$DEST/robot.jar" ] || [ "$(sha256sum "$DEST/robot.jar" | cut -d' ' -f1)" != "$SHA" ]; then
  curl -fsSL -o "$DEST/robot.jar" "$URL"
fi
[ "$(sha256sum "$DEST/robot.jar" | cut -d' ' -f1)" = "$SHA" ] || { echo "SHA do robot.jar não confere" >&2; exit 1; }
echo "ROBOT 1.9.7 ok em $DEST/robot.jar"
