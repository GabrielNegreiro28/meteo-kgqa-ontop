"""Verificação ANTES de qualquer consulta (documento da arquitetura, §8 e §12): a consulta canônica contra a ontologia e contra o catálogo.

- forma e vocabulário: IRIs existem, agregação admitida pela ontologia, dimensões e atributos da grandeza, forma do resultado coerente
  (regras L2/L3 de `pipeline/validators.py`, sem as regras de fundamentação por regex, que a conciliação por trechos substitui);
- capacidades (o catálogo do roteador reduzido): a grandeza tem dados nesta fonte? o período está dentro da cobertura?
"""
from __future__ import annotations

from kgqa.contract import Status
from pipeline.validators import Finding, validate_interpretation

from ..domain import CanonicalQuery, Stop
from ..knowledge import DomainCatalog
from ..planning import to_interp


def verify_pre(cq: CanonicalQuery, catalog: DomainCatalog) -> tuple[list[Finding], Stop | None]:
    findings = validate_interpretation(to_interp(cq), catalog.index, None, (), True)
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
