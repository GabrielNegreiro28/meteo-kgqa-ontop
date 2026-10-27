"""Linha de comando do MVP.

  python -m metqa "Quanto choveu em SBGL no dia 15 de fevereiro de 2024?"
  python -m metqa --show-query "Quantas horas com chuva houve em SBCY em 2022?"
  python -m metqa --json --lexicon ontology "..."          # sem a camada EvoOntology (ablação)
  python -m metqa < perguntas.txt                          # uma pergunta por linha

Precisa do Ontop no ar e do arquivo de ambiente com a chave (fora do repositório; ver metqa/app/settings.py). O gasto é limitado pelo
--budget desta sessão e pelo teto acumulado do ledger.
"""
from __future__ import annotations

import argparse
import json
import sys

from .settings import Settings


def build(settings: Settings, run: str = "metqa-cli"):
    """Monta o MVP com os adaptadores reais (importa só aqui: a ajuda e os testes não precisam de rede)."""
    from kgqa.store import OntopBackend
    from pipeline.ledger import Ledger, LedgerLLM
    from pipeline.llm import ResilientLLM
    from pipeline.openai_client import OpenAIChatClient, load_env

    from ..knowledge import DomainCatalog, EvoLexicon, OntologyLexicon
    from .pipeline import MetQA

    source = OntopBackend(settings.endpoint)
    catalog = DomainCatalog.from_ontop(source)
    lexicon = EvoLexicon(catalog, settings.workspace, settings.lexicon_version) if settings.lexicon == "evo" else OntologyLexicon(catalog)
    client = OpenAIChatClient.from_env(str(settings.env_file))
    cap = float(load_env(str(settings.env_file)).get("KGQA_BUDGET_USD", "5.0"))
    llm = ResilientLLM(LedgerLLM(client, Ledger(str(settings.ledger)), base_cap_usd=cap, run=run, model=getattr(client, "model", "")),
                       budget_usd=settings.budget_usd)
    return MetQA(catalog, lexicon, llm, source, settings)


def show(result, show_query: bool) -> str:
    r = result.response
    lines = [r.answer_text or f"({r.status.value})"]
    if show_query and r.sparql:
        lines += ["", "SPARQL:", r.sparql]
        if r.provenance and r.provenance.generated_sql:
            lines += ["", "SQL gerado pelo Ontop:", r.provenance.generated_sql]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m metqa", description=__doc__.split("\n\n")[0])
    ap.add_argument("question", nargs="*")
    ap.add_argument("--json", action="store_true", help="resposta completa no contrato 0.2.1")
    ap.add_argument("--show-query", action="store_true", help="mostra o SPARQL e o SQL gerado pelo Ontop")
    ap.add_argument("--lexicon", choices=["evo", "ontology"], help="léxico: camada EvoOntology (padrão) ou só a ontologia formal")
    ap.add_argument("--budget", type=float, help="teto de gasto desta sessão em US$")
    ap.add_argument("--endpoint")
    ap.add_argument("--env", help="arquivo com OPENAI_API_KEY e KGQA_*")
    a = ap.parse_args(argv)
    from pathlib import Path
    settings = Settings.from_env(lexicon=a.lexicon, budget_usd=a.budget, endpoint=a.endpoint, env_file=Path(a.env) if a.env else None)
    questions = [" ".join(a.question)] if a.question else [l.strip() for l in sys.stdin if l.strip()]
    if not questions:
        ap.print_help()
        return 2
    app = build(settings)
    for q in questions:
        res = app.ask(q)
        print(json.dumps(res.response.to_dict(), ensure_ascii=False, indent=1, default=str) if a.json else show(res, a.show_query))
        if len(questions) > 1:
            print()
    return 0
