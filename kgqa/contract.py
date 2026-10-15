"""Contrato de entrada/saída do módulo KGQA (versão 0.1, PROPOSTA para negociar com a equipe).

Os resultados seguem o formato W3C "SPARQL 1.1 Query Results JSON" ({head:{vars}, results:{bindings}}),
para preservar tipo (datatype), idioma e IRIs sem conversões com perda.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

CONTRACT_VERSION = "0.1.0"


class Status(str, Enum):
    ANSWERED = "answered"                    # consulta válida executada e com linhas
    NO_RESULTS = "no_results"                # consulta válida executada, zero linhas (é uma resposta!)
    NEEDS_CLARIFICATION = "needs_clarification"  # pergunta ambígua; nada foi executado
    UNSUPPORTED = "unsupported"              # conceito/entidade fora da ontologia ou do grafo
    EXECUTION_ERROR = "execution_error"      # falha de sintaxe, timeout, backend indisponível
    REJECTED = "rejected"                    # consulta violou política (UPDATE, SERVICE, etc.)


@dataclass
class QueryRequest:
    question: str
    language: str = "pt-BR"
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # Contexto opcional vindo das etapas iniciais (entidades já ligadas, histórico). Pode vir vazio.
    context: dict[str, Any] = field(default_factory=dict)
    timeout_s: float = 10.0
    max_rows: int = 1000


@dataclass
class Diagnostic:
    code: str            # ex.: "AMBIGUOUS_SUPERLATIVE", "UNKNOWN_PROPERTY", "TIMEOUT", "TRUNCATED"
    severity: str        # "info" | "warning" | "error"
    message: str         # legível por humanos, em português
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Interpretation:
    """Representação interna (decisão de implementação, não interface externa)."""
    entities: list[dict[str, Any]] = field(default_factory=list)    # [{"text","iri","type","score"}]
    properties: list[str] = field(default_factory=list)             # IRIs de sosa:ObservableProperty
    filters: list[dict[str, Any]] = field(default_factory=list)     # [{"var","op","value","unit"}]
    period: dict[str, str] | None = None                            # {"start","end","tz","inclusive_end"}
    aggregation: str | None = None                                  # avg|min|max|sum|count|None
    expected_answer: str | None = None                              # "list"|"scalar"|"per_group"|"ranking"
    alternatives: list[dict[str, Any]] = field(default_factory=list)  # leituras possíveis se ambígua


@dataclass
class Provenance:
    source_id: str                       # identificador do grafo/endpoint
    dataset_iris: list[str] = field(default_factory=list)
    synthetic: bool | None = None
    ontology_version: str | None = None
    record_iris: list[str] = field(default_factory=list)  # observações que sustentam a resposta, quando houver


@dataclass
class QueryResponse:
    request_id: str
    status: Status
    question: str
    sparql: str | None = None
    results: dict[str, Any] | None = None   # SPARQL 1.1 JSON Results
    units: dict[str, str] = field(default_factory=dict)   # var -> IRI de unidade QUDT
    truncated: bool = False
    interpretation: Interpretation | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    provenance: Provenance | None = None
    answer_text: str | None = None          # opcional, só para demonstração
    timings_ms: dict[str, float] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d
