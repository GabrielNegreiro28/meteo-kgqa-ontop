"""Memória de exemplos VERIFICADOS: como um caso de borda vira DADO em vez de regra.

Cada vez que o usuário confirma ou corrige uma interpretação (ou uma avaliação a confere contra um oráculo), o par (pergunta, interpretação
normalizada) é guardado. Nas perguntas seguintes, os exemplos mais parecidos vão para as duas leituras do LLM, que segue o mesmo critério —
"das 18h às 6h" corrigido uma vez volta como exemplo, sem código novo. Ter um exemplo parecido também baixa o risco da política.

Só entra o que foi verificado (`verified_by`: "user" | "oracle"); a saída não verificada do LLM nunca entra.

A memória é conteúdo da camada evolutiva (documento da arquitetura, §7.2), versionada com ela (plano, D7):
- fica em `<workspace>/versions/<versão>/exemplars.jsonl`, e cada exemplo leva a impressão digital do catálogo em que foi verificado;
  a busca ignora exemplos de outro catálogo (uma grandeza renomeada não volta como exemplo errado);
- o arquivo é um registro só de acréscimos: verificar de novo a mesma pergunta com outra interpretação SUBSTITUI a anterior
  (`superseded`), e remover é um evento com motivo. Nada é apagado: a história fica auditável.
Similaridade: TF-IDF de trigramas de caracteres com cosseno — determinística, sem gramática.
"""
from __future__ import annotations

import json
import math
import unicodedata
import uuid
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ExemplarStore:
    def __init__(self, path: str | Path | None, catalog: str | None = None):
        self.path, self.catalog = (Path(path) if path else None), catalog
        self.log: list[dict[str, Any]] = []
        if self.path and self.path.exists():
            self.log = [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    @classmethod
    def in_workspace(cls, workspace: str | Path, version: str | None = None, catalog: str | None = None) -> "ExemplarStore":
        """A memória da versão da camada (a ativa, se não for dita)."""
        ws = Path(workspace)
        if version is None:
            try:
                version = json.loads((ws / "active.json").read_text(encoding="utf-8"))["active_version"]
            except (OSError, ValueError, KeyError):
                version = "sem_versao"
        return cls(ws / "versions" / version / "exemplars.jsonl", catalog)

    # ---------------- estado (o registro reaplicado) ----------------
    @property
    def items(self) -> list[dict[str, Any]]:
        """Exemplos vigentes: nem substituídos nem removidos."""
        gone = {e["id"] for e in self.log if e.get("event") in ("superseded", "removed")}
        return [e for e in self.log if e.get("event", "added") == "added" and e["id"] not in gone]

    def _usable(self) -> list[dict[str, Any]]:
        return [e for e in self.items if self.catalog is None or e.get("catalog") == self.catalog]

    def _write(self, entry: dict[str, Any]) -> None:
        self.log.append(entry)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ---------------- operações ----------------
    def add(self, question: str, ir: dict[str, Any], verified_by: str, note: str = "") -> bool:
        """Grava o exemplo. A mesma pergunta com a mesma interpretação não duplica; com outra, substitui a anterior."""
        if verified_by not in VERIFIERS:
            raise ValueError(f"exemplo só entra verificado ({sorted(VERIFIERS)}), não {verified_by!r}")
        same = [e for e in self._usable() if _norm(e["question"]) == _norm(question)]
        if any(e["ir"] == ir for e in same):
            return False
        item = {"event": "added", "id": uuid.uuid4().hex[:12], "question": question, "ir": ir, "verified_by": verified_by, "note": note,
                "catalog": self.catalog, "t": _now()}
        self._write(item)
        for old in same:
            self._write({"event": "superseded", "id": old["id"], "by": item["id"], "t": _now()})
        return True

    def remove(self, exemplar_id: str, reason: str, by: str) -> bool:
        if exemplar_id not in {e["id"] for e in self.items}:
            return False
        self._write({"event": "removed", "id": exemplar_id, "reason": reason, "by": by, "t": _now()})
        return True

    def search(self, question: str, k: int = 3, min_score: float = 0.35) -> list[dict[str, Any]]:
        items = self._usable()
        if not items:
            return []
        docs = [_grams(e["question"]) for e in items]
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
        scored = sorted(((cos(qv, vec(d)), e) for d, e in zip(docs, items)), key=lambda x: -x[0])
        return [{**e, "score": round(s, 3)} for s, e in scored[:k] if s >= min_score]
