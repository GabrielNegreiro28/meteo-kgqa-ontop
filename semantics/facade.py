"""Fachada própria sobre o EvoOntology (documento da arquitetura, §7.4, regra 6: "interface estável").

O núcleo do EvoOntology descarta, ao carregar, qualquer campo que não conheça (`Term.from_dict`); o IRI e a categoria BFO
que o documento exige nos Termos existem no JSON em disco, mas não chegam ao agente. A fachada lê os registros crus e
acrescenta `iri`, `bfo_category` e `formal_status` a cada Termo devolvido por `resolve_semantics` e `browse_semantics`.

O resto do sistema só enxerga esta classe: se o formato interno do EvoOntology mudar, muda aqui.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from evoontology.ontology.store import SemanticStore
from evoontology.runtime.runtime import SemanticLayer

from .build import BFO_REQUIRED


class GroundedLayer(SemanticLayer):
    """SemanticLayer que devolve, junto de cada Termo, o IRI da ontologia formal e a categoria BFO."""

    def __init__(self, store: SemanticStore, bindings: dict[str, dict[str, Any]]):
        super().__init__(store)
        self.bindings = bindings

    @classmethod
    def open(cls, workspace: str | Path, version: str | None = None) -> "GroundedLayer":
        """Abre a versão ativa, ou uma explícita (a avaliação de Candidates não pode trocar `active.json`)."""
        store = SemanticStore.load_version(workspace, version) if version else SemanticStore.load(workspace)
        _, records = SemanticStore.load_records(workspace, version=store.version)
        bindings = {r["id"]: {"iri": r.get("iri"), "bfo_category": r.get("bfo_category"), "bfo_iri": r.get("bfo_iri"),
                              "type": r.get("type", "")} for r in records["terms"]}
        return cls(store, bindings)

    def _bind(self, term: dict[str, Any]) -> dict[str, Any]:
        b = self.bindings.get(term.get("id", ""), {})
        term["iri"], term["bfo_category"], term["bfo_iri"] = b.get("iri"), b.get("bfo_category"), b.get("bfo_iri")
        # "unbound": o Termo não tem como virar IRI (ou lhe falta a categoria obrigatória). O interpretador não pode usá-lo.
        needs_bfo = b.get("type") in BFO_REQUIRED
        term["formal_status"] = "bound" if b.get("iri") and (b.get("bfo_category") or not needs_bfo) else "unbound"
        return term

    def resolve(self, mentions: list[str] | None = None, context: str | None = None) -> dict[str, Any]:
        out = super().resolve(mentions=mentions, context=context)
        for r in out["results"]:
            for item in (r, *r.get("candidates", [])):
                if "term" in item:
                    self._bind(item["term"])
        return out

    def browse(self, query: str = "", kind: str = "term", limit: int = 6) -> dict[str, Any]:
        out = super().browse(query=query, kind=kind, limit=limit)
        for item in out.get("items", []):
            if item.get("id") in self.bindings:
                self._bind(item)
        return out

    def manifest(self, exposed_tools: list[str] | None = None) -> str:
        text = super().manifest(exposed_tools)
        if self.store.version == "uninitialized":
            return text
        bound = sum(1 for t in self.store.terms if self._bind({"id": t})["formal_status"] == "bound")
        return text + (
            f"\n\n### Ligação com a ontologia formal\n"
            f"- {bound} de {len(self.store.terms)} Termos têm IRI e categoria BFO. Use SEMPRE o campo `iri` na consulta; "
            "um Termo com formal_status=unbound não pode ser usado.\n"
            "- O EvoOntology aconselha (sinônimos, ressalvas); quem define o significado é a ontologia formal."
        )
