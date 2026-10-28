"""Concordância entre duas leituras independentes: o detector GENÉRICO de dúvida de interpretação.

Duas leituras (enquadramentos diferentes) são comparadas na forma canônica (`schema.canonical_form`). Discordar prova que a pergunta admite
mais de uma leitura plausível — sem nenhuma regra sobre a frase. Concordar não prova acerto (erros podem ser correlacionados): por isso o
usuário sempre vê a paráfrase do que vai ser consultado e pode corrigir.
"""
from __future__ import annotations

from typing import Any

FIELD_NAMES = {"measure": "grandeza", "stations": "estação", "range": "período", "hours": "horas do dia", "weekdays": "dias da semana",
               "instant": "horário", "aggregation": "cálculo", "count_of": "o que se conta", "conditions": "condição", "daily": "condição do dia",
               "group_by": "agrupamento", "attributes": "atributos", "order": "ordenação", "parts": "número de períodos"}


def diff(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> list[str]:
    """Campos em que as duas leituras discordam (vazio = concordam)."""
    if len(a) != len(b):
        return ["parts"]
    out: list[str] = []
    for x, y in zip(a, b):
        out += [k for k in x if x[k] != y.get(k) and k not in out]
    return out


def describe_diff(fields: list[str]) -> str:
    return ", ".join(FIELD_NAMES.get(f, f) for f in fields)
