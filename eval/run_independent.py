"""Mede a pipeline no conjunto de avaliação INDEPENDENTE congelado (`eval/questions_independent_frozen.yaml`, 49 perguntas).

Diferenças em relação a `run_llm_pipeline.py`:
- as perguntas e os códigos pandas de referência vieram de outro agente, sem as regras da pipeline; aqui não há SPARQL de referência;
- o conjunto é verificado contra o hash do manifesto antes de rodar (se mudou, recusa: qualquer revisão é uma nova versão);
- UMA execução por tag (recusa sobrescrever); não se ajusta regra nem prompt a partir do resultado;
- a comparação automática é conservadora: `match` só quando todos os números da referência aparecem na resposta; o resto vai a
  JULGAMENTO HUMANO (erro da pipeline, erro da referência ou diferença declarada de limpeza), nunca é contado como erro nem acerto.

Uso (gasta dinheiro; o ledger de `eval/reports/spend_ledger.jsonl` continua valendo):
  python -m eval.run_independent --prompts v4 --budget 2.0 --tag _a
  python -m eval.run_independent --summarize eval/reports/independent_run_v4_a.json     # recalcula o resumo sem LLM
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "eval" / "independent_evaluation"
FROZEN = ROOT / "eval" / "questions_independent_frozen.yaml"
EXPECTED_STATUS = {"answerable": {"answered", "no_results"}, "unsupported": {"unsupported"},
                   "needs_clarification": {"needs_clarification"}}
REL_TOL, ABS_TOL = 1e-3, 0.01


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen(frozen: Path = FROZEN, manifest: Path = PKG / "independent_manifest.json") -> str:
    """Hash do arquivo congelado == o do manifesto; do contrário o conjunto foi alterado depois do congelamento."""
    want = json.loads(manifest.read_text(encoding="utf-8"))["files"]["questions_independent_frozen.yaml"]
    got = sha256(frozen)
    if got != want:
        raise SystemExit(f"conjunto congelado alterado: sha256 {got} != manifesto {want}. Qualquer revisão deve virar nova versão.")
    return got


def load_frozen(frozen: Path = FROZEN) -> list[dict]:
    return yaml.safe_load(frozen.read_text(encoding="utf-8"))["questions"]


def load_oracle(validation: Path = PKG / "independent_validation.json") -> dict[str, list[list]]:
    return {r["id"]: r["result"] for r in json.loads(validation.read_text(encoding="utf-8"))["records"] if r["status"] == "ok"}


def numbers_of(rows: list[list]) -> list[float]:
    return [float(v) for row in rows for v in row if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(ABS_TOL, REL_TOL * max(abs(a), abs(b)))


def auto_compare(pipeline_rows: list[list], oracle_rows: list[list]) -> tuple[str, str]:
    """('match'|'diverge', motivo). Só números: cada número da referência precisa de um número ainda não usado na resposta.
    Texto (siglas, rótulos) não é conferido aqui; quem decide o que é resposta é o julgamento humano nos casos `diverge`."""
    want, have = numbers_of(oracle_rows), numbers_of(pipeline_rows)
    if not want:
        return "diverge", "referência sem números; julgar manualmente"
    pool = list(have)
    missing = []
    for w in want:
        hit = next((i for i, h in enumerate(pool) if _close(w, h)), None)
        if hit is None:
            missing.append(w)
        else:
            pool.pop(hit)
    if missing:
        return "diverge", f"{len(missing)} de {len(want)} números da referência sem par na resposta: {missing[:5]}"
    extra = len(pool)
    return "match", "todos os números da referência aparecem" + (f" (a resposta traz {extra} número(s) a mais)" if extra else "")


def sparql_rows(results: dict | None) -> list[list]:
    if not results:
        return []
    cols = results["head"]["vars"]
    out = []
    for b in results["results"]["bindings"]:
        row = []
        for c in cols:
            t = b.get(c)
            if t is None:
                row.append(None)
            elif t["type"] == "uri":
                row.append(t["value"].rstrip("/").rsplit("/", 1)[-1])
            else:
                try:
                    row.append(float(t["value"]) if t.get("datatype", "").rsplit("#", 1)[-1] in
                               {"integer", "decimal", "double", "float", "int", "long"} else t["value"])
                except ValueError:
                    row.append(t["value"])
        out.append(row)
    return out


def judge_row(q: dict, status: str, rows: list[list], oracle: dict[str, list[list]]) -> dict:
    exp = EXPECTED_STATUS[q["expected_behavior"]]
    e = {"id": q["id"], "category": q["category"], "expected_behavior": q["expected_behavior"], "status": status,
         "status_ok": status in exp, "auto": None, "auto_note": None}
    if q["expected_behavior"] == "answerable":
        if status == "answered" and q["id"] in oracle:
            e["auto"], e["auto_note"] = auto_compare(rows, oracle[q["id"]])
        elif status == "no_results":
            e["auto"], e["auto_note"] = "diverge", "a pipeline disse que não há registros; conferir se a referência tem dados"
        else:
            e["auto"], e["auto_note"] = "abstained", f"pipeline não respondeu ({status})"
    elif status in ("answered", "no_results"):
        e["auto"], e["auto_note"] = "answered_unanswerable", "respondeu algo que deveria ser recusado/esclarecido; julgar se o recorte pedido existia"
    return e


def summarize(rows: list[dict], model: str, prompts: str, spent: float, sha: str) -> str:
    n = len(rows)
    ans = [r for r in rows if r["expected_behavior"] == "answerable"]
    beh = [r for r in rows if r["expected_behavior"] != "answerable"]
    c = Counter(r["auto"] for r in ans)
    L = [f"# Avaliação independente: prompts `{prompts}`, modelo `{model}`", "",
         f"Conjunto congelado sha256 `{sha}` · n={n} · custo US$ {spent:.4f}. Uma execução; sem ajuste posterior.", "",
         f"- status igual ao esperado: **{sum(r['status_ok'] for r in rows)}/{n}**",
         f"- respondíveis ({len(ans)}): `match` automático {c['match']} · **a julgar** (diverge) {c['diverge']} · abstenções {c['abstained']}",
         f"- não respondíveis ({len(beh)}): recusadas/esclarecidas corretamente {sum(r['status_ok'] for r in beh)} · "
         f"respondidas indevidamente (a julgar) {sum(r['auto'] == 'answered_unanswerable' for r in beh)}", "",
         "`diverge` NÃO é erro: pode ser erro da pipeline, erro do código de referência ou diferença de limpeza (valor impossível, fuso, "
         "leituras repetidas, teto de visibilidade). Cada caso exige veredito humano em `eval/reports/independent_verdicts.yaml` "
         "(`pipeline_error | oracle_error | cleaning_difference | ok`) antes de qualquer taxa de acerto.", "",
         "## Por pergunta", "", "| id | categoria | esperado | obtido | automático | nota |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['id']} | {r['category']} | {r['expected_behavior']} | {r['status']} | {r['auto'] or '—'} | {(r['auto_note'] or '')[:110]} |")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(ROOT.parent / "METEOROLOGIA" / "kgqa.env"))
    ap.add_argument("--prompts", choices=["v1", "v2", "v3", "v4", "v5", "v6"], default="v4")
    ap.add_argument("--budget", type=float, default=2.0, help="teto desta execução em US$ (estimado)")
    ap.add_argument("--ledger", default=str(ROOT / "eval" / "reports" / "spend_ledger.jsonl"))
    ap.add_argument("--authorize-usd", type=float)
    ap.add_argument("--authorized-by")
    ap.add_argument("--reason")
    ap.add_argument("--ids")
    ap.add_argument("--tag", default="")
    ap.add_argument("--summarize", help="recalcula o resumo de um independent_run_*.json sem chamar o LLM")
    args = ap.parse_args()
    sha = verify_frozen()
    questions = load_frozen()
    oracle = load_oracle()
    (ROOT / "eval" / "reports").mkdir(exist_ok=True)
    if args.summarize:
        d = json.loads(Path(args.summarize).read_text(encoding="utf-8"))
        print(summarize(d["rows"], d["model"], d["prompts"], d["spent_usd"], sha))
        return 0
    out_json = ROOT / "eval" / "reports" / f"independent_run_{args.prompts}{args.tag}.json"
    if out_json.exists():
        print(f"{out_json.name} já existe: uma execução por tag. Use outra --tag só se for uma condição diferente.", file=sys.stderr)
        return 2
    from kgqa.store import OntopBackend
    from pipeline.ledger import Ledger, LedgerLLM
    from pipeline.llm import ResilientLLM
    from pipeline.openai_client import OpenAIChatClient, load_env
    from pipeline.orchestrator import run_pipeline
    from pipeline.vocab import OntologyIndex
    backend = OntopBackend()
    index = OntologyIndex.from_ontop(backend)
    client = OpenAIChatClient.from_env(args.env)
    ledger = Ledger(args.ledger)
    if args.authorize_usd:
        if not (args.authorized_by and args.reason):
            print("--authorize-usd exige --authorized-by e --reason", file=sys.stderr)
            return 2
        ledger.authorize(args.authorize_usd, by=args.authorized_by, reason=args.reason)
    cap = float(load_env(args.env).get("KGQA_BUDGET_USD", "5.0"))
    print(f"gasto acumulado: US$ {ledger.total():.2f} · teto acumulado: US$ {cap + ledger.authorized_extra():.2f}", file=sys.stderr)
    shared = ResilientLLM(LedgerLLM(client, ledger, base_cap_usd=cap, run=f"independent_{args.prompts}{args.tag}",
                                    model=getattr(client, "model", "")), budget_usd=args.budget)
    wanted = set(args.ids.split(",")) if args.ids else None
    rows = []
    for q in questions:
        if wanted and q["id"] not in wanted:
            continue
        t0 = time.perf_counter()
        res = run_pipeline(q["question"], shared, backend, index, timeout_s=60, prompts_version=args.prompts)
        r = res.response
        prows = sparql_rows(r.results)
        e = judge_row(q, r.status.value, prows, oracle)
        e.update({"question": q["question"], "answer_text": r.answer_text, "sparql": r.sparql, "pipeline_rows": prows[:50],
                  "oracle_rows": oracle.get(q["id"]), "assumptions": q.get("assumptions"),
                  "diagnostics": [d.code for d in r.diagnostics], "elapsed_s": round(time.perf_counter() - t0, 1)})
        rows.append(e)
        print(f"{e['id']:4} esperado={e['expected_behavior']:19} obtido={e['status']:19} auto={e['auto']} ({e['elapsed_s']}s)", file=sys.stderr)
        if shared.spent_usd >= args.budget:
            print("orçamento da execução atingido; interrompendo", file=sys.stderr)
            break
    model = getattr(client, "model", "?")
    out_json.write_text(json.dumps({"model": model, "prompts": args.prompts, "spent_usd": shared.spent_usd, "frozen_sha256": sha, "rows": rows},
                                   ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    md = out_json.with_suffix(".md")
    md.write_text(summarize(rows, model, args.prompts, shared.spent_usd, sha), encoding="utf-8")
    print(f"{len(rows)} perguntas -> {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
