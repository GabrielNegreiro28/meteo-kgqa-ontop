"""Intérprete: uma LEITURA da pergunta = uma chamada ao LLM (porta `LLM`, `pipeline/llm.py::LLMClient`), num de dois enquadramentos.

O LLM recebe o cardápio do Catálogo (grandezas com unidade e agregações, unidades conhecidas, estações reconhecidas, dimensões), exemplos
VERIFICADOS parecidos (memória) e, numa volta de correção, a interpretação anterior e o que o usuário disse. Devolve a consulta normalizada.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pipeline.llm import LLMClient, parse_json_object
from pipeline.textsafe import clean

from ..knowledge import DomainCatalog, LexiconHit
from .prompts import KEYS, KEYS_B, READING_A, READING_B, REREAD_KEYS, REREAD_TIME

MAX_TOKENS = 1600
FRAMINGS = {"A": (READING_A, KEYS), "B": (READING_B, KEYS_B)}


@dataclass
class Proposal:
    raw: dict[str, Any]
    framing: str
    cost_usd: float = 0.0
    finish: str = ""


def _as_data(text: str) -> str:
    """Texto do usuário vai ao prompt como DADO: sem marcação que feche o bloco nem caracteres de controle."""
    return clean(text).replace("<", "‹").replace(">", "›")


class Interpreter:
    def __init__(self, llm: LLMClient, catalog: DomainCatalog):
        self.llm, self.catalog = llm, catalog

    def read(self, question: str, hit: LexiconHit, framing: str = "A", *, exemplars: list[dict] = (), feedback: str = "",
             corrections: tuple[str, ...] = (), previous: dict | None = None) -> Proposal:
        system, keys = FRAMINGS[framing]
        menu = self.catalog.menu(hit.measures, self.catalog.stations_in(" ".join([question, *corrections])))
        units = "Unidades conhecidas: " + ", ".join(f"unit:{u}" for u in self.catalog.unit_names())
        ex = ""
        if exemplars:
            ex = "<exemplos>\nInterpretações VERIFICADAS de perguntas parecidas (siga o mesmo critério):\n" + "\n".join(
                f"- {_as_data(e['question'])} => {json.dumps(e['ir'], ensure_ascii=False)}" for e in exemplars) + "\n</exemplos>\n"
        prev = (f"<interpretacao_anterior>{json.dumps(previous, ensure_ascii=False)}</interpretacao_anterior>\n" if previous else "")
        fixes = "".join(f"<correcao_do_usuario>{_as_data(c)}</correcao_do_usuario>\n" for c in corrections)
        if corrections:
            fixes += "Aplique as correções do usuário à interpretação anterior; o que ele não corrigiu permanece.\n"
        user = f"{menu}\n{units}\n{ex}<pergunta>{_as_data(question)}</pergunta>\n{prev}{fixes}{feedback}"
        r = self.llm.complete(f"interpret_{framing}", system, user, MAX_TOKENS)
        return Proposal(parse_json_object(r.text, keys), framing, r.cost_usd, r.finish_reason)

    def reread_time(self, span: str) -> dict[str, Any]:
        """Só o trecho de tempo, normalizado de novo numa chamada curta, sem a pergunta nem os exemplos."""
        r = self.llm.complete("reread_time", REREAD_TIME, f"<tempo>{_as_data(span)}</tempo>", 300)
        return parse_json_object(r.text, REREAD_KEYS)
