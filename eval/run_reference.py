"""Executa as consultas de REFERÊNCIA contra o grafo e compara com o oráculo independente.

Uso:  python -m eval.run_reference                      (suíte sintética, rdflib)
      python -m eval.run_reference --suite real          (dados reais, Ontop em 127.0.0.1:8080)
      python -m eval.run_reference --split test

É o incremento 1: prova que grafo, executor, comparador e oráculo concordam ANTES de existir LLM.
O mesmo laço servirá depois para avaliar consultas geradas (troca-se só a origem do SPARQL).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from eval import oracle, oracle_real
from eval.compare import compare, rows_from_sparql
from kgqa.contract import Status
from kgqa.store import PREFIXES, LocalRdflibBackend, OntopBackend
from kgqa.verify import result_status

ROOT = Path(__file__).resolve().parent.parent


SUITES = {
    "synthetic": ("questions.yaml", oracle, LocalRdflibBackend, 20),
    "real": ("questions_real.yaml", oracle_real, OntopBackend, 60),
}


def load_questions(split: str | None = None, suite: str = "synthetic") -> list[dict]:
    qs = yaml.safe_load((ROOT / "eval" / SUITES[suite][0]).read_text(encoding="utf-8"))["questions"]
    return [q for q in qs if split in (None, q["split"])]


def run(split: str | None = None, suite: str = "synthetic") -> list[dict]:
    _, orc, backend_cls, timeout = SUITES[suite]
    backend = backend_cls()
    report = []
    for q in load_questions(split, suite):
        entry = {"id": q["id"], "split": q["split"], "category": q["category"],
                 "expected_status": q["expected_status"]}
        if "sparql" not in q:
            entry.update(checked="behavior_only", passed=None,
                         detail=f"sem consulta de referência; comportamento esperado: {q['expected_status']}"
                                f" ({q.get('expected_diagnostic', '')})")
            report.append(entry)
            continue
        res = backend.select(PREFIXES + q["sparql"], timeout_s=timeout)
        entry["elapsed_ms"] = round(res.elapsed_ms, 1)
        if not res.ok:
            entry.update(checked="executed", passed=False, detail=f"{res.error_kind}: {res.error}")
            report.append(entry)
            continue
        status, notes = result_status(res.results)
        actual = rows_from_sparql(res.results, q["compare"]["columns"])
        exp = orc.expected(q["id"])
        same, why = compare(actual, exp, q["compare"])
        status_ok = status.value == q["expected_status"]
        entry.update(checked="executed", passed=same and status_ok, rows=len(actual),
                     derived_status=status.value, status_ok=status_ok, result_match=same,
                     detail=why if same else why, notes=notes)
        report.append(entry)
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"])
    ap.add_argument("--suite", choices=list(SUITES), default="synthetic")
    args = ap.parse_args()
    report = run(args.split, args.suite)
    out = ROOT / "eval" / "reports"
    out.mkdir(exist_ok=True)
    (out / f"reference_run_{args.suite}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                                            encoding="utf-8")
    print(f"{'id':4} {'split':5} {'esperado':20} {'derivado':12} {'linhas':>6} {'ms':>7}  resultado")
    for e in report:
        mark = {True: "OK", False: "FALHA", None: "-"}[e["passed"]]
        print(f"{e['id']:4} {e['split']:5} {e['expected_status']:20} {e.get('derived_status', '-'):12} "
              f"{e.get('rows', '-'):>6} {e.get('elapsed_ms', '-'):>7}  {mark}  {e['detail'] if not e['passed'] else ''}")
    executed = [e for e in report if e["checked"] == "executed"]
    ok = sum(e["passed"] for e in executed)
    print(f"\n{ok}/{len(executed)} consultas de referência conferem com o oráculo; "
          f"{len(report) - len(executed)} perguntas só com comportamento esperado.")
    return 0 if ok == len(executed) else 1


if __name__ == "__main__":
    sys.exit(main())
