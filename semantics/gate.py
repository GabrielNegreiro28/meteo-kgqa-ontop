"""Porta de validação BFO-aware (documento da arquitetura, §7.4, regra 4).

Roda ANTES da avaliação pareada de um Candidate. Confere, de forma determinística, o que o agente de evolução não pode
decidir sozinho:
  1. todo Termo governado tem IRI, e o IRI existe na ontologia formal;
  2. a categoria BFO do Termo é a da ontologia (met-bfo.ttl); ela nunca é inventada, e é obrigatória para classes e grandezas;
  3. dois Termos não disputam o mesmo IRI;
  4. as Restrições que o grafo formal também afirma (agregações permitidas, unidade) não o contradizem;
  5. a unidade que uma Restrição cita está entre as que as formas SHACL (ontology/shapes.ttl) admitem;
  6. as Relações do Candidate com semântica OWL (`has_domain`, `has_range`) não tornam a ontologia inconsistente nem deixam classe
     insatisfatível: o raciocinador (HermiT) roda sobre a visão completa OWL 2 DL MAIS esses axiomas, e opcionalmente sobre uma amostra
     do grafo real (`abox`), que é o que pega o defeito do Codex C08.

Limite honesto: Restrição em texto livre não pode ser conferida por regra. Só as que têm forma (`allowed_aggregations`,
`unit`) são comparadas com os axiomas; as demais passam por esta porta e dependem da avaliação pareada e da revisão. Relações de outros
tipos (`observed_as`) não são axiomas OWL e não passam pelo raciocinador. Sem ROBOT/Java o passo 6 é `unavailable`: só vira erro com
`require_reasoner=True` (o modo da execução de evolução).
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


SHAPES_TTL = MET_TTL.parent / "shapes.ttl"
_SH_IN = URIRef("http://www.w3.org/ns/shacl#in")
_UNIT_TOKEN = re.compile(r"unit:(\w+)")


def shape_units(shapes: Path = SHAPES_TTL) -> set[str]:
    """Unidades que as formas SHACL aceitam em qudt:unit (nomes curtos, ex.: DEG_C)."""
    from rdflib.collection import Collection
    g = Graph().parse(shapes)
    out: set[str] = set()
    for lst in g.objects(None, _SH_IN):
        out |= {str(u).rsplit("/", 1)[-1] for u in Collection(g, lst)}
    return out


def _relation_axioms(records: dict[str, Any]) -> list[tuple[URIRef, URIRef, URIRef, str]]:
    """Relações do Candidate com semântica OWL como (s, p, o, id): has_domain -> rdfs:domain, has_range -> rdfs:range."""
    from rdflib.namespace import RDFS
    terms = {t["id"]: t for t in records["terms"]}
    pred = {"has_domain": RDFS.domain, "has_range": RDFS.range}
    out = []
    for r in records["relations"]:
        s, o = terms.get(r.get("source", ""), {}), terms.get(r.get("target", ""), {})
        if r.get("relation_type") in pred and s.get("iri") and o.get("iri"):
            out.append((URIRef(s["iri"]), pred[r["relation_type"]], URIRef(o["iri"]), r["id"]))
    return out


def reasoner_check(records: dict[str, Any], abox: Graph | None = None) -> tuple[str, list[str]]:
    """('ok'|'unavailable', erros). Visão completa + axiomas das Relações do Candidate (+ amostra do grafo real) no HermiT, num arquivo só
    (o ROBOT lê cada arquivo sozinho e propriedade não declarada nele vira anotação: ver DECISOES.md D-84)."""
    import tempfile

    from ontology import build_views as bv
    from ontology import formal_check as fc
    if not fc.available():
        return "unavailable", []
    base = bv.build_dl()
    extra = _relation_axioms(records)

    def consistent(axioms, with_abox: bool) -> tuple[bool, str]:
        g = Graph()
        for t in base:
            g.add(t)
        for s, p, o, _ in axioms:
            g.add((s, p, o))
        if with_abox and abox is not None:
            for t in abox:
                g.add(t)
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "candidate.ttl"
            f.write_text(g.serialize(format="turtle"), encoding="utf-8")
            return fc.reason(f)

    ok, text = consistent(extra, True)
    if ok:
        return "ok", []
    errors = []
    for ax in extra:                                           # qual Relação quebra: uma de cada vez
        if not consistent([ax], True)[0]:
            errors.append(f"{ax[3]}: o raciocinador recusa este axioma (inconsistência ou classe insatisfatível com a ontologia"
                          f"{' e a amostra do grafo real' if abox is not None else ''})")
    if not errors:
        errors.append("a ontologia (visão completa" + (" + amostra do grafo real" if abox is not None else "") + ") já é inconsistente antes do Candidate: "
                      + " ".join(text[-300:].split()))
    return "ok", errors


def validate_candidate(workspace: str | Path, version: str, ontology: Path = MET_TTL, structure: Path = STRUCTURE_TTL,
                       bfo: Path = BFO_TTL, *, abox: Graph | None = None, require_reasoner: bool = False) -> dict[str, Any]:
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
    allowed_units = shape_units()
    for c in records["constraints"]:
        if c.get("constraint_type") == "unit":
            unknown = {u for u in _UNIT_TOKEN.findall(c.get("description", ""))} - allowed_units
            if unknown:
                errors.append(f"{c['id']}: unidade {sorted(unknown)} não é aceita pelas formas SHACL (ontology/shapes.ttl)")
    status, rerrors = reasoner_check(records, abox)
    errors += rerrors
    if status == "unavailable" and require_reasoner:
        errors.append("raciocinador indisponível (ROBOT/Java): modo estrito exige a checagem OWL; instale com ontology/imports/fetch.sh")
    return {"passed": not errors, "version": version, "errors": errors, "reasoner": status}
