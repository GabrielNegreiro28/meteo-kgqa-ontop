"""Configuração ÚNICA do MVP, lida do ambiente. Nenhum caminho, endpoint ou teto de gasto fica espalhado pelo código.

Variáveis (todas opcionais):
  METQA_ENV            arquivo com OPENAI_API_KEY e KGQA_MODEL/KGQA_BUDGET_USD (padrão: ../METEOROLOGIA/kgqa.env, fora do repositório)
  KGQA_ONTOP_ENDPOINT  endpoint SPARQL do Ontop (padrão: http://127.0.0.1:8080/sparql)
  METQA_WORKSPACE      workspace do EvoOntology (padrão: .evoontology)
  METQA_LEXICON        "evo" (camada EvoOntology publicada) | "ontology" (só rótulos formais; ablação)
  METQA_LEXICON_VERSION versão da camada (padrão: a ativa)
  METQA_LEDGER         registro de gasto (padrão: eval/reports/spend_ledger.jsonl)
  METQA_TRAJECTORIES   "1" grava a trajetória de cada pergunta no workspace (sinal para a evolução)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Settings:
    env_file: Path = ROOT.parent / "METEOROLOGIA" / "kgqa.env"
    endpoint: str = "http://127.0.0.1:8080/sparql"
    workspace: Path = ROOT / ".evoontology"
    lexicon: str = "evo"
    lexicon_version: str | None = None
    ledger: Path = ROOT / "eval" / "reports" / "spend_ledger.jsonl"
    record_trajectories: bool = False
    timeout_s: float = 60.0
    max_rows: int = 1000
    max_repairs: int = 1
    budget_usd: float = 0.10                       # teto desta sessão; o teto acumulado é o do ledger
    max_question_chars: int = field(default=500)

    @classmethod
    def from_env(cls, **override) -> "Settings":
        env = os.environ
        base = dict(
            env_file=Path(env["METQA_ENV"]) if env.get("METQA_ENV") else cls.env_file,
            endpoint=env.get("KGQA_ONTOP_ENDPOINT", cls.endpoint),
            workspace=Path(env["METQA_WORKSPACE"]) if env.get("METQA_WORKSPACE") else cls.workspace,
            lexicon=env.get("METQA_LEXICON", cls.lexicon),
            lexicon_version=env.get("METQA_LEXICON_VERSION") or None,
            ledger=Path(env["METQA_LEDGER"]) if env.get("METQA_LEDGER") else cls.ledger,
            record_trajectories=env.get("METQA_TRAJECTORIES") == "1",
        )
        return cls(**{**base, **{k: v for k, v in override.items() if v is not None}})
