"""Paráfrase DETERMINÍSTICA da consulta canônica: o que o usuário lê é exatamente o que vai ser consultado (o que se vê é o que se executa).

Gerada da consulta já normalizada, não da pergunta: por isso mostra ao usuário a interpretação real do sistema, inclusive o que foi assumido.
"""
from __future__ import annotations

from ..domain import CanonicalQuery
from ..knowledge import DomainCatalog
from ..presentation.render import AGG, COUNTED, DIMS, OPS, UNIT_NS, _cond, _where, num


def paraphrase(cq: CanonicalQuery, catalog: DomainCatalog) -> str:
    m = catalog.measure(cq.measure)
    label = m.label if m else cq.measure.rsplit("#", 1)[-1]
    where, when = _where(cq), cq.scope.describe()
    cond = _cond(cq, catalog) if m else ""
    if cq.scope.instant is not None:
        return f"o valor de {label} {where} {when}"
    if cq.aggregation == "count" and cq.daily:
        d = cq.daily
        unit = catalog.symbol(UNIT_NS + d["unit"].split(":")[-1]) if d.get("unit") else (m.symbol if m else "")
        return (f"o número de dias {where}, {when}, em que a {AGG[d['agg']]} diária de {label} ficou {OPS[d['op']]} "
                f"{num(d['value'])} {unit}".rstrip())
    calc = f"o número de {COUNTED.get(cq.count_of or 'readings')}" if cq.aggregation == "count" else \
        f"a {AGG.get(cq.aggregation, cq.aggregation)}" if cq.aggregation else "os valores"
    text = f"{calc} de {label} {where}, {when}{cond}"
    if cq.group_by:
        text += ", por " + ", ".join(DIMS.get(g, g.rsplit("#", 1)[-1]) for g in cq.group_by)
    if cq.order:
        text += f" (só os {cq.order['limit']} {'maiores' if cq.order['direction'] == 'desc' else 'menores'})"
    if cq.attributes:
        text += ", mostrando " + ", ".join(a.rsplit("#", 1)[-1].split(":")[-1] for a in cq.attributes)
    return text


def paraphrase_parts(parts, catalog: DomainCatalog) -> str:
    texts = [paraphrase(cq, catalog) for _, cq in parts]
    return texts[0] if len(texts) == 1 else "comparar " + " com ".join(texts)
