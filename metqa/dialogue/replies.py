"""Respostas do usuário classificadas por regras (sim / não / cancelar / correção), nunca por LLM: a decisão de seguir não pode depender de
um modelo. E o usuário roteirizado dos testes. O texto mostrado ao usuário é de `channel.py` e `paraphrase.py`."""
from __future__ import annotations

import re

from ..knowledge.index import fold
from ..util.text import clean

MAX_REPLY_CHARS = 500           # resposta do usuário vai para o LLM como DADO: tamanho limitado
CONFIRM_WORDS = {"sim", "s", "ok", "isso", "certo", "correto", "confirmo", "confirmado", "exato", "exatamente", "perfeito",
                 "isso mesmo", "esta certo", "esta correto", "pode seguir", "pode continuar", "pode prosseguir", "segue", "vai"}
CANCEL_WORDS = {"cancelar", "cancela", "cancele", "desisto", "deixa pra la", "deixa para la", "sair", "esquece"}
DENY_WORDS = {"nao", "n", "errado", "incorreto", "esta errado", "nao esta certo", "nao e isso", "nao e"}


def classify_reply(reply: str) -> tuple[str, str]:
    """('confirm'|'cancel'|'deny'|'correct', texto). Regras, não LLM: a decisão de seguir não pode depender de um modelo."""
    raw = clean(reply or "").strip()
    norm = re.sub(r"[^\w\s]", " ", fold(raw))
    norm = re.sub(r"\s+", " ", norm).strip()
    if not norm:
        return "deny", ""
    if norm in CONFIRM_WORDS:
        return "confirm", ""
    if norm in CANCEL_WORDS:
        return "cancel", ""
    if norm in DENY_WORDS:
        return "deny", ""
    # "sim, mas na verdade X" e "não, X": a parte depois do aceno é a correção; sem conteúdo útil, trata como aceno
    m = re.match(r"^(sim|nao)\b[\s,.;:!-]*(.*)$", fold(raw), flags=re.S)     # fold preserva o comprimento: as posições valem para raw
    if m and m.group(2).strip():
        raw = raw[m.start(2):].strip()
    return "correct", raw[:MAX_REPLY_CHARS]


class ScriptedUser:
    """Usuário simulado para testes e experimentos: uma fila de respostas; guarda o que lhe foi mostrado."""

    def __init__(self, replies: list[str]):
        self.replies, self.shown = list(replies), []

    def __call__(self, prompt: str) -> str:
        self.shown.append(prompt)
        return self.replies.pop(0) if self.replies else "cancelar"
