"""Higiene de texto nas fronteiras do sistema (entrada do usuário, saída do LLM, rótulos do grafo).

Por que: o texto que o usuário digita, o que o LLM devolve e os rótulos que vêm do grafo atravessam prompts, relatórios e o
terminal. Sequências ANSI, caracteres de controle e caracteres bidirecionais invisíveis ("trojan source") permitem esconder
conteúdo, reescrever o que o terminal mostra ou alterar a ordem visual de um texto sem mudar os bytes que as regras veem.
"""
from __future__ import annotations

import re
import unicodedata

MAX_QUESTION_CHARS = 1000
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b.")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")           # mantém \t e \n
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁩﻿­]")


def clean(text: str, max_chars: int | None = None) -> str:
    """NFC, sem ANSI, sem controle (exceto \\n e \\t) e sem caracteres invisíveis/bidirecionais."""
    t = unicodedata.normalize("NFC", str(text))
    t = _INVISIBLE.sub("", _CONTROL.sub("", _ANSI.sub("", t)))
    return t[:max_chars] if max_chars else t


def ctx(text: str, max_chars: int = 200) -> str:
    """Texto vindo do grafo que entra num prompt: uma linha, sem marcação que feche as tags de dado."""
    return re.sub(r"\s+", " ", clean(text, max_chars)).replace("<", "‹").replace(">", "›").strip()
