"""Congela um conjunto NOVO de perguntas (A1..A5 de docs/PLANO_ABLACAO.md) antes de qualquer execução com LLM.

  python -m eval.freeze_set perguntas_novas.yaml --name novo_a --source "10 perguntas do professor"

Confere o arquivo (formato, ids únicos, campos obrigatórios), recusa perguntas já vistas em qualquer conjunto anterior (o ponto de um conjunto novo é
não ter sido visto), e grava `eval/frozen/<name>/{questions.yaml,manifest.json}` com o sha256. Depois de congelado não se edita: revisão é nova versão.
Não chama LLM e não gasta nada.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
REQUIRED = ("id", "question", "expected_behavior")
BEHAVIORS = {"answerable", "impossible", "ambiguous", "abstain"}


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    return re.sub(r"\W+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip()


def seen_questions(root: Path = ROOT) -> set[str]:
    """Perguntas (normalizadas) de todos os conjuntos já existentes em eval/, inclusive os congelados."""
    out: set[str] = set()
    for f in [*root.glob("questions*.yaml"), *root.glob("independent_evaluation/questions*.yaml"), *root.glob("frozen/*/questions.yaml")]:
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        items = data.get("questions", data) if isinstance(data, dict) else data
        out |= {_norm(q["question"]) for q in items if isinstance(q, dict) and q.get("question")}
    return out


def check(questions: list[dict], seen: set[str]) -> list[str]:
    errors: list[str] = []
    ids = [q.get("id") for q in questions]
    errors += [f"id repetido: {i}" for i in {i for i in ids if ids.count(i) > 1}]
    for q in questions:
        miss = [k for k in REQUIRED if not q.get(k)]
        if miss:
            errors.append(f"{q.get('id', '?')}: faltam campos {miss}")
        elif q["expected_behavior"] not in BEHAVIORS:
            errors.append(f"{q['id']}: expected_behavior '{q['expected_behavior']}' fora de {sorted(BEHAVIORS)}")
        elif _norm(q["question"]) in seen:
            errors.append(f"{q['id']}: pergunta já vista em conjunto anterior (o conjunto novo não pode repetir)")
    return errors


def freeze(src: Path, name: str, source: str, root: Path = ROOT) -> Path:
    data = yaml.safe_load(src.read_text(encoding="utf-8"))
    questions = data["questions"] if isinstance(data, dict) else data
    errors = check(questions, seen_questions(root))
    if errors:
        raise SystemExit("conjunto recusado:\n  " + "\n  ".join(errors))
    out = root / "frozen" / name
    if out.exists():
        raise SystemExit(f"{out} já existe: conjunto congelado não se sobrescreve (use outro --name)")
    out.mkdir(parents=True)
    body = yaml.safe_dump({"questions": questions}, allow_unicode=True, sort_keys=False)
    (out / "questions.yaml").write_bytes(body.encode("utf-8"))
    manifest = {"name": name, "source": source, "frozen_utc": datetime.now(timezone.utc).isoformat(), "count": len(questions),
                "pipeline_executed": False, "files": {"questions.yaml": hashlib.sha256(body.encode("utf-8")).hexdigest()}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def verify(name: str, root: Path = ROOT) -> str:
    d = root / "frozen" / name
    want = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["files"]["questions.yaml"]
    got = hashlib.sha256((d / "questions.yaml").read_bytes()).hexdigest()
    if got != want:
        raise SystemExit(f"conjunto '{name}' alterado depois de congelado: {got} != {want}")
    return got


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file", type=Path)
    ap.add_argument("--name", required=True)
    ap.add_argument("--source", required=True, help="quem gerou as perguntas (outro modelo, professor, usuários reais)")
    a = ap.parse_args(argv)
    out = freeze(a.file, a.name, a.source)
    print(f"congelado em {out} (sha256 {verify(a.name)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
