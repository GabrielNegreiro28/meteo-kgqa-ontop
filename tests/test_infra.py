"""Infraestrutura: o que quebrou ou estava errado e não pode voltar (docs/ANALISE_CRITICA.md, A-10, A-30, A-32, A-33).

Os testes estáticos rodam em qualquer sistema. O de rede só roda onde o Ontop está no ar e há `ss` (WSL/Linux).
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_real_pipeline import needs_ontop

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted((ROOT / "infra").glob("*.sh"))


def test_the_ontop_endpoint_is_bound_to_the_loopback_by_default():
    """O endpoint não tem autenticação e responde sobre todo o banco. Escutava em *:8080 (todas as interfaces) enquanto o cabeçalho dizia 127.0.0.1."""
    text = (ROOT / "infra" / "ontop.sh").read_text(encoding="utf-8")
    assert re.search(r'SERVER_ADDRESS="\$\{ONTOP_BIND:-127\.0\.0\.1\}"', text)
    assert "0.0.0.0" not in text


def test_postgres_listens_only_on_the_loopback():
    assert "-h 127.0.0.1" in (ROOT / "infra" / "pg.sh").read_text(encoding="utf-8")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_shell_scripts_have_unix_line_endings(script):
    """CRLF em .sh quebra no WSL (`$'\\r': command not found`)."""
    assert b"\r" not in script.read_bytes(), f"{script.name} tem CRLF"


def test_gitattributes_keeps_scripts_in_lf():
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"^\*\.sh\s+text eol=lf", attrs, re.M) and re.search(r"^\*\.obda\s+text eol=lf", attrs, re.M)


def test_setup_script_pins_every_version_and_has_a_place_for_each_checksum():
    text = (ROOT / "infra" / "setup_wsl.sh").read_text(encoding="utf-8")
    for var in ("UV_VERSION", "ONTOP_VERSION", "JDK_VERSION", "JDBC_VERSION"):
        assert re.search(rf"^{var}=\d", text, re.M), var
    for var in ("UV_SHA", "ONTOP_SHA", "JDK_SHA", "JDBC_SHA"):
        assert re.search(rf'^{var}="', text, re.M), var
    assert "set -euo pipefail" in text
    assert not re.search(r"^[^#\n]*\bsudo\b", text, re.M)                                    # nenhuma LINHA DE CÓDIGO usa sudo (o comentário pode citá-lo)


def test_stop_also_kills_the_java_child():
    """O PID gravado é o do script `ontop`; o java filho sobrevivia e segurava a porta."""
    assert "pkill -f" in (ROOT / "infra" / "ontop.sh").read_text(encoding="utf-8")


def test_secrets_stay_out_of_version_control():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("*.env", ".venv/", ".evoontology/trajectories/", "METEOROLOGIA/"):
        assert pattern in ignore, pattern


@needs_ontop
@pytest.mark.skipif(shutil.which("ss") is None, reason="sem `ss`")
def test_the_running_endpoint_does_not_listen_on_a_public_interface():
    out = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, timeout=10).stdout
    lines = [l for l in out.splitlines() if re.search(r":8080\s", l)]
    assert lines, "ninguém escutando na 8080"
    for l in lines:
        local = l.split()[3]
        assert "127.0.0.1" in local or "[::1]" in local, f"escutando fora do loopback: {local}"


# ---------- Codex C19: os testes de infraestrutura passam a conferir o que importa, não só a presença de texto ----------

def test_every_registered_checksum_is_a_real_sha256():
    """O teste anterior aceitava `UV_SHA=""`: um checksum vazio desliga a conferência sem que ninguém veja."""
    text = (ROOT / "infra" / "setup_wsl.sh").read_text(encoding="utf-8")
    for var in ("UV_SHA", "ONTOP_SHA", "JDK_SHA", "JDBC_SHA"):
        m = re.search(rf'^{var}="([^"]*)"', text, re.M)
        assert m and re.fullmatch(r"[0-9a-f]{64}", m.group(1)), f"{var} não é um SHA-256 de 64 dígitos hexadecimais"


def test_setup_checks_artifacts_that_already_exist():
    text = (ROOT / "infra" / "setup_wsl.sh").read_text(encoding="utf-8")
    assert re.search(r'GOT_JDBC=\$\(sha256sum "\$TOOLS/ontop/jdbc/postgresql-\$JDBC_VERSION\.jar" \| cut', text)
    assert "driver JDBC instalado difere" in text and "--version" in text


def test_stop_never_kills_by_a_pid_that_is_not_a_real_process_id_and_is_limited_to_this_installation():
    """`kill 0` derruba o grupo do próprio script; `pkill -f java` derrubaria o Java dos outros. O stop só mata o que é deste Ontop."""
    text = (ROOT / "infra" / "ontop.sh").read_text(encoding="utf-8")
    stop = text[text.index("stop)"):]
    assert re.search(r'\[\[ "\$PID" =~ \^\[0-9\]\+\$ \]\] && \[ "\$PID" -gt 1 \]', stop)
    assert "pkill -f" in stop and "ONTOP_HOME" in stop.split("pkill -f", 1)[1].splitlines()[0]     # padrão amarrado à instalação
    assert not re.search(r"pkill -f \"?java", stop)


@pytest.mark.skipif(shutil.which("bash") is None or shutil.which("pkill") is None, reason="sem bash/pkill")
def test_stop_kills_this_ontops_children_and_spares_other_processes(tmp_path):
    """Comportamento real do trecho `stop`, com um Ontop de mentira (script `ontop` que cria um filho) e um processo alheio."""
    import os, signal, time
    fake_home = tmp_path / "ontop_home"
    fake_home.mkdir()
    marker = tmp_path / "met"
    marker.mkdir()
    (fake_home / "ontop").write_text("#!/usr/bin/env bash\nsleep 300 &\nwait\n", encoding="utf-8", newline="\n")
    (fake_home / "ontop").chmod(0o755)
    parent = subprocess.Popen([str(fake_home / "ontop"), "endpoint"], start_new_session=True)
    bystander = subprocess.Popen(["sleep", "301"], start_new_session=True)
    (marker / "ontop.pid").write_text(str(parent.pid))
    time.sleep(0.5)
    try:
        script = ROOT / "infra" / "ontop.sh"
        env = {**os.environ, "MET_HOME": str(marker), "ONTOP_HOME": str(fake_home)}
        subprocess.run(["bash", str(script), "stop"], env=env, timeout=30, check=True)
        time.sleep(0.5)
        assert parent.poll() is not None, "o script do Ontop deveria ter sido encerrado"
        assert bystander.poll() is None, "um processo alheio foi morto"
        assert not (marker / "ontop.pid").exists()
    finally:
        for p in (parent, bystander):
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
