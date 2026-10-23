"""Porta de validação BFO-aware (documento da arquitetura, §7.4, regra 4).

Roda ANTES da avaliação pareada de um Candidate. Confere, de forma determinística, o que o agente de evolução não pode
decidir sozinho:
  1. todo Termo governado tem IRI, e o IRI existe na ontologia formal;
  2. a categoria BFO do Termo é a da ontologia (met-bfo.ttl); ela nunca é inventada, e é obrigatória para classes e grandezas;
  3. dois Termos não disputam o mesmo IRI;
  4. as Restrições que o grafo formal também afirma (agregações permitidas, unidade) não o contradizem.

Limite honesto: Restrição em texto livre não pode ser conferida por regra. Só as que têm forma (`allowed_aggregations`,
`unit`) são comparadas com os axiomas; as demais passam por esta porta e dependem da avaliação pareada e da revisão.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from evoontology.ontology.store import SemanticStore
from rdflib import Graph, URIRef

from pipeline.vocab import OntologyIndex, _short

from .build import BFO_REQUIRED, BFO_TTL, MET_TTL, STRUCTURE_TTL, _bfo_table

_AGG = re.compile(r":\s*([A-Za-z, ]+)\.?\s*$")


def validate_candidate(workspace: str | Path, version: str, ontology: Path = MET_TTL, structure: Path = STRUCTURE_TTL,
                       bfo: Path = BFO_TTL) -> dict[str, Any]:
    _, records = SemanticStore.load_records(workspace, version=version)
    formal = Graph().parse(ontology)
    subjects = {str(s) for s in formal.subjects()}
    table = _bfo_table(Graph().parse(bfo))
    idx = OntologyIndex.load(ontology=ontology, structure=structure)
    errors: list[str] = []
    terms = {t["id"]: t for t in records["terms"]}

    seen: dict[str, str] = {}
    for tid, t in terms.items():
        iri = t.get("iri")
        if not iri:
            errors.append(f"{tid}: Termo sem IRI (todo Termo governado carrega o IRI da ontologia)")
            continue
        if iri not in subjects:
            errors.append(f"{tid}: IRI {iri} não existe na ontologia formal")
        if iri in seen:
            errors.append(f"{tid}: IRI {iri} já é de {seen[iri]}")
        seen[iri] = tid
        expected = table.get(iri)
        cat = t.get("bfo_category")
        if t.get("type") in BFO_REQUIRED and not cat:
            errors.append(f"{tid}: falta a categoria BFO (obrigatória para {t.get('type')})")
        if cat and (not expected or cat != expected[0]):
            errors.append(f"{tid}: categoria BFO '{cat}' difere da ontologia ({expected[0] if expected else 'sem alinhamento'}): "
                          "a categoria é copiada da ontologia, nunca inventada")
        if t.get("bfo_iri") and expected and t["bfo_iri"] != expected[1]:
            errors.append(f"{tid}: bfo_iri {t['bfo_iri']} difere da ontologia ({expected[1]})")

    for c in records["constraints"]:
        target = terms.get(c.get("target", ""))
        info = idx.properties.get(target.get("iri", "")) if target else None
        if info is None:
            continue
        if c.get("constraint_type") == "allowed_aggregations":
            m = _AGG.search(c.get("description", ""))
            claimed = {x.strip() for x in m.group(1).split(",") if x.strip()} if m else set()
            if not claimed or not claimed <= info.aggregations:
                errors.append(f"{c['id']}: agregações {sorted(claimed) or '(ilegíveis)'} não estão entre as permitidas pela "
                              f"ontologia para {_short(info.iri)} ({sorted(info.aggregations)})")
        if c.get("constraint_type") == "unit" and info.unit:
            sym = idx.unit_symbols.get(info.unit, "")
            if _short(info.unit) not in c.get("description", "") and (not sym or sym not in c.get("description", "")):
                errors.append(f"{c['id']}: unidade diverge da canônica {sym or _short(info.unit)}")
    return {"passed": not errors, "version": version, "errors": errors}
