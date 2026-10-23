"""Linha de comando: pergunte em português sobre os dados meteorológicos.

  python -m kgqa "Qual a temperatura média de SBGL em fevereiro de 2021?"
  python -m kgqa --interactive                          # várias perguntas, uma por linha
  python -m kgqa --json "pergunta"                      # a resposta completa (contrato 0.2.1) em JSON

O que ela faz: interpreta a pergunta (LLM), valida pelas regras, MOSTRA como entendeu e pede confirmação quando houve suposição,
monta ou escreve a consulta, confere pelo motor, executa somente leitura no grafo (Ontop) e responde com ressalvas e procedência.
Sem confirmação possível (entrada não interativa), segue sem perguntar e diz isso.

Gasta dinheiro (LLM): cada pergunta custa centavos e o gasto é limitado pelo teto do ledger (`eval/reports/spend_ledger.jsonl` e
KGQA_BUDGET_USD no kgqa.env), além de `--budget` por sessão. A chave fica no kgqa.env, fora do repositório.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV = ROOT.parent / "METEOROLOGIA" / "kgqa.env"


def render(res, show_query: bool = False) -> str:
    """Texto para a pessoa: estado, resposta (com ressalvas), avisos e, se pedido, a consulta e a procedência."""
    r = res.response
    lines = [f"[{r.status.value}] " + (r.answer_text or "").strip()]
    notes = [d for d in r.diagnostics if d.severity in ("warning", "info") and d.code not in {"COMPILED_QUERY"}]
    if notes and not (r.answer_text or "").strip():
        lines.append("; ".join(d.message for d in notes[:3]))
    elif r.status.value not in ("answered",) and r.diagnostics:
        lines.append("Motivo: " + "; ".join(f"{d.code}: {d.message}" for d in r.diagnostics[:3]))
    if show_query:
        if r.sparql:
            lines += ["", "Consulta SPARQL:", r.sparql]
        p = r.provenance
        if p:
            lines += ["", f"Procedência: fonte {p.source_id}; versões {json.dumps(p.versions, ensure_ascii=False)}"
                      + ("" if p.complete else "; ATENÇÃO: procedência incompleta")]
    return "\n".join(lines)


def make_confirm(policy: str):
    """Pergunta no terminal quando há suposição. Sem terminal interativo não há como perguntar: segue e o diz."""
    if policy == "never" or not sys.stdin.isatty():
        return None

    def confirm(text: str) -> str:
        print(text)
        return input("> ")
    return confirm


def build_runtime(args):
    """Backend, índice, LLM com teto de gasto e (se o prompt pedir) a camada semântica. Importa só aqui: ajuda e testes não precisam da rede."""
    from kgqa.store import OntopBackend
    from pipeline.ledger import Ledger, LedgerLLM
    from pipeline.llm import ResilientLLM
    from pipeline.openai_client import OpenAIChatClient, load_env
    from pipeline.prompts import VERSIONS
    from pipeline.vocab import OntologyIndex

    backend = OntopBackend(args.endpoint) if args.endpoint else OntopBackend()
    index = OntologyIndex.from_ontop(backend)
    client = OpenAIChatClient.from_env(args.env)
    ledger = Ledger(str(ROOT / "eval" / "reports" / "spend_ledger.jsonl"))
    cap = float(load_env(args.env).get("KGQA_BUDGET_USD", "5.0"))
    llm = ResilientLLM(LedgerLLM(client, ledger, base_cap_usd=cap, run="cli", model=getattr(client, "model", "")), budget_usd=args.budget)
    grounder = None
    if VERSIONS[args.prompts].semantic:
        from semantics.facade import GroundedLayer
        from semantics.ground import SemanticGrounder
        grounder = SemanticGrounder(GroundedLayer.open(str(ROOT / ".evoontology"), None))
    return backend, index, llm, grounder


def ask(question: str, args, runtime) -> object:
    from pipeline.orchestrator import run_pipeline
    backend, index, llm, grounder = runtime
    return run_pipeline(question, llm, backend, index, timeout_s=args.timeout, prompts_version=args.prompts,
                        confirm=make_confirm(args.confirm), confirm_policy=args.confirm, semantics=grounder)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m kgqa", description=__doc__.split("\n\n")[0])
    ap.add_argument("question", nargs="*", help="a pergunta (ou use --interactive)")
    ap.add_argument("--interactive", "-i", action="store_true", help="lê perguntas da entrada, uma por linha")
    ap.add_argument("--prompts", default="v7", choices=["v4", "v5", "v6", "v7"],
                    help="versão do prompt; v7 monta por código a agregação simples e a contagem com limiar (padrão)")
    ap.add_argument("--confirm", default="assumptions", choices=["assumptions", "always", "never"],
                    help="quando mostrar a interpretação e pedir confirmação")
    ap.add_argument("--budget", type=float, default=0.10, help="teto de gasto desta sessão em US$ (estimado)")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--env", default=str(DEFAULT_ENV), help="arquivo com OPENAI_API_KEY e KGQA_* (nunca é lido por esta ajuda)")
    ap.add_argument("--endpoint", help="URL do endpoint SPARQL do Ontop (padrão: http://127.0.0.1:8080/sparql)")
    ap.add_argument("--show-query", action="store_true", help="mostra o SPARQL e a procedência")
    ap.add_argument("--json", action="store_true", help="imprime a resposta completa em JSON")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    questions = [" ".join(args.question)] if args.question else []
    if not questions and not args.interactive:
        parser().print_usage(sys.stderr)
        return 2
    try:
        runtime = build_runtime(args)
    except Exception as e:                                  # noqa: BLE001 — sem backend ou sem chave: dizer o que falta, sem detalhe interno
        print(f"Não consegui iniciar: {type(e).__name__}. Confira se o Ontop está no ar (infra/ontop.sh start) e o kgqa.env.", file=sys.stderr)
        return 1
    if args.interactive:
        questions += [line.strip() for line in sys.stdin if line.strip()]
    code = 0
    for q in questions:
        res = ask(q, args, runtime)
        print(json.dumps(res.response.to_dict(), ensure_ascii=False, indent=1, default=str) if args.json else render(res, args.show_query))
        print()
        code = code or (0 if res.response.status.value in ("answered", "no_results", "unsupported", "needs_clarification") else 1)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
