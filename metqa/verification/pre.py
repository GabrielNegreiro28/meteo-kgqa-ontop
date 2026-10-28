"""Verificação ANTES de qualquer consulta (documento da arquitetura, §8 e §12): a consulta canônica contra a ontologia e contra o catálogo.

- forma e vocabulário: IRIs existem, agregação admitida pela ontologia, dimensões e atributos da grandeza, forma do resultado coerente
  (regras L2/L3 de `pipeline/validators.py`, sem as regras de fundamentação por regex, que a conciliação por trechos substitui);
- capacidades (o catálogo do roteador reduzido): a grandeza tem dados nesta fonte? o período está dentro da cobertura?
"""
from __future__ import annotations

from kgqa.contract import Status
from pipeline.validators import L3, Finding, _err, validate_interpretation

from ..domain import CanonicalQuery, Stop
from ..knowledge import DomainCatalog
from ..planning import to_interp


def _values(cq: CanonicalQuery, catalog: DomainCatalog) -> list[Finding]:
    """Checagens sobre VALORES já normalizados (análise dimensional, coerência do cálculo). Finitas: não crescem com as perguntas."""
    out: list[Finding] = []
    m = catalog.measure(cq.measure)
    for c in [*cq.conditions, *([cq.daily] if cq.daily else [])]:
        if m and catalog.to_canonical(c["value"], c.get("unit"), cq.measure) is None:
            out.append(_err(L3, "UNIT_DIMENSION_MISMATCH",
                            f"A condição {c['op']} {c['value']} {c.get('unit', '')} não se converte para a unidade de {m.label} "
                            f"({m.symbol or 'sem unidade'}): a unidade não é dessa grandeza, ou a grandeza escolhida não é a da pergunta"))
    if cq.count_of and cq.aggregation != "count":
        out.append(_err(L3, "COUNT_OF_WITHOUT_COUNT", "calc.count_of só vale com aggregation \"count\""))
    if cq.count_of == "days" and not cq.daily:
        out.append(_err(L3, "DAYS_NEED_DAILY", "Contar dias exige calc.daily com a estatística do dia e a condição"))
    return out


def verify_pre(cq: CanonicalQuery, catalog: DomainCatalog) -> tuple[list[Finding], Stop | None]:
    findings = validate_interpretation(to_interp(cq), catalog.index, None, (), True) or _values(cq, catalog)
    if findings:
        return findings, None
    m = catalog.measure(cq.measure)
    if m is None:
        return [], Stop.of(Status.UNSUPPORTED, "UNKNOWN_PROPERTY", f"A grandeza {cq.measure} não existe na ontologia.")
    if not m.has_data:
        return [], Stop.of(Status.UNSUPPORTED, "PROPERTY_WITHOUT_DATA",
                           f"A ontologia prevê '{m.label}', mas esta fonte não tem nenhuma observação dessa grandeza.")
    cov, s = catalog.coverage, cq.scope
    day = s.instant.date() if s.instant else None
    lo, hi = (day, day) if day else (s.start, s.end)
    if cov and lo is not None and (hi < cov[0] or lo > cov[1]):
        return [], Stop.of(Status.NO_RESULTS, "OUT_OF_COVERAGE",
                           f"Não há registros nesse período: os dados cobrem de {cov[0]:%d/%m/%Y} a {cov[1]:%d/%m/%Y}.",
                           coverage=[cov[0].isoformat(), cov[1].isoformat()])
    return [], None
