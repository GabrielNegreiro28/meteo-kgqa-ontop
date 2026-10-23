"""Gera as DUAS visões da ontologia a partir de UMA fonte (documento da arquitetura, §6.6).

Fonte única = os módulos em ontology/ (met.ttl, met-structure.ttl, met-bfo.ttl) mais os imports fixados em ontology/imports/
(BFO 2020 sem alteração e um módulo da IAO), com versões e SHA-256 em imports/SOURCES.md.

  visão completa (OWL 2 DL): a união de tudo, para o raciocinador (HermiT) conferir consistência e colocação das classes.
                             Única transformação: o domínio alternativo da camada estrutural (met:alsoDomain) vira domínio por UNIÃO
                             (owl:unionOf), que é o que ele significa; sem isso o RDFS leria os dois domínios como interseção
                             (observação E boletim ao mesmo tempo, que a BFO declara disjuntos: Codex C08).
  visão QL (OWL 2 QL):       só os axiomas que o OWL 2 QL expressa (hierarquias, domínios e imagens, inversas, disjunções).
                             O que não cabe (restrições allValuesFrom, domínio por união, datatypes fora do perfil) NÃO é perdido:
                             regras de dados ficam no SHACL (ontology/shapes.ttl) e o resto no verificador da pipeline.

Uso:  python -m ontology.build_views [--out ontology/generated]      (escreve met-ql.ttl e met-ontop.ttl; com --dl também met-dl.ttl)
met-ql.ttl (perfil OWL 2 QL completo) e met-ontop.ttl (o que o Ontop carrega: a QL sem domínios e imagens, ver build_ontop) são
versionados, e um teste confere que regerá-los dá os mesmos arquivos.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, XSD

ROOT = Path(__file__).resolve().parent
MODULES = [ROOT / "met.ttl", ROOT / "met-structure.ttl", ROOT / "met-bfo.ttl", ROOT / "met-external.ttl"]
IMPORTS = [ROOT / "imports" / "bfo-core.owl", ROOT / "imports" / "iao-module.owl"]
MET = "https://example.org/kgqa-met/ontology#"
ALSO_DOMAIN = URIRef(MET + "alsoDomain")

# Datatypes do perfil OWL 2 QL (https://www.w3.org/TR/owl2-profiles/#OWL_2_QL). xsd:date, xsd:boolean e xsd:double ficam de fora.
QL_DATATYPES = {RDF.PlainLiteral, RDF.XMLLiteral, RDFS.Literal, XSD.decimal, XSD.integer, XSD.nonNegativeInteger, XSD.string,
                XSD.normalizedString, XSD.token, XSD.Name, XSD.NCName, XSD.NMTOKEN, XSD.hexBinary, XSD.base64Binary, XSD.anyURI,
                XSD.dateTime, XSD.dateTimeStamp}
DECLARATIONS = {OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, OWL.NamedIndividual}
# Características de propriedade que o QL admite (funcional, funcional inversa e transitiva NÃO).
QL_CHARACTERISTICS = {OWL.SymmetricProperty, OWL.AsymmetricProperty, OWL.ReflexiveProperty, OWL.IrreflexiveProperty}
ANNOTATIONS = {RDFS.label}


def load_source() -> Graph:
    g = Graph()
    for p in [*MODULES, *IMPORTS]:
        g.parse(p)
    return g


def build_dl(source: Graph | None = None) -> Graph:
    """Visão completa: a fonte com o domínio alternativo expresso como união."""
    g = Graph()
    src = source if source is not None else load_source()
    for t in src:
        g.add(t)
    for prop, other in sorted(set(src.subject_objects(ALSO_DOMAIN)), key=str):
        primary = [d for d in src.objects(prop, RDFS.domain) if isinstance(d, URIRef)]
        members = sorted({*primary, other}, key=str)
        for d in primary:
            g.remove((prop, RDFS.domain, d))
        union, lst = BNode(), BNode()
        Collection(g, lst, members)
        g.add((union, RDF.type, OWL.Class))
        g.add((union, OWL.unionOf, lst))
        g.add((prop, RDFS.domain, union))
    return g


def _is_iri(x) -> bool:
    return isinstance(x, URIRef)


def build_ql(full: Graph | None = None) -> Graph:
    """Visão QL: só axiomas atômicos que o OWL 2 QL expressa. Sem nós em branco, logo a serialização é determinística."""
    src = full if full is not None else build_dl()
    ql = Graph()
    ql.bind("met", MET)
    for s, p, o in src:
        if not _is_iri(s):
            continue
        if p == RDF.type and o in DECLARATIONS | QL_CHARACTERISTICS and _is_iri(o):
            ql.add((s, p, o))
        elif p in (RDFS.subClassOf, OWL.disjointWith, RDFS.subPropertyOf, OWL.inverseOf, OWL.equivalentClass,
                   OWL.equivalentProperty, OWL.propertyDisjointWith) and _is_iri(o):
            ql.add((s, p, o))
        elif p == RDFS.domain and _is_iri(o):
            ql.add((s, p, o))
        elif p == RDFS.range and _is_iri(o) and (not str(o).startswith(str(XSD)) or o in QL_DATATYPES):
            ql.add((s, p, o))
        elif p in ANNOTATIONS and isinstance(o, Literal):
            ql.add((s, p, o))
    return ql


def build_ontop(ql: Graph | None = None) -> Graph:
    """Visão de EXECUÇÃO do Ontop: a visão QL sem rdfs:domain e rdfs:range.

    Medido no grafo real: com domínios e imagens, `?s a sosa:Sensor` (que vira união de sosa:hosts e de sosa:madeBySensor, ou seja, das
    105 mi de observações) estourava 60 s, e a suíte inteira ficou ~55% mais lenta. Esses axiomas só ADICIONAM tipos que o mapeamento já
    emite para todo sujeito, então não acrescentam respostas e custam reescrita. Hierarquias, disjunções e subpropriedades ficam
    (é delas que vem a consulta por categoria BFO). Domínios e imagens continuam na visão QL completa e na checagem do raciocinador."""
    out = Graph()
    out.bind("met", MET)
    for t in (ql if ql is not None else build_ql()):
        if t[1] not in (RDFS.domain, RDFS.range):
            out.add(t)
    return out


def serialize(g: Graph) -> str:
    """Turtle com triplas em ordem estável (o rdflib já ordena sujeitos e predicados; os objetos são ordenados aqui)."""
    ordered = Graph()
    for prefix, ns in sorted(g.namespaces()):
        ordered.bind(prefix, ns)
    for t in sorted(g, key=lambda t: tuple(str(x) for x in t)):
        ordered.add(t)
    return ordered.serialize(format="turtle")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "generated"))
    ap.add_argument("--dl", action="store_true", help="também escreve a visão completa (grande; não é versionada)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    full = build_dl()
    ql = build_ql(full)
    (out / "met-ql.ttl").write_text(serialize(ql), encoding="utf-8", newline="\n")
    (out / "met-ontop.ttl").write_text(serialize(build_ontop(ql)), encoding="utf-8", newline="\n")
    if args.dl:
        (out / "met-dl.ttl").write_text(full.serialize(format="turtle"), encoding="utf-8", newline="\n")
    print(f"met-ql.ttl: {len(build_ql(full))} triplas; fonte: {len(load_source())} triplas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
