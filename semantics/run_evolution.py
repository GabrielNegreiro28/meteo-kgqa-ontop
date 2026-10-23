"""Roda o ciclo de evolução sobre um workspace do EvoOntology (sem LLM; o avaliador é determinístico).

  python -m semantics.run_evolution --workspace .evoontology --parent ontology_v0 --seed-gold --require-reasoner

Por padrão trabalha numa CÓPIA do workspace (`--in-place` para valer de verdade): aceitar um Candidate publica `ontology_vN` e troca
`active.json`, o que é uma decisão de publicação, não um efeito colateral de um teste.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workspace", default=str(ROOT / ".evoontology"))
    ap.add_argument("--parent", default="ontology_v0")
    ap.add_argument("--seed-gold", action="store_true", help="acrescenta trajetórias de semente do gabarito (perguntas de construção)")
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--min-support", type=int, default=2)
    ap.add_argument("--require-reasoner", action="store_true", help="exige o HermiT na porta de validação")
    ap.add_argument("--sample-graph", action="store_true", help="amostra o grafo real (Ontop) para a conformância do raciocinador")
    ap.add_argument("--in-place", action="store_true", help="publica no workspace de verdade (padrão: numa cópia descartável)")
    args = ap.parse_args(argv)

    from semantics.evolve import run_evolution
    from semantics.resolution import CONSTRUCTION_FILES, VALIDATION_FILES, ResolutionAdapter, load_cases
    from semantics.seed import seed_from_gold

    work = Path(args.workspace)
    if not args.in_place:
        work = Path(tempfile.mkdtemp(prefix="evo_")) / "workspace"
        shutil.copytree(args.workspace, work)
        print(f"trabalhando na cópia {work} (o workspace original não muda)")
    if args.seed_gold:
        print(f"{seed_from_gold(work, args.parent)} trajetórias de semente gravadas")
    abox = None
    if args.sample_graph:
        from kgqa.store import OntopBackend
        from ontology.conformance import sample_abox
        abox, found = sample_abox(OntopBackend(), per_class=3)
        print(f"amostra do grafo real: {len(abox)} triplas ({sum(found.values())} indivíduos)")
    validation = load_cases(VALIDATION_FILES)
    regression = load_cases(CONSTRUCTION_FILES)
    summary = run_evolution(work, args.parent, ResolutionAdapter(work, validation), ResolutionAdapter(work, regression),
                            max_rounds=args.max_rounds, min_support=args.min_support, abox=abox, require_reasoner=args.require_reasoner)
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
