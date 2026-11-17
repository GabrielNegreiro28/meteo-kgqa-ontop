"""Mede a pipeline no conjunto de avaliação INDEPENDENTE congelado (`eval/questions_independent_frozen.yaml`, 49 perguntas).

Diferenças em relação a `run_llm_pipeline.py`:
- as perguntas e os códigos pandas de referência vieram de outro agente, sem as regras da pipeline; aqui não há SPARQL de referência;
- o conjunto é verificado contra o hash do manifesto antes de rodar (se mudou, recusa: qualquer revisão é uma nova versão);
- UMA execução por tag (recusa sobrescrever); não se ajusta regra nem prompt a partir do resultado;
- a comparação automática preserva linhas, colunas, tipos e multiplicidade; esquemas diferentes precisam de projeção explícita. O resto vai a
  JULGAMENTO HUMANO (erro da pipeline, erro da referência ou diferença declarada de limpeza), nunca é contado como erro nem acerto.

Uso (gasta dinheiro; o ledger de `eval/reports/spend_ledger.jsonl` continua valendo):
  python -m eval.run_independent --prompts metqa --budget 2.0 --tag _a
  python -m eval.run_independent --summarize eval/reports/independent_run_metqa_a.json
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


def auto_compare(pipeline_rows, oracle_rows):
    from eval.matching import match_rows
    if oracle_rows is None:
        return "evaluation_error", "missing reference"
    ok = match_rows(pipeline_rows, oracle_rows)
    return ("match", "typed rows match") if ok else ("diverge", "typed rows differ; explicit schema alignment or review required")


def sparql_rows(results: dict | None) -> list[list]:
    if not results:
        return []
    if "parts" in results:                              # comparação do MVP: uma subconsulta por período, cada linha com o rótulo da parte
        return [[p["label"], *row] for p in results["parts"] for row in sparql_rows(p["results"])]
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
        elif q["id"] not in oracle:
            e["auto"], e["auto_note"] = "evaluation_error", "missing reference"
        elif status == "no_results":
            e["auto"], e["auto_note"] = auto_compare(rows, oracle[q["id"]])
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
    ap.add_argument("--prompts", choices=["metqa", "metqa-1r", "metqa-formal", "metqa-noconserv", "metqa-nobfo"], default="metqa",
                    help="condição, sempre sem usuário: metqa (2 leituras) | metqa-1r (1 leitura) | metqa-formal (sem EvoOntology) | "
                         "metqa-noconserv (sem conservação da evidência nem releitura). O legado (v1–v8) está na tag legado-v8")
    ap.add_argument("--budget", type=float, default=2.0, help="teto desta execução em US$ (estimado)")
    ap.add_argument("--ledger", default=str(ROOT / "eval" / "reports" / "spend_ledger.jsonl"))
    ap.add_argument("--authorize-usd", type=float)
    ap.add_argument("--authorized-by")
    ap.add_argument("--reason")
    ap.add_argument("--ids")
    ap.add_argument("--tag", default="")
    ap.add_argument("--set", dest="set_name", help="conjunto congelado por eval.freeze_set (eval/frozen/<nome>); sem isto usa o independente de 49")
    ap.add_argument("--semantic-workspace", default=str(ROOT / ".evoontology"), help="workspace da camada semântica")
    ap.add_argument("--semantic-version", help="versão da camada (padrão: a ativa)")
    ap.add_argument("--snapshot", type=Path, help="manifesto da carga limpa declarada pelo operador")
    ap.add_argument("--clean-reference", type=Path, help="referências tipadas geradas por eval.clean_reference")
    ap.add_argument("--summarize", help="recalcula o resumo de um independent_run_*.json sem chamar o LLM")
    args = ap.parse_args()
    if args.set_name:
        from eval.freeze_set import verify
        sha = verify(args.set_name)
        d = ROOT / "eval" / "frozen" / args.set_name
        questions = load_frozen(d / "questions.yaml")
        oracle = {r["id"]: r["result"] for r in json.loads((d / "oracle_results.json").read_text(encoding="utf-8"))["results"] if r["status"] == "ok"}
    else:
        sha = verify_frozen()
        questions = load_frozen()
        oracle = load_oracle()
    (ROOT / "eval" / "reports").mkdir(exist_ok=True)
    if args.summarize:
        d = json.loads(Path(args.summarize).read_text(encoding="utf-8"))
        print(summarize(d["rows"], d["model"], d["prompts"], d["spent_usd"], sha))
        return 0
    out_json = ROOT / "eval" / "reports" / f"independent_run_{args.set_name + '_' if args.set_name else ''}{args.prompts}{args.tag}.json"
    if out_json.exists():
        print(f"{out_json.name} já existe: uma execução por tag. Use outra --tag só se for uma condição diferente.", file=sys.stderr)
        return 2
    from metqa.execution.store import OntopBackend
    from metqa.llm.ledger import Ledger, LedgerLLM
    from metqa.llm.client import ResilientLLM
    from metqa.llm.openai_client import OpenAIChatClient, load_env
    from metqa.knowledge.index import OntologyIndex
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
    from metqa.app import MetQA, Settings
    from metqa.knowledge import DomainCatalog, EvoLexicon, OntologyLexicon
    catalog = DomainCatalog(index)
    if args.snapshot:
        from ingest.manifest import load
        catalog.snapshot = load(args.snapshot)
    clean_references = None
    if args.clean_reference:
        clean_references = json.loads(args.clean_reference.read_text(encoding="utf-8"))
        if not catalog.snapshot or clean_references['snapshot_id'] != catalog.snapshot['snapshot_id']:
            raise ValueError("reference and source snapshot must match")
        missing = [q['id'] for q in questions if q['expected_behavior'] == 'answerable' and q['id'] not in clean_references['cases']]
        if missing:
            raise ValueError(f"missing clean references: {missing}")
    lexicon = (OntologyLexicon(catalog) if args.prompts == "metqa-formal"
               else EvoLexicon(catalog, args.semantic_workspace, args.semantic_version, bfo_context=args.prompts != 'metqa-nobfo'))
    # sem usuário: o que exigiria confirmação vira needs_clarification (CONFIRMATION_REQUIRED); memória vazia (sem contaminação)
    mvp = MetQA(catalog, lexicon, shared, backend, Settings(timeout_s=60, readings=1 if args.prompts == "metqa-1r" else 2,
                                                             conservation=args.prompts != "metqa-noconserv"))
    trace_file = out_json.with_name(out_json.stem + "_trace.jsonl").open("w", encoding="utf-8")
    print(f"metqa, léxico: {lexicon.version}", file=sys.stderr)
    wanted = set(args.ids.split(",")) if args.ids else None
    rows = []
    for q in questions:
        if wanted and q["id"] not in wanted:
            continue
        t0 = time.perf_counter()
        res = mvp.ask(q["question"])
        r = res.response
        prows = sparql_rows(r.results)
        e = judge_row(q, r.status.value, prows, oracle)
        if clean_references is not None and q['expected_behavior'] == 'answerable':
            from eval.clean_reference import compare
            ok = compare(r, clean_references['cases'][q['id']])
            e['auto'] = 'match' if ok else ('diverge' if r.status.value in ('answered', 'no_results') else 'abstained')
            e['auto_note'] = 'typed clean snapshot reference; explicit columns and units'
            e['status_ok'] = r.status.value == clean_references['cases'][q['id']]['expected_status']
        e.update({"question": q["question"], "answer_text": r.answer_text, "sparql": r.sparql, "pipeline_rows": prows[:50],
                  "oracle_rows": oracle.get(q["id"]), "assumptions": q.get("assumptions"),
                  "diagnostics": [d.code for d in r.diagnostics], "elapsed_s": round(time.perf_counter() - t0, 1)})
        # a trilha inteira de cada pergunta (D9): o que as leituras disseram, a concordância, a releitura, o SPARQL e o papel das colunas
        e["result_shape"] = r.result_shape
        e['provenance'] = r.to_dict()['provenance']
        e['contract_version'] = r.contract_version
        trace_file.write(json.dumps({"id": q["id"], "trace": res.trace}, ensure_ascii=False, default=str) + "\n")
        trace_file.flush()
        try:                                        # trajetória de MEDIÇÃO (split "eval"): a evolução nunca a minera
            from semantics.trajectories import record_trajectory
            record_trajectory(args.semantic_workspace, res, task_id=f"{out_json.stem}:{q['id']}", split="eval",
                              extra={"status_ok": e.get("status_ok"), "result_match": e.get("auto") == "match" if e.get("auto") else None})
        except Exception as err:                    # noqa: BLE001 — a medição não para por causa do registro
            print(f"trajetória não gravada ({type(err).__name__})", file=sys.stderr)
        rows.append(e)
        print(f"{e['id']:4} esperado={e['expected_behavior']:19} obtido={e['status']:19} auto={e['auto']} ({e['elapsed_s']}s)", file=sys.stderr)
        if shared.spent_usd >= args.budget:
            print("orçamento da execução atingido; interrompendo", file=sys.stderr)
            break
    model = getattr(client, "model", "?")
    out_json.write_text(json.dumps({"model": model, "prompts": args.prompts, "spent_usd": shared.spent_usd, "frozen_sha256": sha, "semantic_layer": lexicon.version, "rows": rows},
                                   ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    md = out_json.with_suffix(".md")
    md.write_text(summarize(rows, model, args.prompts, shared.spent_usd, sha), encoding="utf-8")
    print(f"{len(rows)} perguntas -> {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
