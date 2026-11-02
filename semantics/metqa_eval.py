"""Avaliação da evolução com o metqa INTEIRO (plano, D9): Parent e Candidate respondem o MESMO conjunto congelado, e o escore de cada
pergunta é 1 quando o comportamento está certo (respondeu e conferiu com o oráculo, ou recusou/esclareceu o que não era respondível).

É a medida ponta a ponta que `semantics/resolution.py` (barata, sem LLM) não dá. Custa LLM: duas execuções do conjunto por rodada, com o
teto do ledger valendo (o `llm` recebido já é o `LedgerLLM` envolto em `ResilientLLM`).

  python -m semantics.run_evolution --adapter metqa --set <conjunto congelado> --budget 3
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


class MetqaAdapter:
    def __init__(self, workspace: str | Path, set_name: str, llm, source, catalog, ids: list[str] | None = None):
        from eval.freeze_set import verify
        from eval.run_independent import load_frozen
        verify(set_name)
        d = ROOT / "eval" / "frozen" / set_name
        self.workspace, self.llm, self.source, self.catalog = Path(workspace), llm, source, catalog
        self.questions = {q["id"]: q for q in load_frozen(d / "questions.yaml") if not ids or q["id"] in ids}
        self.oracle = {r["id"]: r["result"] for r in json.loads((d / "oracle_results.json").read_text(encoding="utf-8"))["results"]
                       if r["status"] == "ok"}

    def evaluate(self, subject: str, cases: list[str] | None = None, output_hint: str | None = None) -> dict[str, Any]:
        from eval.adjudicate import robust_match
        from eval.run_independent import judge_row, sparql_rows
        from metqa.app import MetQA, Settings
        from metqa.knowledge import EvoLexicon
        qa = MetQA(self.catalog, EvoLexicon(self.catalog, self.workspace, subject), self.llm, self.source, Settings(timeout_s=60))
        rows = []
        for cid in (cases if cases is not None else sorted(self.questions)):
            q = self.questions[cid]
            r = qa.ask(q["question"]).response
            prows = sparql_rows(r.results)
            e = judge_row(q, r.status.value, prows, self.oracle)
            ok = (r.status.value == "answered" and robust_match(prows, self.oracle.get(cid) or [])) if e["expected_behavior"] == "answerable" \
                else bool(e["status_ok"])
            rows.append({"id": cid, "score": 1.0 if ok else 0.0, "status": r.status.value})
        mean = sum(r["score"] for r in rows) / len(rows) if rows else 0.0
        return {"metrics": {"mean_score": mean, "n": len(rows), "exact": sum(r["score"] == 1.0 for r in rows)}, "cases": rows,
                "artifact_paths": [], "provenance": f"semantics.metqa_eval (metqa inteiro, LLM; léxico {subject})"}
