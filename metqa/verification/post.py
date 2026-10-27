"""Verificação DEPOIS da consulta (documento da arquitetura, §12): o resultado faz sentido para ser dito?

- vazio de verdade x agregado sobre conjunto vazio (`kgqa/verify.py::result_status`, que olha o ?n);
- ressalvas determinísticas: amostra pequena, grupos pequenos, visibilidade censurada em 20 km, cuidados da ontologia
  (`pipeline/caveats.py::answer_caveats`);
- resultado truncado é dito.
"""
from __future__ import annotations

from kgqa.contract import Status
from pipeline.caveats import answer_caveats

from ..domain import Executed
from ..knowledge import DomainCatalog
from ..planning import to_interp


def verify_post(done: list[Executed], catalog: DomainCatalog) -> tuple[Status, list[str]]:
    status = Status.NO_RESULTS if all(e.status == Status.NO_RESULTS for e in done) else Status.ANSWERED
    caveats: list[str] = []
    for e in done:
        if e.status == Status.ANSWERED:
            caveats += [c for c in answer_caveats(to_interp(e.part.query), e.results, catalog.index) if c not in caveats]
        if e.truncated:
            caveats.append("resultado parcial: o limite de linhas foi atingido")
    return status, caveats
