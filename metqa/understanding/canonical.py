"""Da proposta do LLM à consulta canônica: conciliação com a leitura determinística e verificação antes de qualquer consulta.

A conciliação é a de `pipeline/reconcile.py` (trechos existem e correspondem, número sem dono, unidade x grandeza, medida x contagem,
"horas com chuva" = > 0, o que a contagem conta, alcance mínimo). Aqui ela é aplicada a cada janela de uma comparação e o resultado vira
uma `CanonicalQuery` com intenção explícita.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from kgqa.contract import Status
from pipeline.reconcile import REPAIRABLE, reconcile
from pipeline.spans import Reading
from pipeline.validators import Finding, PipelineInterpretation
from pipeline.vocab import expand

from ..domain import CanonicalQuery, Stop, TimeScope
from ..knowledge import DomainCatalog
from .reader import split_windows


@dataclass
class Understood:
    parts: list[tuple[str, CanonicalQuery]] = field(default_factory=list)   # (rótulo, consulta); 2 partes = comparação
    findings: list[Finding] = field(default_factory=list)                   # achados que voltam ao LLM numa rodada de reparo
    stop: Stop | None = None
    interpretations: list[PipelineInterpretation] = field(default_factory=list)

    @property
    def repairable(self) -> bool:
        return bool(self.findings) and all(f.diag.code in REPAIRABLE for f in self.findings)


def intent_of(i: PipelineInterpretation, compare: bool) -> str:
    if compare:
        return "comparison"
    if i.instant:
        return "instant"
    if i.attributes:
        return "extreme_with_attribute"
    if i.order:
        return "ranking"
    if i.group_by:
        return "series"
    return "count" if i.aggregation == "count" else "value"


def _scope(i: PipelineInterpretation) -> TimeScope:
    start = date.fromisoformat(i.period["start"]) if i.period else None
    end = date.fromisoformat(i.period["end"]) if i.period else None
    instant = datetime.fromisoformat(i.instant) if i.instant else None
    return TimeScope(start, end, tuple(i.hours) if i.hours else None, tuple(i.weekdays) if i.weekdays else None, instant)


def to_canonical(i: PipelineInterpretation, raw: dict[str, Any], notes: list[str], compare: bool) -> CanonicalQuery:
    spans = {k: v["span"] for k, v in (("aggregation", raw.get("aggregation")), ("order", raw.get("order")), ("daily", raw.get("daily")))
             if isinstance(v, dict) and isinstance(v.get("span"), str)}
    spans.update({f"measure:{p.get('iri')}": p.get("span") for p in raw.get("properties") or [] if isinstance(p, dict)})
    assumptions = list(notes)
    if not i.entities and "station" not in i.group_by:
        assumptions.append("a pergunta não citou estação: usei todas as estações")
    if not i.period and not i.instant:
        assumptions.append("a pergunta não limitou o tempo: usei todo o histórico disponível")
    return CanonicalQuery(intent=intent_of(i, compare), measure=expand(i.properties[0]),
                          stations=[{"iri": expand(e["iri"]), "text": e.get("text", "")} for e in i.entities], scope=_scope(i),
                          aggregation=i.aggregation, count_of=i.count_of, conditions=list(i.filters), daily=i.daily,
                          group_by=list(i.group_by), attributes=list(i.attributes), order=i.order, spans=spans, assumptions=assumptions)


def understand(question: str, raw: dict[str, Any], reading: Reading, catalog: DomainCatalog) -> Understood:
    out = Understood()
    if raw.get("status") == "needs_clarification":
        out.stop = Stop.of(Status.NEEDS_CLARIFICATION, "AMBIGUOUS_QUESTION", str(raw.get("reason") or "A pergunta é ambígua."),
                           alternatives=raw.get("alternatives") or [])
        return out
    if raw.get("status") == "unsupported":
        out.stop = Stop.of(Status.UNSUPPORTED, "UNSUPPORTED_BY_MODEL", str(raw.get("reason") or "Fora do que os dados cobrem."))
        return out
    windows = split_windows(reading)
    if len(windows) > 2:
        out.stop = Stop.of(Status.UNSUPPORTED, "TOO_MANY_PERIODS", "Compare no máximo dois períodos por pergunta.")
        return out
    for label, r in windows:
        rec = reconcile(raw, question, catalog.index, r)
        out.interpretations.append(rec.interp)
        if rec.findings:
            out.findings = rec.findings
            return out
        if rec.unsupported:
            out.stop = Stop.of(Status.UNSUPPORTED, "UNSUPPORTED_SHAPE", rec.unsupported)
            return out
        if rec.clarify:
            out.stop = Stop.of(Status.NEEDS_CLARIFICATION, "AMBIGUOUS_QUESTION", rec.clarify)
            return out
        if len(rec.interp.properties) != 1:
            out.stop = Stop.of(Status.UNSUPPORTED, "ONE_MEASURE", "Pergunte uma grandeza por vez (ex.: a temperatura OU a umidade).")
            return out
        out.parts.append((label, to_canonical(rec.interp, raw, rec.notes, compare=len(windows) == 2)))
    return out
