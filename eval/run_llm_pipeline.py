"""Roda a pipeline completa com um LLM sobre as perguntas da suíte sintética e mede segurança e acerto.

Uso:
  python -m eval.run_llm_pipeline --dry-run                  # arcabouço com LLM roteirizado (sem rede, custo zero)
  python -m eval.run_llm_pipeline --env ../METEOROLOGIA/kgqa.env [--split dev|test] [--budget 2.0] [--limit N]

Saídas: eval/reports/llm_run.json (por pergunta) e docs/RESULTADOS_LLM_REAL.md (resumo).
Os prompts (pipeline/prompts.py) não contêm exemplos tirados das perguntas, então `test` não vaza para o prompt.

Métrica central de segurança: respostas ERRADAS ENTREGUES (status final answered, resultado diferente do oráculo).
Ablação com LLM real: a PRIMEIRA tentativa do modelo é executada sem as regras para ver o que teria chegado ao
usuário, e comparada com o que cada camada barrou.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from eval import oracle
from eval.compare import compare_flexible as flexible_compare
from eval.compare import judge
from eval.run_reference import SUITES, load_questions
from eval.safety_experiment import CASES
from kgqa.contract import Status
from kgqa.store import PREFIXES, LocalRdflibBackend
from kgqa.verify import result_status
from pipeline.ledger import Ledger, LedgerLLM
from pipeline.llm import LLMError, ResilientLLM, ScriptedLLM
from pipeline.orchestrator import run_pipeline
from pipeline.validators import PipelineInterpretation, validate_query
from pipeline.vocab import OntologyIndex

ROOT = Path(__file__).resolve().parent.parent
ANSWERABLE = {"answered", "no_results"}


def make_llm(args) -> tuple[object, ResilientLLM]:
    if args.dry_run:
        script = {}
        for qid, (interp, _) in CASES.items():
            q = QUESTIONS[qid]
            script[qid] = {"interpret": [json.dumps({"status": "ok", "properties": interp.properties, "entities": interp.entities,
                                                      "filters": interp.filters, "period": interp.period,
                                                      "aggregation": interp.aggregation, "record_kind": "observation"})],
                           "generate": [json.dumps({"sparql": q["sparql"]})],
                           "answer": [json.dumps({"answer": "Resultado conforme a consulta."})]}
        return None, script                                              # roteiro por pergunta
    from pipeline.openai_client import OpenAIChatClient
    return OpenAIChatClient.from_env(args.env), None


def evaluate(q: dict, res, backend) -> dict:
    r = res.response
    entry = {"id": q["id"], "split": q["split"], "category": q["category"], "expected_status": q["expected_status"],
             "status": r.status.value, "status_ok": r.status.value == q["expected_status"],
             "diagnostics": [d.code for d in r.diagnostics], "answer_text": r.answer_text, "sparql": r.sparql,
             "fallback": any(d.code == "ANSWER_FALLBACK" for d in r.diagnostics), "result_match": None,
             "compiled": any(d.code == "COMPILED_QUERY" for d in r.diagnostics)}     # consulta montada pelo compilador, não pelo LLM
    calls = Counter(t["stage"] for t in res.trace if t["event"] == "llm")
    errors = [t for t in res.trace if t["event"] == "llm_error"]
    entry["llm_calls"] = dict(calls)
    entry["repairs"] = sum(max(0, n - 1) for n in calls.values())
    entry["llm_errors"] = [e["kind"] for e in errors]
    entry["llm_error_detail"] = [{"stage": e["stage"], "detail": e.get("detail"), "raw": e.get("raw")} for e in errors]
    entry["diag_messages"] = [{"code": d.code, "message": d.message[:300], "details": d.details} for d in r.diagnostics]
    entry["cost_usd"] = round(sum(t.get("cost", 0) for t in res.trace if t["event"] == "llm"), 5)
    entry["elapsed_ms"] = next((t["t_ms"] for t in res.trace if t["event"] == "end"), None)
    if "sparql" in q and r.results is not None:
        same, why, quality = judge(r.results, ORACLE.expected(q["id"]), q["compare"])
        entry["result_match"], entry["match_note"], entry["quality"] = same, why, quality
        entry["mismatch"] = None if same else why
    # primeira tentativa do modelo: o que teria acontecido sem as regras
    first_q = next((t for t in res.trace if t["event"] == "validate_query"), None)
    # a interpretação ACEITA (a última antes da 1ª consulta): a 1ª interpretação pode ter sido recusada e reparada, e a
    # consulta foi gerada da reparada; compará-la com a recusada fabricaria achados que não existiram
    before = res.trace[:res.trace.index(first_q)] if first_q else []
    first_i = next((t for t in reversed(before) if t["event"] == "validate_interpretation"), None)
    entry["first_attempt"] = None
    if first_q and first_i:
        from pipeline.orchestrator import _to_interpretation
        interp = PipelineInterpretation(**{**_to_interpretation(first_i["interpretation"]).__dict__})
        _, findings = validate_query(first_q["sparql"], interp, INDEX, PROMPTS_GROUNDED)
        layers = sorted({f.layer for f in findings})
        truth = None
        if "sparql" in q and "L1" not in layers:
            ex = backend.select(PREFIXES + first_q["sparql"], timeout_s=30)
            if not ex.ok:
                truth = "surfaced_error"
            else:
                same, _, _ = judge(ex.results, ORACLE.expected(q["id"]), q["compare"])
                status, _ = result_status(ex.results)
                truth = "correct" if same else ("surfaced_empty" if status == Status.NO_RESULTS else "silent_wrong")
        elif "L1" in layers:
            truth = "blocked_l1"
        entry["first_attempt"] = {"layers": layers, "codes": [f.diag.code for f in findings], "truth": truth,
                                  "sparql": first_q["sparql"]}
    return entry


def summarize(rows: list[dict], model: str, spent: float, dropped: list[str], graph: str = "**sintético** (rdflib)") -> str:
    def block(sub: list[dict], title: str) -> list[str]:
        n = len(sub)
        if not n:
            return []
        ans = [r for r in sub if r["expected_status"] in ANSWERABLE and r["result_match"] is not None]
        beh = [r for r in sub if r["expected_status"] not in ANSWERABLE]
        wrong = [r for r in ans if r["status"] == "answered" and not r["result_match"]]
        false_empty = [r for r in ans if r["status"] == "no_results" and r["expected_status"] == "answered" and not r["result_match"]]
        over = [r for r in sub if r["expected_status"] in ANSWERABLE and r["status"] in ("unsupported", "needs_clarification", "rejected", "execution_error")]
        under = [r for r in beh if r["status"] in ("answered", "no_results")]
        return [f"### {title} (n={n})", "",
                f"- status final igual ao esperado: **{sum(r['status_ok'] for r in sub)}/{n}**",
                f"- respondíveis com resultado conferido: {sum(bool(r['result_match']) for r in ans)}/{len(ans)} corretas"
                f" (das quais {sum(r.get('quality') == 'incomplete' for r in ans)} incompletas — faltam colunas que a referência pede — e "
                f"{sum(r.get('quality') == 'order_only' for r in ans)} em outra ordem)",
                f"- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **{len(wrong)}**"
                + (": " + ", ".join(r["id"] for r in wrong) if wrong else ""),
                f"- **falsa ausência de registros** (disse 'não há registros' onde há dados): **{len(false_empty)}**"
                + (": " + ", ".join(r["id"] for r in false_empty) if false_empty else ""),
                f"- abstenções indevidas (pergunta respondível recusada): {len(over)}" + (": " + ", ".join(f"{r['id']}→{r['status']}" for r in over) if over else ""),
                f"- respostas a perguntas que deveriam ser recusadas/esclarecidas: {len(under)}" + (": " + ", ".join(r["id"] for r in under) if under else ""),
                f"- reparos usados: {sum(r['repairs'] for r in sub)} · respostas de reserva (texto determinístico): {sum(r['fallback'] for r in sub)}"
                f" · consultas montadas pelo compilador (não são acerto do LLM): {sum(r.get('compiled', False) for r in sub)}",
                f"- erros de LLM: {dict(Counter(e for r in sub for e in r['llm_errors'])) or 'nenhum'}", ""]
    L = ["# Resultados com LLM roteirizado (dry-run)" if model.startswith("dry-run") else "# Resultados com LLM real", "", f"Modelo: `{model}` · custo estimado: US$ {spent:.4f} · gerado por `python -m eval.run_llm_pipeline`.", ""]
    if dropped:
        L += [f"Parâmetros recusados pelo modelo e removidos: {sorted(set(dropped))}", ""]
    L += [f"Resultados sobre o grafo {graph}. Comparação com o oráculo independente.", ""]
    L += block(rows, "Todas") + block([r for r in rows if r["split"] == "dev"], "dev") + block([r for r in rows if r["split"] == "test"], "test")
    fa = [r for r in rows if r["first_attempt"] and r["first_attempt"]["truth"]]
    L += ["## Ablação sobre a primeira tentativa do modelo", "",
          "Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.", "",
          "| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |", "|---|---:|---:|---:|---:|---:|"]
    for truth in ("correct", "silent_wrong", "surfaced_empty", "surfaced_error", "blocked_l1"):
        sub = [r for r in fa if r["first_attempt"]["truth"] == truth]
        if not sub:
            continue
        first = Counter(next((l for l in ("L1", "L2", "L3") if l in r["first_attempt"]["layers"]), "—") for r in sub)
        L.append(f"| {truth} | {len(sub)} | {first['L1']} | {first['L2']} | {first['L3']} | {first['—']} |")
    L += ["", "`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).", "",
          "## Por pergunta", "", "| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        f = r["first_attempt"]
        L.append(f"| {r['id']} | {r['split']} | {r['expected_status']} | {r['status']} | "
                 f"{'ok' if r['result_match'] else ('ERRADO' if r['result_match'] is False else '—')} | {r['repairs']} | "
                 f"{'sim' if r['fallback'] else ''} | {(','.join(f['codes']) or 'ok') if f else '—'} |")
    return "\n".join(L) + "\n"


QUESTIONS = {q["id"]: q for q in load_questions()}
PROMPTS_GROUNDED = False
ORACLE = oracle
INDEX = OntologyIndex.load()


def reevaluate(path: Path, model: str, dropped: list[str], backend=None, graph: str = "**sintético** (rdflib)") -> Path:
    """Recalcula result_match e a verdade da 1ª tentativa executando de novo as consultas gravadas (sem LLM)."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    backend = backend or LocalRdflibBackend()
    for e in rows:
        q = QUESTIONS[e["id"]]
        if "sparql" not in q:
            continue
        def truth_of(sparql):
            ex = backend.select(PREFIXES + sparql, timeout_s=30)
            if not ex.ok:
                return "surfaced_error", None, None, None
            same, why, quality = judge(ex.results, ORACLE.expected(q["id"]), q["compare"])
            status, _ = result_status(ex.results)
            return ("correct" if same else ("surfaced_empty" if status == Status.NO_RESULTS else "silent_wrong")), same, why, quality
        if e["sparql"] and e["status"] in ("answered", "no_results"):
            _, same, why, quality = truth_of(e["sparql"])
            e["result_match"], e["mismatch"], e["quality"] = same, (None if same else why), quality
        fa = e.get("first_attempt")
        if fa and fa["truth"] not in (None, "blocked_l1"):
            src = fa.get("sparql") or (e["sparql"] if e["repairs"] == 0 else None)
            if src:
                fa["truth"] = truth_of(src)[0]
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    out = ROOT / "docs" / (path.stem.replace("llm_run_", "RESULTADOS_LLM_REAL_") + ".md")
    out.write_text(summarize(rows, model, sum(r["cost_usd"] for r in rows), dropped, graph), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(ROOT.parent / "METEOROLOGIA" / "kgqa.env"))
    ap.add_argument("--split", choices=["dev", "test"])
    ap.add_argument("--budget", type=float, default=2.0, help="teto desta execução em US$ (estimado)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prompts", choices=["v1", "v2", "v3", "v4", "v5", "v6", "v7"], default="v1")
    ap.add_argument("--semantic-workspace", default=str(ROOT / ".evoontology"), help="workspace da camada semântica (só v5)")
    ap.add_argument("--semantic-version", help="versão da camada (padrão: a ativa); a de um Candidate não troca a ativa")
    ap.add_argument("--ledger", default=str(ROOT / "eval" / "reports" / "spend_ledger.jsonl"),
                    help="registro persistente de gasto; o teto (KGQA_BUDGET_USD + autorizações) vale para a SOMA de tudo")
    ap.add_argument("--authorize-usd", type=float, help="eleva o teto acumulado em US$ (exige --authorized-by e --reason)")
    ap.add_argument("--authorized-by")
    ap.add_argument("--reason")
    ap.add_argument("--record-trajectories", metavar="WORKSPACE",
                    help="grava cada pergunta como trajetória do EvoOntology (com os sinais do §13 e o veredito da avaliação) em WORKSPACE/trajectories")
    ap.add_argument("--ids", help="só estas perguntas (ex.: H02,G01); para refazer poucas após uma correção, a custo mínimo")
    ap.add_argument("--tag", default="", help="sufixo dos arquivos de saída (ex.: _r2), para repetições")
    ap.add_argument("--suite", choices=["synthetic", "heldout", "fresh", "real", "real_fresh", "real_gen", "real_probe"], default="synthetic",
                    help="'real' usa o Ontop (grafo real) e o índice construído dele; precisa do endpoint no ar e do DuckDB do oráculo")
    ap.add_argument("--reevaluate", help="recalcula as métricas de um llm_run_*.json sem chamar o LLM")
    args = ap.parse_args()
    global QUESTIONS, ORACLE, PROMPTS_GROUNDED, INDEX
    from pipeline.prompts import VERSIONS
    PROMPTS_GROUNDED = VERSIONS[args.prompts].grounded
    QUESTIONS = {q["id"]: q for q in load_questions(suite=args.suite)}
    ORACLE = SUITES[args.suite][1]
    real = args.suite in ("real", "real_fresh", "real_gen", "real_probe")
    backend = SUITES[args.suite][2]()                 # LocalRdflibBackend (sintético) ou OntopBackend (real)
    graph = "**real** (Ontop sobre PostgreSQL)" if real else "**sintético** (rdflib)"
    if real:
        INDEX = OntologyIndex.from_ontop(backend)     # estações, cobertura e grandezas com dados vêm do grafo real
    if args.reevaluate:
        print(reevaluate(Path(args.reevaluate), f"gpt-6-luna (prompts {args.prompts})", ["response_format"], backend, graph))
        return 0
    client, scripts = make_llm(args)
    ledger = Ledger(args.ledger)
    if args.authorize_usd:
        if not (args.authorized_by and args.reason):
            print("--authorize-usd exige --authorized-by e --reason", file=sys.stderr)
            return 2
        ledger.authorize(args.authorize_usd, by=args.authorized_by, reason=args.reason)
    grounder = None
    if VERSIONS[args.prompts].semantic:
        from semantics.facade import GroundedLayer
        from semantics.ground import SemanticGrounder
        grounder = SemanticGrounder(GroundedLayer.open(args.semantic_workspace, args.semantic_version))
        print(f"camada semântica: {grounder.version}", file=sys.stderr)
    qs = [q for q in QUESTIONS.values() if args.split in (None, q["split"])]
    if args.dry_run:
        qs = [q for q in qs if q["id"] in scripts]
    if args.ids:
        wanted = args.ids.split(",")
        qs = [q for q in qs if q["id"] in wanted]
    qs = qs[: args.limit] if args.limit else qs
    if args.dry_run:
        shared = None
    else:
        from pipeline.openai_client import load_env
        cap = float(load_env(args.env).get("KGQA_BUDGET_USD", "5.0"))
        print(f"gasto acumulado registrado: US$ {ledger.total():.2f} · teto acumulado: US$ {cap + ledger.authorized_extra():.2f}", file=sys.stderr)
        tracked = LedgerLLM(client, ledger, base_cap_usd=cap, run=f"{args.suite}_{args.prompts}{args.tag}", model=getattr(client, "model", ""))
        shared = ResilientLLM(tracked, budget_usd=args.budget)
    rows, spent = [], 0.0
    for q in qs:
        llm = ResilientLLM(ScriptedLLM(scripts[q["id"]])) if args.dry_run else shared
        t0 = time.perf_counter()
        infra_retries = 0
        while True:
            try:
                res = run_pipeline(q["question"], llm, backend, INDEX, timeout_s=SUITES[args.suite][3] if real else 30,
                                   prompts_version=args.prompts, semantics=grounder)
            except LLMError as e:                   # defesa extra: nada deve escapar do orquestrador
                print(f"{q['id']}: erro não tratado {e.kind}", file=sys.stderr)
                res = None
                break
            # Falha de INFRAESTRUTURA (rede, limite de taxa, disjuntor aberto) não é resultado do sistema: espera o disjuntor
            # fechar e refaz a pergunta, registrando as tentativas. Sem isto, uma queda de rede apaga as perguntas seguintes.
            infra = {"TIMEOUT", "CIRCUIT_OPEN", "RATE_LIMITED"}
            # só a falha do LLM é de infraestrutura. O TIMEOUT de uma consulta lenta no Ontop tem o mesmo código, mas refazer a pergunta
            # reexecutaria as chamadas ao LLM (até 4x o custo daquela pergunta) para obter o mesmo timeout.
            llm_infra = any(t["event"] == "llm_error" and str(t.get("kind", "")).upper() in infra for t in res.trace)
            if (res.response.status == Status.EXECUTION_ERROR and {d.code for d in res.response.diagnostics} & infra
                    and llm_infra and infra_retries < 3 and not args.dry_run):
                infra_retries += 1
                print(f"{q['id']}: falha de infraestrutura; aguardando 35 s (tentativa {infra_retries}/3)", file=sys.stderr)
                time.sleep(35)
                continue
            break
        if res is None:
            continue
        e = evaluate(q, res, backend)
        e["infra_retries"] = infra_retries
        if args.record_trajectories:                  # insumo do ciclo de evolução (§7.3): a trilha da pipeline no formato do EvoOntology
            from semantics.trajectories import record_trajectory
            record_trajectory(args.record_trajectories, res, split=q["split"], ontology_version=grounder.version if grounder else "",
                              extra={k: e.get(k) for k in ("expected_status", "status_ok", "result_match", "quality", "category")})
        rows.append(e)
        print(f"{e['id']:4} {e['split']:4} esperado={e['expected_status']:19} obtido={e['status']:19} "
              f"resultado={e['result_match']} reparos={e['repairs']} ({time.perf_counter() - t0:.1f}s)", file=sys.stderr)
        if shared and shared.spent_usd >= args.budget:
            print("orçamento da execução atingido; interrompendo", file=sys.stderr)
            break
    spent = shared.spent_usd if shared else 0.0
    model = "dry-run (LLM roteirizado)" if args.dry_run else getattr(client, "model", "?")
    (ROOT / "eval" / "reports").mkdir(exist_ok=True)
    (ROOT / "eval" / "reports" / ("llm_run_dry.json" if args.dry_run else f"llm_run_{args.prompts}{args.tag}.json")).write_text(
        json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    out = ROOT / "docs" / ("RESULTADOS_LLM_DRYRUN.md" if args.dry_run else f"RESULTADOS_LLM_REAL_{args.prompts}{args.tag}.md")
    out.write_text(summarize(rows, model, spent, getattr(client, "dropped_params", []) if client else [], graph), encoding="utf-8")
    print(f"{len(rows)} perguntas -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
