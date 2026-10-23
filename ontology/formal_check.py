"""Ferramentas de verificação formal (ROBOT + HermiT) usadas pelos testes e pelo `infra/verify.sh`.

ROBOT é um .jar do OBO Foundry (versão e SHA-256 em ontology/imports/SOURCES.md); precisa de Java. Onde não houver, os testes
que o usam são pulados (o resto da verificação, em Python puro, roda em qualquer lugar).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HOME = Path.home()


def java() -> str | None:
    return shutil.which("java") or next((str(p) for p in [HOME / "tools" / "jdk17" / "bin" / "java"] if p.exists()), None)


def robot_jar() -> str | None:
    cand = [os.environ.get("ROBOT_JAR", ""), str(HOME / "tools" / "onto" / "robot.jar")]
    return next((c for c in cand if c and Path(c).exists()), None)


def available() -> bool:
    return bool(java() and robot_jar())


def run(*args: str, timeout: int = 600) -> tuple[int, str]:
    out = subprocess.run([java(), "-jar", robot_jar(), *args], capture_output=True, text=True, timeout=timeout)
    return out.returncode, (out.stdout + out.stderr)


def validate_profile(profile: str, path: Path) -> tuple[bool, str]:
    """Perfil OWL 2 ('DL' ou 'QL'). O ROBOT devolve código != 0 e lista as violações."""
    with tempfile.TemporaryDirectory() as d:
        code, text = run("validate-profile", "--profile", profile, "--input", str(path), "--output", str(Path(d) / "report.txt"))
        report = (Path(d) / "report.txt").read_text(encoding="utf-8") if (Path(d) / "report.txt").exists() else text
    return code == 0 and "in profile" in report and "NOT in profile" not in report, report


def reason(*inputs: Path) -> tuple[bool, str]:
    """HermiT sobre a união das entradas: falha se a ontologia é inconsistente ou tem classe insatisfatível."""
    with tempfile.TemporaryDirectory() as d:
        args = ["merge"]
        for p in inputs:
            args += ["--input", str(p)]
        args += ["reason", "--reasoner", "HermiT", "--output", str(Path(d) / "out.ofn")]
        code, text = run(*args)
    return code == 0, text
