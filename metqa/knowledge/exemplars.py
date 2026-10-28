"""Memória de exemplos VERIFICADOS: como um caso de borda vira DADO em vez de regra.

Cada vez que o usuário confirma ou corrige uma interpretação (ou uma avaliação a confere contra um oráculo), o par (pergunta, interpretação
normalizada) é guardado. Nas perguntas seguintes, os exemplos mais parecidos vão para as duas leituras do LLM, que segue o mesmo critério —
"das 18h às 6h" corrigido uma vez volta como exemplo, sem código novo. Ter um exemplo parecido também baixa o risco da política.

Só entra o que foi verificado (`verified_by`: "user" | "oracle"); a saída não verificada do LLM nunca entra. A memória é conteúdo da camada
evolutiva (documento da arquitetura, §7.2, Evidência de uso correto): versionada no workspace do EvoOntology e removível.
Similaridade: TF-IDF de trigramas de caracteres com cosseno — determinística, sem gramática.
"""
from __future__ import annotations

import json
import math
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERIFIERS = {"user", "oracle"}


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def _grams(text: str) -> Counter:
    t = f"  {_norm(text)}  "
    return Counter(t[i:i + 3] for i in range(len(t) - 2))


class ExemplarStore:
    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path else None
        self.items: list[dict[str, Any]] = []
        if self.path and self.path.exists():
            self.items = [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    @classmethod
    def in_workspace(cls, workspace: str | Path) -> "ExemplarStore":
        return cls(Path(workspace) / "exemplars" / "verified.jsonl")

    def add(self, question: str, ir: dict[str, Any], verified_by: str, note: str = "") -> bool:
        if verified_by not in VERIFIERS:
            raise ValueError(f"exemplo só entra verificado ({sorted(VERIFIERS)}), não {verified_by!r}")
        if any(_norm(e["question"]) == _norm(question) for e in self.items):
            return False
        item = {"question": question, "ir": ir, "verified_by": verified_by, "note": note,
                "t": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.items.append(item)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        return True

    def search(self, question: str, k: int = 3, min_score: float = 0.35) -> list[dict[str, Any]]:
        if not self.items:
            return []
        docs = [_grams(e["question"]) for e in self.items]
        df = Counter(g for d in docs for g in d)
        n = len(docs) + 1
        idf = lambda g: math.log(n / (1 + df.get(g, 0))) + 1

        def vec(c: Counter) -> dict[str, float]:
            return {g: f * idf(g) for g, f in c.items()}

        def cos(a: dict, b: dict) -> float:
            dot = sum(v * b.get(g, 0.0) for g, v in a.items())
            na, nb = math.sqrt(sum(v * v for v in a.values())), math.sqrt(sum(v * v for v in b.values()))
            return dot / (na * nb) if na and nb else 0.0

        qv = vec(_grams(question))
        scored = sorted(((cos(qv, vec(d)), e) for d, e in zip(docs, self.items)), key=lambda x: -x[0])
        return [{**e, "score": round(s, 3)} for s, e in scored[:k] if s >= min_score]
