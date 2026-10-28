"""Tipos do domínio: os contratos entre os estágios. Puros (sem I/O); o contrato externo é o de `kgqa/contract.py` (0.2.1).

A `CanonicalQuery` é a "consulta canônica" do documento da arquitetura (§8): o que foi perguntado, em IRIs da ontologia, sem depender de
onde os dados estão. Responde à questão aberta do §16 com uma representação intermediária leve, compilada para SPARQL por código.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from kgqa.contract import Diagnostic, Status

INTENTS = ("value", "count", "series", "ranking", "extreme_with_attribute", "instant", "comparison")
COUNT_OF = ("readings", "hours", "days", "reports")


def hour_ranges(hours) -> str:
    """{18..23, 0..5} -> "das 18h às 6h"; {0..5} -> "das 0h às 6h"; horas soltas -> "3h, 9h". Fim exclusivo, dito assim ao usuário."""
    hs = sorted(set(hours))
    if not hs:
        return ""
    runs, cur = [], [hs[0]]
    for h in hs[1:]:
        if h == cur[-1] + 1:
            cur.append(h)
        else:
            runs.append(cur)
            cur = [h]
    runs.append(cur)
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == 23:          # atravessa a meia-noite: junta o fim com o começo
        runs = [runs[-1] + runs[0]] + runs[1:-1]
    return ", ".join(f"das {r[0]}h às {(r[-1] + 1) % 24}h (antes das {(r[-1] + 1) % 24}h)" if len(r) > 1 else f"{r[0]}h" for r in runs)


@dataclass(frozen=True)
class TimeScope:
    """Recorte de tempo, sempre em hora local UTC−3 (D-85). Valores JÁ NORMALIZADOS (pelo LLM, conferidos por código e pelo usuário)."""
    start: date | None = None                 # janela [start, end], fim inclusivo; None = todo o histórico
    end: date | None = None
    hours: tuple[int, ...] | None = None      # CONJUNTO de horas locais (0–23): "das 18h às 6h" = 18..23 e 0..5, sem caso especial
    weekdays: tuple[int, ...] | None = None   # 0 = segunda ... 6 = domingo
    instant: datetime | None = None           # "às 12h" (com fuso)

    def describe(self) -> str:
        if self.instant is not None:
            return f"em {self.instant:%d/%m/%Y} às {self.instant:%H:%M}"
        parts = ["todo o histórico disponível" if self.start is None else
                 f"em {self.start:%d/%m/%Y}" if self.start == self.end else f"de {self.start:%d/%m/%Y} a {self.end:%d/%m/%Y}"]
        if self.hours:
            parts.append("só nas horas " + hour_ranges(self.hours))
        if self.weekdays:
            names = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
            parts.append("só " + ("fins de semana" if set(self.weekdays) == {5, 6} else ", ".join(names[d] for d in self.weekdays)))
        return ", ".join(parts)


@dataclass
class CanonicalQuery:
    intent: str                                            # um de INTENTS
    measure: str                                           # IRI da grandeza (sosa:ObservableProperty)
    stations: list[dict[str, str]] = field(default_factory=list)      # [{"iri", "text"}]
    scope: TimeScope = field(default_factory=TimeScope)
    aggregation: str | None = None                         # avg | min | max | sum | count
    count_of: str | None = None                            # um de COUNT_OF (só com aggregation "count")
    conditions: list[dict[str, Any]] = field(default_factory=list)    # [{"op", "value", "unit"?}] — o compilador converte para a unidade canônica
    daily: dict[str, Any] | None = None                    # {"agg", "op", "value", "unit"?}: conta DIAS que cumprem a condição
    group_by: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)
    order: dict[str, Any] | None = None
    spans: dict[str, str] = field(default_factory=dict)    # campo -> trecho literal da pergunta que o justifica
    assumptions: list[str] = field(default_factory=list)   # o que foi decidido por regra e deve ser dito ao usuário


@dataclass
class SubQuery:
    label: str                                             # como a parte aparece na resposta ("janeiro de 2016")
    query: CanonicalQuery


@dataclass
class Plan:
    parts: list[SubQuery]
    combine: str = "single"                                # "single" | "compare"


@dataclass
class Executed:
    part: SubQuery
    sparql: str
    results: dict[str, Any]
    truncated: bool = False
    status: Status = Status.ANSWERED
    engine_sql: str | None = None


@dataclass
class Stop:
    """Um estágio encerra a pergunta: o status e o motivo, sempre ditos (falhar fechado, §4 'dizer não sei')."""
    status: Status
    diagnostics: list[Diagnostic]

    @classmethod
    def of(cls, status: Status, code: str, message: str, severity: str = "info", **details) -> "Stop":
        return cls(status, [Diagnostic(code, severity, message, details or None)])
