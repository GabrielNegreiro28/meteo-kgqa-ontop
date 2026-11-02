"""Trajetórias de SEMENTE a partir do gabarito, para o ciclo de evolução rodar sem gastar com LLM.

A evolução precisa de trajetórias (§7.3 "Use"). Nenhuma foi gravada ainda com a camada ligada, porque isso exige rodar o LLM (dinheiro).
Há, porém, perguntas cuja interpretação certa é CONHECIDA (a consulta de referência diz quais grandezas ela usa). Para cada uma, o
`SemanticGrounder` diz que palavras da pergunta nenhum Termo cobriu, e o gabarito diz a que grandeza a pergunta levou. É exatamente o par
(palavra sem cobertura, grandeza) que o minerador usa para propor um sinônimo.

Honestidade sobre a origem: estas NÃO são trajetórias de um agente. Têm `evaluation.origin = "gold_seed"` e o gabarito faz o papel da
avaliação. Servem para exercitar e medir o ciclo; trajetórias de uso real (com o LLM e usuários) entram pelo mesmo caminho e valem mais.
Só as perguntas de CONSTRUÇÃO entram (as de validação continuam invisíveis ao minerador).
"""
from __future__ import annotations

import re
from pathlib import Path

from evoontology.trajectory.trajectory import TrajectoryStore

from metqa.knowledge.index import _short

from .facade import GroundedLayer
from .ground import SemanticGrounder
from .resolution import CONSTRUCTION_FILES, Case, load_cases


def seed_from_gold(workspace: str | Path, version: str, cases: list[Case] | None = None) -> int:
    """Grava uma trajetória por caso de construção. Devolve quantas foram gravadas (idempotente: o task_id é derivado do caso)."""
    cases = cases if cases is not None else load_cases(CONSTRUCTION_FILES)
    grounder = SemanticGrounder(GroundedLayer.open(workspace, version))
    store = TrajectoryStore(workspace)
    for c in cases:
        g = grounder.ground(c.question)
        store.append({
            "task_id": "seed_" + re.sub(r"[^A-Za-z0-9_.-]", "_", c.id),
            "question": c.question, "split": "construction", "ontology_version": version,
            "pipeline_status": "answered", "task_status": "completed", "final_answer": "",
            "native_tool_calls": [{"tool": "interpret", "input": {"question": c.question},
                                   "result": {"interpretation": {"properties": sorted(_short(i) for i in c.gold)}, "findings": []}}],
            "semantic_calls": [],
            "signals": {"semantics": {"uncovered": g.uncovered, "unbound": sorted(set(g.unbound))}, "user_corrections": 0, "verifier_findings": []},
            "evaluation": {"origin": "gold_seed", "result_match": True, "status_ok": True},
        })
    return len(cases)
