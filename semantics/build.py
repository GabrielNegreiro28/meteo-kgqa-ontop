"""Versão 0 da camada do EvoOntology, gerada da ontologia formal (nenhum texto escrito à mão).

Documento da arquitetura, §7.3: "o construtor é semeado com a ontologia de domínio: toda classe e propriedade governada
recebe um Termo com rótulo, definição, IRI e categoria BFO". Aqui isso é determinístico: mesma ontologia, mesmos registros.

O que entra e o que não entra na v0:
  - Termos: classes, grandezas observáveis e propriedades com rótulo em met.ttl. Estações NÃO são Termos (são entidades,
    resolvidas pelo índice de identidades, §8); conceitos SKOS de gênero de nuvem ficam de fora até terem categoria BFO.
  - Relações e Restrições: derivadas de met.ttl e met-structure.ttl (domínio/imagem, tipo de observação, agregações,
    unidade, contenção de período).
  - Evidências: só a procedência da ontologia. Perguntas de eval/ NÃO viram evidência: o conjunto de avaliação da evolução
    tem de ficar separado do que alimenta a camada, senão o ganho medido seria vazamento.
  - Mapeamentos: vazio. No documento são ponteiros consultivos; o mapeamento executável é o do Ontop.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rdflib import OWL, RDF, RDFS, Graph, Literal, URIRef
from rdflib.namespace import SKOS

from pipeline.vocab import MET, OntologyIndex, _short, fold

ROOT = Path(__file__).resolve().parent.parent
MET_TTL = ROOT / "ontology" / "met.ttl"
STRUCTURE_TTL = ROOT / "ontology" / "met-structure.ttl"
BFO_TTL = ROOT / "ontology" / "met-bfo.ttl"

BFO_CATEGORY = URIRef(MET + "bfoCategory")
SOSA_OBSERVABLE = URIRef("http://www.w3.org/ns/sosa/ObservableProperty")
EVIDENCE_NS = "https://example.org/kgqa-met/evidence/"     # IRIs das entidades PROV-O das Evidências (§7.4 r.3)
SOURCE = "ontology/met.ttl"
METHOD = "derivado da ontologia (determinístico)"

# Tipos de Termo cuja categoria BFO é obrigatória (propriedades de dados/objeto não são categorizadas pela BFO).
BFO_REQUIRED = {"class", "observable_property"}


def term_id(iri: str) -> str:
    return "term." + iri.rsplit("#", 1)[-1]


def _label(g: Graph, s: URIRef, pred=RDFS.label, lang: str = "pt") -> list[str]:
    out = [o for o in g.objects(s, pred) if isinstance(o, Literal)]
    return [str(o) for o in out if o.language == lang] + [str(o) for o in out if o.language not in (None, lang)]


def _aliases(name: str, *groups: list[str]) -> list[str]:
    """Rótulos e sinônimos, cada um também sem acento: o casamento de menções do EvoOntology diferencia 'estação' de
    'estacao' e suas palavras vazias são só em inglês, então a normalização é feita aqui, na construção."""
    seen, out = {name.lower()}, []
    for text in (t for g in groups for t in g):
        for variant in (text, fold(text)):
            if variant.lower() not in seen:
                seen.add(variant.lower())
                out.append(variant)
    if fold(name) not in seen:
        out.append(fold(name))
    return out


def _bfo_table(bfo: Graph) -> dict[str, tuple[str, str]]:
    """IRI da entidade -> (identificador curto da categoria, IRI da categoria BFO/IAO)."""
    table = {}
    for s, cat in bfo.subject_objects(BFO_CATEGORY):
        notation = bfo.value(cat, SKOS.notation)
        if notation is not None:
            table[str(s)] = (str(notation), str(cat))
    return table


def build_records(ontology: Path = MET_TTL, structure: Path = STRUCTURE_TTL, bfo: Path = BFO_TTL) -> dict[str, list[dict[str, Any]]]:
    g = Graph().parse(ontology)
    bfo_g = Graph().parse(bfo)
    bfo_of = _bfo_table(bfo_g)
    idx = OntologyIndex.load(ontology=ontology, structure=structure)
    version_info = str(g.value(None, OWL.versionInfo) or "")
    fingerprint = idx.fingerprint

    terms: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    def add_term(s: URIRef, kind: str, definition: str, scope: str = "") -> dict[str, Any] | None:
        labels = _label(g, s)
        if not labels:
            return None
        iri = str(s)
        cat = bfo_of.get(iri)
        tid, ev_id = term_id(iri), "ev." + iri.rsplit("#", 1)[-1]
        name = labels[0]
        term = {"id": tid, "name": name, "type": kind, "definition": definition, "scope": scope,
                "aliases": _aliases(name, labels[1:], _label(g, s, SKOS.altLabel), _label(g, s, SKOS.altLabel, "en")),
                "iri": iri, "bfo_category": cat[0] if cat else None, "bfo_iri": cat[1] if cat else None,
                "evidence": [ev_id]}
        terms.append(term)
        evidence.append({"id": ev_id, "source": SOURCE, "query": evidence_iri(ev_id), "validation_method": METHOD, "timestamp": "",
                         "result": f"{_short(iri)} declarado na ontologia {version_info} (impressão {fingerprint})"
                                   + (f"; categoria {cat[0]}" if cat else "")})
        return term

    for s in sorted(set(g.subjects(RDF.type, OWL.Class)), key=str):
        if isinstance(s, URIRef) and str(s).startswith(MET):
            comment = next(iter(_label(g, s, RDFS.comment)), "")
            add_term(s, "class", comment or (_label(g, s) or [""])[0])

    for iri, info in idx.properties.items():
        s = URIRef(iri)
        symbol = idx.unit_symbols.get(info.unit or "", "")
        label = (_label(g, s) or [""])[0]
        definition = f"Grandeza observável: {label}." + (f" Unidade canônica: {symbol}." if symbol else " Sem unidade.")
        kind_label = (_label(g, URIRef(info.kind)) or [""])[0] if info.kind else ""
        t = add_term(s, "observable_property", definition, kind_label)
        if t is None:
            continue
        tid, ev = t["id"], t["evidence"]
        keywords = [t["name"], *t["aliases"]]

        def constraint(kind: str, description: str, severity: str = "warn") -> None:
            constraints.append({"id": f"con.{tid[5:]}.{kind}", "target": tid, "constraint_type": kind,
                                "trigger_keywords": keywords, "severity": severity, "scope": "", "confidence": "high",
                                "description": description, "evidence": ev})

        note = next(iter(_label(g, s, URIRef(MET + "aggregationNote"))), "")
        if note:
            constraint("aggregation_note", note)
        if info.aggregations:
            constraint("allowed_aggregations", f"Agregações permitidas para {label}: {', '.join(sorted(info.aggregations))}.")
        if info.unit:
            constraint("unit", f"Unidade canônica de {label}: {symbol or _short(info.unit)} ({_short(info.unit)}).", "info")
        if info.containment:
            constraint("period_containment", f"{label}: só entram intervalos INTEIROS dentro do período pedido "
                       "(início >= começo do período e fim <= fim exclusivo).")

    for p in sorted(set(g.subjects(RDF.type, OWL.ObjectProperty)) | set(g.subjects(RDF.type, OWL.DatatypeProperty)), key=str):
        if isinstance(p, URIRef) and str(p).startswith(MET):
            add_term(p, "property", next(iter(_label(g, p, RDFS.comment)), "") or (_label(g, p) or [""])[0])

    known = {t["id"] for t in terms}
    for p_iri in sorted(idx.domain.keys() | idx.range_.keys()):
        tid = term_id(p_iri)
        if tid not in known:
            continue
        for rel, target in (("has_domain", idx.domain.get(p_iri)), ("has_range", idx.range_.get(p_iri))):
            if target and term_id(target) in known:
                relations.append({"id": f"rel.{tid[5:]}.{rel}.{term_id(target)[5:]}", "source": tid, "relation_type": rel,
                                  "target": term_id(target), "connection_condition": "", "description": "", "evidence": []})
    for iri, info in idx.properties.items():
        if info.kind and term_id(iri) in known and term_id(info.kind) in known:
            relations.append({"id": f"rel.{term_id(iri)[5:]}.observed_as.{term_id(info.kind)[5:]}", "source": term_id(iri),
                              "relation_type": "observed_as", "target": term_id(info.kind), "connection_condition": "",
                              "description": "Classe de observação que registra esta grandeza.", "evidence": []})

    return {"terms": terms, "mappings": [], "relations": relations, "constraints": constraints, "evidence": evidence}


def evidence_iri(ev_id: str) -> str:
    """IRI da entidade PROV-O da Evidência. O esquema de Evidência do EvoOntology não tem campo para ela; vai em `query` (que numa
    evidência derivada da ontologia estaria vazio) e o grafo PROV correspondente sai de `evidence_prov()`."""
    return EVIDENCE_NS + ev_id


def evidence_prov(records: dict[str, Any] | None = None) -> Graph:
    """Evidências da camada como PROV-O (documento da arquitetura, §7.4 regra 3: "Evidência ligada a PROV-O"). Cada Evidência é uma
    prov:Entity gerada pela atividade de construção da v0, que USOU os arquivos da ontologia (com a impressão de cada um) e foi
    associada ao construtor. Resolvível a partir do Termo: Term.evidence -> id -> `evidence_iri(id)` -> este grafo."""
    import hashlib
    from rdflib.namespace import PROV, XSD

    records = records or build_records()
    g = Graph()
    g.bind("prov", PROV)
    activity, agent = URIRef(EVIDENCE_NS + "activity/build-v0"), URIRef(EVIDENCE_NS + "agent/semantics.build")
    g.add((activity, RDF.type, PROV.Activity))
    g.add((agent, RDF.type, PROV.SoftwareAgent))
    g.add((activity, PROV.wasAssociatedWith, agent))
    for path in (MET_TTL, STRUCTURE_TTL, BFO_TTL):
        if path.is_file():
            src = URIRef(EVIDENCE_NS + "source/" + path.name)
            g.add((src, RDF.type, PROV.Entity))
            g.add((src, RDFS.label, Literal(f"ontology/{path.name}")))
            g.add((src, URIRef(MET + "sha256"), Literal(hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(), datatype=XSD.string)))
            g.add((activity, PROV.used, src))
    for ev in records["evidence"]:
        e = URIRef(evidence_iri(ev["id"]))
        g.add((e, RDF.type, PROV.Entity))
        g.add((e, RDFS.comment, Literal(ev["result"])))
        g.add((e, PROV.wasGeneratedBy, activity))
        g.add((e, PROV.wasAttributedTo, agent))
        g.add((e, PROV.wasDerivedFrom, URIRef(EVIDENCE_NS + "source/" + Path(ev["source"]).name)))
    return g


def build_v0(workspace: Path, version: str = "ontology_v0") -> dict[str, Any]:
    """Grava a v0 e a publica. Recusa sobrescrever uma camada ativa (a evolução é que a faz avançar)."""
    from evoontology.ontology.store import SemanticStore
    from evoontology.runtime import ops

    if (workspace / "active.json").exists() or (workspace / "versions" / version).exists():
        raise ValueError(f"{version} já existe em {workspace}: versões publicadas não se sobrescrevem (a evolução gera a seguinte)")
    records = build_records()
    SemanticStore.save_version(workspace, version, records)
    ops.publish_ontology_build({"workspace": str(workspace), "version": version, "open_browser": False})
    return {name: len(items) for name, items in records.items()}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Gera e publica a v0 da camada semântica a partir da ontologia")
    ap.add_argument("--workspace", type=Path, default=ROOT / ".evoontology")
    print(build_v0(ap.parse_args().workspace))
