"""Evolução da camada EvoOntology, FORA do caminho da pergunta (processo em lote; documento da arquitetura, §7.3 e §13).

O MVP só grava a trajetória de cada pergunta (sinais do §13: reparos, achados, abstenções, palavras sem cobertura do léxico). O ciclo em si
é o já existente e testado:
  minerar (`semantics/evolve.py::mine`) -> Candidate -> porta BFO/SHACL/HermiT (`semantics/gate.py`) -> avaliação pareada -> publicar/rejeitar,
  com mudanças da camada formal viradas PROPOSTA para revisão humana (`proposals/pending.json`).
Rodar: `python -m semantics.run_evolution --parent <versão ativa> --require-reasoner --sample-graph` (numa cópia; `--in-place` publica).
Como o léxico do MVP é a camada publicada, um sinônimo aceito muda o cardápio do intérprete a partir da próxima pergunta.
"""
from __future__ import annotations

from pathlib import Path


def record(workspace: str | Path, result, split: str = "use") -> str | None:
    """Grava a trajetória; registro apenas: uma falha aqui nunca afeta a resposta."""
    try:
        from semantics.trajectories import record_trajectory
        return record_trajectory(workspace, result, split=split)
    except Exception:                                   # noqa: BLE001
        return None
