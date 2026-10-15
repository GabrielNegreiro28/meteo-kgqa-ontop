"""Verificações pós-execução independentes do gerador de consultas (primeira peça do verificador)."""
from __future__ import annotations

from typing import Any

from .contract import Status

COUNT_VARS = ("n", "count", "cnt")


def result_status(results: dict[str, Any]) -> tuple[Status, list[str]]:
    """Classifica um resultado SELECT bem-sucedido em ANSWERED ou NO_RESULTS.

    Pega o caso traiçoeiro do SPARQL 1.1: agregação sem GROUP BY sobre conjunto vazio devolve
    UMA linha (COUNT=0, SUM=0, AVG=0). Se todas as variáveis de contagem forem 0, não há dados.
    Por isso as consultas agregadas devem sempre projetar uma contagem (?n).
    """
    notes: list[str] = []
    bindings = results.get("results", {}).get("bindings", [])
    if not bindings:
        return Status.NO_RESULTS, ["zero linhas"]
    count_vars = [v for v in results["head"].get("vars", []) if v.lower() in COUNT_VARS]
    if count_vars and all(
        all(b.get(v, {}).get("value", "0") == "0" for v in count_vars) for b in bindings
    ):
        return Status.NO_RESULTS, ["agregação sobre conjunto vazio (contagem = 0)"]
    return Status.ANSWERED, notes
