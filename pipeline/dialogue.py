"""Camada de verificação com o usuário: o sistema mostra como entendeu a pergunta, em linguagem natural, ANTES de consultar.

Nada aqui usa LLM. O texto de confirmação é montado só da interpretação já validada (o LLM não escreve o que o usuário lê
como "foi isso que entendi") e a resposta do usuário é classificada por regras. Uma correção volta para a etapa 1, que
reinterpreta e passa de novo por TODAS as regras; o "sim" do usuário soma à validação, nunca a substitui.

Política de quando perguntar (`confirm_policy`):
  "always"       sempre confirma;
  "assumptions"  confirma quando o SISTEMA assumiu algo que a pergunta não disse (todas as estações, todo o histórico) ou
                 quando o usuário já corrigiu uma vez (o resultado da correção também precisa ser visto);
  "never"        não pergunta (só o eco final, como antes).
"""
from __future__ import annotations

import re
from typing import Callable, Protocol

from .textsafe import clean
from .validators import PipelineInterpretation
from .vocab import OntologyIndex, expand, fold

MAX_REPLY_CHARS = 500           # resposta do usuário vai para o LLM como DADO: tamanho limitado
CONFIRM_WORDS = {"sim", "s", "ok", "isso", "certo", "correto", "confirmo", "confirmado", "exato", "exatamente", "perfeito",
                 "isso mesmo", "esta certo", "esta correto", "pode seguir", "pode continuar", "pode prosseguir", "segue", "vai"}
CANCEL_WORDS = {"cancelar", "cancela", "cancele", "desisto", "deixa pra la", "deixa para la", "sair", "esquece"}
DENY_WORDS = {"nao", "n", "errado", "incorreto", "esta errado", "nao esta certo", "nao e isso", "nao e"}

ConfirmChannel = Callable[[str], str]           # recebe o texto mostrado ao usuário, devolve o que ele respondeu


class UserChannel(Protocol):
    def __call__(self, prompt: str) -> str: ...


def assumptions(interp: PipelineInterpretation) -> list[str]:
    """O que o sistema decidiu sozinho: ausência de estação, de período. Dito às claras, não escondido num default."""
    out = []
    if not interp.entities:
        out.append("a pergunta não citou estação: usarei TODAS as estações")
    if not interp.period and not interp.instant:
        out.append("a pergunta não limitou o tempo: usarei TODO o histórico disponível")
    return out


def describe(interp: PipelineInterpretation, index: OntologyIndex) -> str:
    names = [index.properties[expand(p)].labels[0] for p in interp.properties
             if expand(p) in index.properties and index.properties[expand(p)].labels]
    parts = [f"grandeza: {', '.join(names) or 'n/d'}"]
    parts.append("estação: " + (", ".join(str(e.get("text") or e["iri"]) for e in interp.entities) if interp.entities else "todas"))
    if interp.instant:
        parts.append(f"instante: {interp.instant}")
    elif interp.period:
        # Todas as estações são tratadas em UTC−3 (hipótese P-16): o Brasil tem UTC−2 a UTC−5, então "o dia" de uma estação do
        # Amazonas ou do Acre é o dia em horário de Brasília, não o dia local dela. Dito aqui para o usuário poder discordar.
        parts.append(f"período: {interp.period['start']} a {interp.period['end']} (dias em UTC−3, horário de Brasília: hipótese ainda não confirmada para todas as estações)")
    else:
        parts.append("período: todo o histórico disponível")
    if interp.aggregation:
        parts.append(f"agregação: {interp.aggregation}")
    if interp.filters:
        parts.append("filtro: " + "; ".join(f"{f.get('op')} {f.get('value')}" for f in interp.filters))
    if interp.record_kind == "forecast":
        parts.append("tipo: previsão")
    if interp.structured:                             # a forma do resultado, dita às claras: é o que o usuário confere
        names = {"station": "estação", "year": "ano", "month": "mês", "day": "dia", "value": "valor medido"}
        short = lambda x: names.get(x) or expand(x).rsplit("#", 1)[-1]
        if interp.group_by:
            parts.append("resultado por: " + ", ".join(short(d) for d in interp.group_by))
        if interp.attributes:
            parts.append("mostrando também: " + ", ".join(short(a) for a in interp.attributes))
        if interp.daily:
            d = interp.daily
            parts.append(f"conta DIAS em que o {d['agg']} do dia {d['op']} {d['value']}")
        if interp.order:
            parts.append(f"ordem: {'decrescente' if interp.order['direction'] == 'desc' else 'crescente'} pela agregação, só os {interp.order['limit']} primeiros")
    return " · ".join(parts)


def confirmation_prompt(interp: PipelineInterpretation, index: OntologyIndex, notice: str = "") -> str:
    lines = [notice] if notice else []
    lines.append("Entendi sua pergunta assim — " + describe(interp, index) + ".")
    lines += [f"Atenção: {a}." for a in assumptions(interp)]
    lines.append("Está correto? Responda \"sim\" para seguir, ou diga o que devo corrigir (ex.: \"na verdade é a Estação Vale Verde\").")
    return "\n".join(lines)


def clarification_prompt(reason: str, alternatives: list) -> str:
    """O LLM pediu esclarecimento: em vez de encerrar, mostra o motivo e as leituras possíveis e deixa o usuário escolher.
    Tudo que o LLM escreveu é higienizado e limitado antes de ser mostrado."""
    lines = ["Preciso de um esclarecimento" + (f": {clean(str(reason), 300)}" if reason else ".")]
    alts = [clean(str(a), 200) for a in (alternatives if isinstance(alternatives, list) else [])[:5] if str(a).strip()]
    if alts:
        lines += ["Posso ter entendido de mais de um jeito:"] + [f"  {i}. {a}" for i, a in enumerate(alts, 1)]
    lines.append("Responda com a opção que você quer ou descreva em uma frase (ou \"cancelar\").")
    return "\n".join(lines)


def needs_confirmation(interp: PipelineInterpretation, policy: str, corrections: list[str]) -> bool:
    if policy == "never":
        return False
    if policy == "always" or corrections:
        return True
    return bool(assumptions(interp))


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
