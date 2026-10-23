# Ambiente do grafo real no WSL. O setup_wsl.sh grava uma cópia deste arquivo em $MET_HOME/env.sh. Uso:  source ~/metdata/env.sh
export MET_HOME=$HOME/metdata                      # dados, venv e logs: FORA do OneDrive (dezenas de GB)
export PY=$MET_HOME/venv/bin/python
export JAVA_HOME=$HOME/tools/jdk17                 # o Ontop 5.5 exige Java 17+
export ONTOP_HOME=$HOME/tools/ontop
export PATH=$JAVA_HOME/bin:$HOME/.local/bin:$PATH
# ONTOP_DEV=0   desliga o modo --dev do Ontop (sem ele não há checagem prévia pelo motor nem SQL na procedência)
# ONTOP_BIND=127.0.0.1   endereço em que o endpoint escuta; NÃO mude: ele não tem autenticação
