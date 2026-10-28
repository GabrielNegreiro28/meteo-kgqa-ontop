"""Política de confirmação: QUANDO perguntar ao usuário. O risco é calculado da interpretação e das leituras, não da frase.

Sinais FORTES (com eles, pergunta; sem usuário, vira esclarecimento — nunca palpite):
  - as duas leituras independentes divergem;
  - um trecho citado como evidência não está na pergunta (decisão sem base no texto);
  - um número escrito na pergunta não aparece em nenhuma evidência (uma restrição pode ter caído).
Sinais FRACOS (só ditos na resposta, em "Como entendi"; perguntados apenas no modo `always`):
  - estação ou período assumidos por padrão; nenhum exemplo verificado parecido.

O único padrão de texto aqui é o tokenizador de números (`\\d+([.,]\\d+)?`): ele não tenta ENTENDER o número (isso é do LLM), só garante que
nenhum foi ignorado. Não é gramática e não cresce com casos novos.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ..understanding.crosscheck import describe_diff
from ..understanding.schema import Parsed

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text).lower())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


@dataclass
class Risk:
    strong: list[str] = field(default_factory=list)
    weak: list[str] = field(default_factory=list)

    def must_ask(self, mode: str) -> bool:
        return mode == "always" or bool(self.strong)


def assess(question: str, a: Parsed, b: Parsed | None, differ: list[str], has_exemplar: bool) -> Risk:
    r = Risk()
    q = norm(question)
    if differ:
        r.strong.append(f"as duas leituras independentes divergem em: {describe_diff(differ)}")
    for field_, text in a.evidence.items():
        if norm(text) not in q:
            r.strong.append(f"o trecho citado para '{field_}' ('{text}') não está na pergunta")
    cited = set(NUMBER.findall(" ".join(norm(t) for t in a.evidence.values())))     # números inteiros: "6" não está em "2016"
    for n in dict.fromkeys(NUMBER.findall(q)):
        if n not in cited:
            r.strong.append(f"o número '{n}' da pergunta não foi usado na interpretação")
    cq = a.parts[0][1] if a.parts else None
    if cq is not None:
        if not cq.stations and "station" not in cq.group_by:
            r.weak.append("sem estação na pergunta: todas as estações")
        if cq.scope.start is None and cq.scope.instant is None:
            r.weak.append("sem período na pergunta: todo o histórico")
    if not has_exemplar:
        r.weak.append("nenhuma pergunta parecida já verificada")
    return r
