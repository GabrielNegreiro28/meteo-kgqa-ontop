"""Procedência de cada resposta em PROV-O (documento da arquitetura, §7.4 regra 3, §10 e §12: "toda resposta cita a fonte, a consulta
executada, incluindo o SQL gerado pelo Ontop, e as versões usadas").

Uma resposta é uma `prov:Entity` gerada por uma `prov:Activity` que USOU a pergunta, o SPARQL e a fonte (o grafo), e foi
associada a um agente de software com as versões que a produziram (prompts, ontologia, camada semântica, modelo). O SQL que o motor
gerou é uma entidade derivada do SPARQL. Nada aqui entra no prompt; é só registro. Falha ao montar a procedência NUNCA derruba a
resposta (quem chama captura a exceção).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from rdflib import RDF, RDFS, Graph, Literal, Namespace, URIRef
from rdflib.namespace import PROV, XSD

from kgqa.contract import QueryResponse

RUN = Namespace("https://example.org/kgqa-met/run/")
VER = Namespace("https://example.org/kgqa-met/run/version#")


@lru_cache(maxsize=1)
def artifact_versions() -> dict[str, str]:
    """Impressão (SHA-256, 12 hex) dos artefatos que determinam o que uma resposta significa: mapeamento do Ontop, regras de limpeza, camada
    estrutural, alinhamento BFO e o código do pipeline/executor. Uma resposta sem isso não diz sobre QUAL grafo e QUAL código ela saiu."""
    root = Path(__file__).resolve().parent.parent

    def digest(*paths: Path) -> str | None:
        h, found = hashlib.sha256(), False
        for p in sorted(paths):
            if p.is_file():
                h.update(p.name.encode() + p.read_bytes().replace(b"\r\n", b"\n"))      # fim de linha não muda a impressão
                found = True
        return h.hexdigest()[:12] if found else None

    out = {"mapping": digest(root / "mapping" / "met.obda"), "cleaning": digest(root / "ingest" / "transform.py"),
           "structure": digest(root / "ontology" / "met-structure.ttl"), "bfo_alignment": digest(root / "ontology" / "met-bfo.ttl"),
           "code": digest(*(root / "pipeline").glob("*.py"), *(root / "kgqa").glob("*.py"))}
    return {k: v for k, v in out.items() if v}


def build_prov(resp: QueryResponse, started: datetime, ended: datetime | None = None) -> Graph:
    g = Graph()
    g.bind("prov", PROV)
    g.bind("run", RUN)
    g.bind("ver", VER)
    rid = resp.request_id
    answer, activity, question = RUN[f"{rid}/answer"], RUN[f"{rid}/activity"], RUN[f"{rid}/question"]
    agent = RUN["agent/kgqa-pipeline"]
    prov = resp.provenance
    ended = ended or datetime.now(timezone.utc)

    g.add((question, RDF.type, PROV.Entity))
    g.add((question, RDFS.label, Literal(resp.question or "")))
    g.add((answer, RDF.type, PROV.Entity))
    g.add((answer, VER.status, Literal(resp.status.value)))
    g.add((answer, PROV.wasGeneratedBy, activity))
    g.add((activity, RDF.type, PROV.Activity))
    g.add((activity, PROV.startedAtTime, Literal(started.isoformat(), datatype=XSD.dateTime)))
    g.add((activity, PROV.endedAtTime, Literal(ended.isoformat(), datatype=XSD.dateTime)))
    g.add((activity, PROV.used, question))
    g.add((activity, PROV.wasAssociatedWith, agent))
    g.add((answer, PROV.wasAttributedTo, agent))

    if prov is not None and prov.source_id:
        source = RUN[f"source/{prov.source_id}"]
        g.add((source, RDF.type, PROV.Entity))
        g.add((source, RDFS.label, Literal(prov.source_id)))
        g.add((activity, PROV.used, source))
        g.add((answer, PROV.wasDerivedFrom, source))

    if resp.sparql:                                   # a consulta que foi (ou seria) executada
        sparql = RUN[f"{rid}/sparql"]
        g.add((sparql, RDF.type, PROV.Entity))
        g.add((sparql, VER.text, Literal(resp.sparql)))
        g.add((sparql, PROV.wasDerivedFrom, question))
        g.add((activity, PROV.used, sparql))
        if prov is not None and prov.executed_sparql and prov.executed_sparql != resp.sparql:   # o que o motor recebeu de fato (com LIMIT)
            sent = RUN[f"{rid}/sparql-sent"]
            g.add((sent, RDF.type, PROV.Entity))
            g.add((sent, VER.text, Literal(prov.executed_sparql)))
            g.add((sent, PROV.wasDerivedFrom, sparql))
            g.add((activity, PROV.used, sent))
        if prov is not None and prov.generated_sql:   # o SQL que o motor gerou a partir do SPARQL
            sql = RUN[f"{rid}/sql"]
            g.add((sql, RDF.type, PROV.Entity))
            g.add((sql, VER.text, Literal(prov.generated_sql)))
            g.add((sql, PROV.wasDerivedFrom, RUN[f"{rid}/sparql-sent"] if (prov.executed_sparql and prov.executed_sparql != resp.sparql) else sparql))
            g.add((answer, PROV.wasDerivedFrom, sql))
            if prov.engine:
                g.add((sql, PROV.wasAttributedTo, RUN[f"agent/{prov.engine}"]))
                g.add((RUN[f"agent/{prov.engine}"], RDF.type, PROV.SoftwareAgent))

    g.add((agent, RDF.type, PROV.SoftwareAgent))
    if prov is not None and not prov.complete:
        g.add((answer, VER.provenanceComplete, Literal(False)))
    for key, value in ((prov.versions if prov is not None else {}) or {}).items():
        if value is not None:
            g.add((agent, VER[str(key)], Literal(str(value))))
    return g


def prov_turtle(resp: QueryResponse, started: datetime, ended: datetime | None = None) -> str:
    return build_prov(resp, started, ended).serialize(format="turtle")


def llm_model_of(llm: Any) -> str | None:
    """Nome do modelo, procurando nos envoltórios (ResilientLLM -> LedgerLLM -> cliente). None se o cliente não informa."""
    obj = llm
    for _ in range(4):
        model = getattr(obj, "model", None)
        if isinstance(model, str) and model:
            return model
        obj = getattr(obj, "client", None)
        if obj is None:
            break
    return None
