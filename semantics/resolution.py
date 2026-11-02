"""Avaliação sem LLM da camada semântica: ela RESOLVE a grandeza certa a partir da pergunta?

O ciclo de evolução (§7.3) compara o Parent e o Candidate "nas mesmas condições". A comparação que mede o efeito final (resposta certa com a
camada v5 contra sem ela) usa o LLM e custa dinheiro. Esta aqui é a parte determinística e gratuita: dada uma pergunta com resposta de referência,
o `SemanticGrounder` (a mesma peça que a pipeline usa) reconhece a grandeza que a consulta de referência usa?

  - o gabarito (ground truth) vem da CONSULTA DE REFERÊNCIA de cada pergunta: as grandezas `met:` que ela cita;
  - o escore por pergunta é Jaccard(grandezas reconhecidas, grandezas do gabarito), de 0 a 1; reconhecimento ambíguo não conta;
  - construção e validação são conjuntos DISJUNTOS de arquivos de perguntas: o minerador de trajetórias só vê a construção, e o Candidate só é
    aceito pelo que faz na validação congelada (+ uma checagem de regressão sobre a construção).

Limite honesto: mede o reconhecimento de sinônimos e grandezas, não se a resposta final melhora. Um Candidate que resolve melhor pode, em
tese, não mudar a resposta; o efeito ponta a ponta fica para a ablação com LLM (docs/PLANO_ABLACAO.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from metqa.knowledge.index import OntologyIndex, expand

from .facade import GroundedLayer
from .ground import SemanticGrounder

ROOT = Path(__file__).resolve().parent.parent
CONSTRUCTION_FILES = ("questions.yaml", "questions_real.yaml", "questions_real_probe.yaml")
VALIDATION_FILES = ("questions_heldout.yaml", "questions_fresh.yaml", "questions_real_fresh.yaml", "questions_real_gen.yaml")
_MET = re.compile(r"\bmet:(\w+)")


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    gold: frozenset[str]            # IRIs de grandezas observáveis que a consulta de referência usa
    source: str


def gold_properties(sparql: str, index: OntologyIndex) -> frozenset[str]:
    return frozenset(i for i in (expand("met:" + n) for n in _MET.findall(sparql)) if i in index.properties)


def load_cases(files: tuple[str, ...], index: OntologyIndex | None = None) -> list[Case]:
    index = index or OntologyIndex.load()
    cases: list[Case] = []
    for name in files:
        for q in yaml.safe_load((ROOT / "eval" / name).read_text(encoding="utf-8"))["questions"]:
            gold = gold_properties(q.get("sparql", ""), index) if q.get("sparql") else frozenset()
            if gold and q.get("expected_status", "answered") == "answered":
                cases.append(Case(f"{name.removesuffix('.yaml')}:{q['id']}", q["question"], gold, name))
    return cases


def score(resolved: set[str], gold: frozenset[str]) -> float:
    return len(resolved & gold) / len(resolved | gold) if (resolved | gold) else 1.0


class ResolutionAdapter:
    """EvolutionAdapter (protocolo do núcleo): avalia uma versão da camada sobre um conjunto de casos."""

    def __init__(self, workspace: str | Path, cases: list[Case]):
        self.workspace = Path(workspace)
        self.cases = {c.id: c for c in cases}

    def evaluate(self, subject: str, cases: list[str] | None = None, output_hint: str | None = None) -> dict[str, Any]:
        grounder = SemanticGrounder(GroundedLayer.open(self.workspace, subject))
        rows = []
        for cid in (cases if cases is not None else sorted(self.cases)):
            c = self.cases[cid]
            resolved = {m.result["term"]["iri"] for m in grounder.ground(c.question).resolved}
            s = score(resolved, c.gold)
            rows.append({"id": cid, "score": s, "status": "exact" if s == 1.0 else "miss" if s == 0.0 else "partial"})
        mean = sum(r["score"] for r in rows) / len(rows) if rows else 0.0
        return {"metrics": {"mean_score": mean, "n": len(rows), "exact": sum(r["status"] == "exact" for r in rows)}, "cases": rows,
                "artifact_paths": [], "provenance": "semantics.resolution (determinístico, sem LLM)"}
