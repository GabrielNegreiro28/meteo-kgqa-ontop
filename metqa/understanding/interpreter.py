"""Intérprete: o ÚNICO estágio com LLM no caminho da pergunta (porta `LLM`, `pipeline/llm.py::LLMClient`).

O LLM recebe o cardápio do catálogo (grandezas com unidade e agregações, estações reconhecidas, dimensões) com o destaque do léxico, e devolve
só ESCOLHAS com o trecho literal que justifica cada uma (prompt `INTERPRET_V8`). Não escreve datas, números, unidades nem SPARQL.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pipeline.llm import LLMClient, parse_json_object
from pipeline.prompts import INTERPRET_V8
from pipeline.textsafe import clean

from ..knowledge import DomainCatalog, LexiconHit

KEYS = {"status", "properties", "entities", "aggregation", "filters", "daily", "group_by", "attributes", "order", "record_kind",
        "alternatives", "reason"}
MAX_TOKENS = 1200


@dataclass
class Proposal:
    raw: dict[str, Any]
    cost_usd: float = 0.0
    finish: str = ""


def _as_data(text: str) -> str:
    """Texto do usuário vai ao prompt como DADO: sem marcação que feche o bloco nem caracteres de controle."""
    return clean(text).replace("<", "‹").replace(">", "›")


class Interpreter:
    def __init__(self, llm: LLMClient, catalog: DomainCatalog):
        self.llm, self.catalog = llm, catalog

    def propose(self, question: str, hit: LexiconHit, feedback: str = "", corrections: tuple[str, ...] = ()) -> Proposal:
        menu = self.catalog.menu(hit.measures, self.catalog.stations_in(" ".join([question, *corrections])))
        fixes = "".join(f"<correcao_do_usuario>{_as_data(c)}</correcao_do_usuario>\n" for c in corrections)
        user = f"{menu}\n<pergunta>{_as_data(question)}</pergunta>\n{fixes}{feedback}"
        r = self.llm.complete("interpret", INTERPRET_V8, user, MAX_TOKENS)
        return Proposal(parse_json_object(r.text, KEYS), r.cost_usd, r.finish_reason)
