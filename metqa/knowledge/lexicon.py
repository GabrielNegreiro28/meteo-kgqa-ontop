"""Léxico: a porta pela qual o EvoOntology entra no caminho de TODA pergunta (documento da arquitetura, §7 e §7.4 regra 6).

O léxico responde "que grandezas da ontologia a pergunta nomeia?" e "que palavras de conteúdo ficaram sem cobertura?". As grandezas viram o
destaque do cardápio do intérprete; as palavras sem cobertura vão para a trilha, que o ciclo de evolução minera (`semantics/evolve.py`).
Assim um sinônimo aprendido pela evolução ("choveu" -> precipitação) passa a mudar o que o intérprete recebe, de forma mensurável.

Dois adaptadores atrás da mesma porta:
  - `OntologyLexicon`: só os rótulos da ontologia formal (sem EvoOntology): a condição "léxico desligado" das ablações (§15).
  - `EvoLexicon`: a camada EvoOntology publicada (`semantics/facade.py` + `semantics/ground.py`), unida aos rótulos formais.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from metqa.knowledge.index import expand

from .catalog import DomainCatalog


@dataclass
class LexiconHit:
    measures: dict[str, str] = field(default_factory=dict)     # IRI -> trecho da pergunta
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)
    info: dict[str, Any] = field(default_factory=dict)          # o que vai para a trilha (evento "semantics")


class Lexicon(Protocol):
    version: str

    def lookup(self, text: str) -> LexiconHit: ...


class OntologyLexicon:
    def __init__(self, catalog: DomainCatalog):
        self.catalog, self.version = catalog, f"ontology:{catalog.index.fingerprint}"

    def lookup(self, text: str) -> LexiconHit:
        found = self.catalog.measures_in(text)
        return LexiconHit(measures=found, info={"layer": self.version, "resolved": [{"phrase": t, "iri": i} for i, t in found.items()],
                                                "ambiguous": [], "unbound": [], "uncovered": []})


class EvoLexicon:
    def __init__(self, catalog: DomainCatalog, workspace: str | Path, version: str | None = None):
        from semantics.facade import GroundedLayer
        from semantics.ground import SemanticGrounder
        self.catalog = catalog
        self.grounder = SemanticGrounder(GroundedLayer.open(workspace, version))
        self.version = self.grounder.version

    def lookup(self, text: str) -> LexiconHit:
        _, info = self.grounder.block(text)
        measures = {expand(r["iri"]): r["phrase"] for r in info["resolved"] if self.catalog.measure(r["iri"])}
        for iri, label in self.catalog.measures_in(text).items():          # rótulo formal que a camada não cobriu (nunca o contrário)
            measures.setdefault(iri, label)
        return LexiconHit(measures=measures, ambiguous=info["ambiguous"], uncovered=info["uncovered"], info=info)
