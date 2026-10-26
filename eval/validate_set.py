"""Executa os oráculos pandas de um conjunto congelado (eval/frozen/<name>) sem rodar a pipeline nem gastar LLM.

  python -m eval.validate_set novo_a

Cada oráculo roda num processo próprio (`eval/independent_evaluation/oracle_worker.py`: só lê os CSV permitidos, com `usecols` explícito; é isolamento de processo,
não um sandbox de segurança, por isso o código é varrido antes). O cwd é a pasta dos CSV porque os oráculos citam `temperatura.csv` sem caminho.
Grava `eval/frozen/<name>/oracle_results.json`; o que der erro, vazio ou estourar o tempo precisa de decisão humana antes de medir.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from eval.freeze_set import ROOT, verify

WORKER = ROOT / "independent_evaluation" / "oracle_worker.py"
CSV_DIR = Path(r"C:\Users\Gabriel\OneDrive\Área de Trabalho\Parente\METEOROLOGIA")


def run_one(src: Path, q: dict, tmp: Path, timeout: int = 180) -> dict:
    if q["expected_behavior"] != "answerable":
        return {"id": q["id"], "status": "not_applicable", "expected_behavior": q["expected_behavior"]}
    dest = tmp / f"{q['id']}.json"
    try:
        p = subprocess.run([sys.executable, "-I", "-B", str(WORKER), str(src), q["id"], str(dest)], cwd=CSV_DIR, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return json.loads(dest.read_text(encoding="utf-8")) if dest.exists() else {"id": q["id"], "status": "error", "error": f"worker {p.returncode}: {p.stderr[-500:]}"}
    except subprocess.TimeoutExpired:
        return {"id": q["id"], "status": "timeout", "error": f"mais de {timeout}s"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("name")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args(argv)
    sha = verify(a.name)
    d = ROOT / "frozen" / a.name
    questions = yaml.safe_load((d / "questions.yaml").read_text(encoding="utf-8"))["questions"]
    tmp = d / "oracle_tmp"
    tmp.mkdir(exist_ok=True)
    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(lambda q: run_one(d / "questions.yaml", q, tmp), questions))
    (d / "oracle_results.json").write_text(json.dumps({"sha256": sha, "results": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(Counter(r["status"] for r in rows))
    for r in rows:
        if r["status"] not in ("ok", "not_applicable"):
            print(r["id"], r["status"], str(r.get("error"))[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
