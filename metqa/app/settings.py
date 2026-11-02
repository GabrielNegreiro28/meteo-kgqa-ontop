"""Configuração ÚNICA do MVP, lida do ambiente. Nenhum caminho, endpoint ou teto de gasto fica espalhado pelo código.

Variáveis (todas opcionais):
  METQA_ENV            arquivo com OPENAI_API_KEY e KGQA_MODEL/KGQA_BUDGET_USD (padrão: ../METEOROLOGIA/kgqa.env, fora do repositório)
  KGQA_ONTOP_ENDPOINT  endpoint SPARQL do Ontop (padrão: http://127.0.0.1:8080/sparql)
  METQA_WORKSPACE      workspace do EvoOntology (padrão: .evoontology)
  METQA_LEXICON        "evo" (camada EvoOntology publicada) | "ontology" (só rótulos formais; ablação)
  METQA_LEXICON_VERSION versão da camada (padrão: a ativa)
  METQA_LEDGER         registro de gasto (padrão: eval/reports/spend_ledger.jsonl)
  METQA_TRAJECTORIES   "1" grava a trajetória de cada pergunta no workspace (sinal para a evolução)
  METQA_SECRET         chave que assina os tokens de confirmação (padrão: aleatória por processo)
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
    confirm: str = "risk"                          # quando perguntar ao usuário: "risk" (sinal forte) | "always" | "never" (sem usuário)
    readings: int = 2                              # leituras independentes do LLM (1 desliga a concordância: ablação)
    exemplars: bool = True                         # usar e gravar a memória de exemplos verificados
    max_rounds: int = 3                            # voltas de correção com o usuário
    budget_usd: float = 0.10                       # teto desta sessão; o teto acumulado é o do ledger
    max_question_chars: int = field(default=500)
    conservation: bool = True                      # conservação da evidência (números do trecho no valor); False só na ablação
    reread: bool = True                            # releitura isolada do trecho de tempo quando a janela passa de um dia (plano, D1b)
    secret: bytes = field(default_factory=lambda: os.urandom(32), repr=False)   # assina as opções devolvidas (token de confirmação)

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
            secret=env["METQA_SECRET"].encode() if env.get("METQA_SECRET") else None,
        )
        return cls(**{**base, **{k: v for k, v in override.items() if v is not None}})
