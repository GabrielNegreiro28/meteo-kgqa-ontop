"""Canal com o usuário (porta) e as mensagens de confirmação.

- `TerminalChannel`: linha de comando (pergunta e lê a resposta).
- qualquer chamável `prompt -> resposta` serve (testes: `pipeline/dialogue.py::ScriptedUser`).
- sem canal (API, lote): o pipeline devolve `needs_clarification` com as paráfrases e as opções; o cliente reenvia a escolha.

A resposta do usuário é classificada por um conjunto FECHADO de palavras (sim / não / cancelar / número da opção,
`pipeline/dialogue.py::classify_reply`); qualquer outro texto é uma CORREÇÃO, que volta ao LLM. Não há regra sobre o conteúdo da correção.
"""
from __future__ import annotations

import sys
from typing import Callable, Protocol

from pipeline.dialogue import classify_reply


class UserChannel(Protocol):
    def __call__(self, prompt: str) -> str: ...


class TerminalChannel:
    def __call__(self, prompt: str) -> str:
        print(prompt, flush=True)
        try:
            return input("> ")
        except EOFError:
            return "cancelar"


def terminal_if_interactive() -> Callable[[str], str] | None:
    return TerminalChannel() if sys.stdin.isatty() else None


def confirm_message(paraphrase: str, reasons: list[str]) -> str:
    lines = [f"Entendi assim: {paraphrase}."]
    lines += [f"  (atenção: {r})" for r in reasons]
    lines.append("Está certo? Responda \"sim\", \"cancelar\", ou diga o que devo corrigir.")
    return "\n".join(lines)


def choice_message(options: list[str], fields: str) -> str:
    lines = [f"Sua pergunta pode ser lida de mais de um jeito (muda: {fields}):"]
    lines += [f"  {i}. {o}" for i, o in enumerate(options, 1)]
    lines.append("Responda com o número da opção, \"cancelar\", ou diga o que você quer.")
    return "\n".join(lines)


def classify(reply: str, n_options: int = 0) -> tuple[str, str]:
    """('confirm' | 'cancel' | 'choose' | 'correct', valor). 'deny' sem conteúdo vira pedido do que corrigir."""
    text = (reply or "").strip()
    if n_options and text.rstrip(".)") in {str(i) for i in range(1, n_options + 1)}:
        return "choose", text.rstrip(".)")
    kind, rest = classify_reply(text)
    return kind, rest
