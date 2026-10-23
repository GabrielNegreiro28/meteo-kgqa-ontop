"""Compara condições de contexto (A: só rótulos, B: contexto gerado da ontologia) sobre várias execuções.

Uso: python -m eval.compare_runs A=eval/reports/llm_run_v1_s1.json,eval/reports/llm_run_v1_s2.json \
                                  B=eval/reports/llm_run_v3_s1.json,eval/reports/llm_run_v3_s2.json
Gera docs/COMPARACAO_CONTEXTO.md. Métricas com as mesmas definições de eval/run_llm_pipeline.py.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANSWERABLE = {"answered", "no_results"}
REFUSALS = {"unsupported", "needs_clarification", "rejected", "execution_error"}


def metrics(rows: list[dict]) -> dict[str, float]:
    ans = [r for r in rows if r["expected_status"] in ANSWERABLE and r["result_match"] is not None]
    fa = [r["first_attempt"] for r in rows if r.get("first_attempt") and r["first_attempt"].get("truth")]
    bad_first = [f for f in fa if f["truth"] in ("silent_wrong", "surfaced_empty", "surfaced_error")]
    return {
        "status igual ao esperado": sum(r["status_ok"] for r in rows),
        "respondíveis corretas": sum(bool(r["result_match"]) for r in ans),
        "  das quais incompletas (valor certo, falta coluna exigida)": sum(r.get("quality") == "incomplete" for r in ans),
        "  das quais em outra ordem": sum(r.get("quality") == "order_only" for r in ans),
        "respondíveis (n)": len(ans),
        "RESPOSTAS ERRADAS entregues": sum(r["status"] == "answered" and not r["result_match"] for r in ans),
        "falsa ausência de registros": sum(r["status"] == "no_results" and r["expected_status"] == "answered" and not r["result_match"] for r in ans),
        "abstenções indevidas": sum(r["expected_status"] in ANSWERABLE and r["status"] in REFUSALS for r in rows),
        "respondeu o que devia esclarecer/recusar": sum(r["expected_status"] not in ANSWERABLE and r["status"] in ANSWERABLE for r in rows),
        "1ª tentativa de consulta correta": sum(f["truth"] == "correct" for f in fa),
        "1ª tentativa errada (n)": len(bad_first),
        "  das quais barradas pelas regras": sum(bool(f["layers"]) for f in bad_first),
        "reparos": sum(r["repairs"] for r in rows),
        "respostas de reserva": sum(r["fallback"] for r in rows),
        "consultas montadas pelo compilador": sum(bool(r.get("compiled")) for r in rows),
        "custo (US$)": round(sum(r["cost_usd"] for r in rows), 3),
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out_name = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--out=")), "COMPARACAO_CONTEXTO.md")
    title = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--title=")), "Comparação de contexto: rótulos (A) × ontologia (B)")
    conds: dict[str, list[list[dict]]] = {}
    for arg in args:
        name, files = arg.split("=", 1)
        # "a.json+b.json" junta suítes numa só execução; "x,y" são execuções repetidas da condição
        conds[name] = [[row for f in run.split("+") for row in json.loads(Path(f).read_text(encoding="utf-8"))] for run in files.split(",")]
    L = [f"# {title}", "",
         "Gerado por `python -m eval.compare_runs`. Mesmo código de regras de consulta nas condições; muda o contexto/prompt/etapas. "
         "**Poucas execuções, poucas perguntas, um modelo**: leia as diferenças pequenas como ruído.", ""]
    per = {c: [metrics(r) for r in runs] for c, runs in conds.items()}
    keys = list(next(iter(per.values()))[0])
    head = "| métrica | " + " | ".join(f"{c} #{i + 1}" for c, ms in per.items() for i in range(len(ms))) + " |"
    L += [head, "|---|" + "---:|" * sum(len(ms) for ms in per.values())]
    for k in keys:
        L.append(f"| {k} | " + " | ".join(str(m[k]) for ms in per.values() for m in ms) + " |")
    # por pergunta
    L += ["", "## Por pergunta (status final em cada execução; ✔ resultado conferido, ✘ resultado errado)", "",
          "| id | esperado | " + " | ".join(f"{c}#{i + 1}" for c, runs in conds.items() for i in range(len(runs))) + " |",
          "|---|---|" + "---|" * sum(len(r) for r in conds.values())]
    ids = [r["id"] for r in next(iter(conds.values()))[0]]
    by = {c: [{r["id"]: r for r in run} for run in runs] for c, runs in conds.items()}
    for qid in ids:
        exp = by[next(iter(by))][0][qid]["expected_status"]
        cells = []
        for runs in by.values():
            for run in runs:
                r = run.get(qid)
                mark = "" if not r or r["result_match"] is None else (" ✔" if r["result_match"] else " ✘")
                cells.append((r["status"] if r else "—") + mark)
        L.append(f"| {qid} | {exp} | " + " | ".join(cells) + " |")
    # erros por código nas 1ªs tentativas
    L += ["", "## Achados das regras na 1ª tentativa do modelo (todas as execuções da condição)", "",
          "| condição | códigos (contagem) |", "|---|---|"]
    for c, runs in conds.items():
        cnt = Counter(code for run in runs for r in run if r.get("first_attempt") for code in r["first_attempt"]["codes"])
        L.append(f"| {c} | " + (", ".join(f"{k}×{v}" for k, v in cnt.most_common()) or "nenhum") + " |")
    out = ROOT / "docs" / out_name
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
