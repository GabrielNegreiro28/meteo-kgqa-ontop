"""Política de confirmação: QUANDO perguntar ao usuário. O risco é calculado da interpretação e das leituras, não da frase.

Sinais FORTES (com eles, pergunta; sem usuário, vira esclarecimento — nunca palpite):
  - as duas leituras independentes divergem;
  - um trecho citado como evidência não está na pergunta (decisão sem base no texto); a grandeza vale também quando o léxico liga algum
    trecho da pergunta ao IRI escolhido (sinônimo), e a comparação ignora aspas, pontuação, caixa e acento;
  - um número escrito na pergunta não aparece em nenhuma evidência (uma restrição pode ter caído);
  - um número do trecho de um campo não está no valor normalizado do campo ("dia 3" que virou o mês inteiro: `understanding/evidence.py`).
Sinais FRACOS (só ditos na resposta, em "Como entendi"; perguntados apenas no modo `always`):
  - estação ou período assumidos por padrão; nenhum exemplo verificado parecido.

O único padrão de texto aqui é o tokenizador de números (`\\d+([.,]\\d+)?`): ele não tenta ENTENDER o número (isso é do LLM), só garante que
nenhum foi ignorado. Não é gramática e não cresce com casos novos.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..understanding.crosscheck import describe_diff
from ..understanding.evidence import conservation as conserved
from ..understanding.evidence import numbers, span_in
from ..understanding.schema import Parsed


@dataclass
class Risk:
    strong: list[str] = field(default_factory=list)
    weak: list[str] = field(default_factory=list)

    def must_ask(self, mode: str) -> bool:
        return mode == "always" or bool(self.strong)


def assess(question: str, a: Parsed, b: Parsed | None, differ: list[str], has_exemplar: bool,
           lexicon_measures: frozenset[str] = frozenset(), conservation: bool = True, station_matches: frozenset[str] | None = None,
           name_numbers: frozenset = frozenset()) -> Risk:
    r = Risk()
    if differ:
        r.strong.append(f"as duas leituras independentes divergem em: {describe_diff(differ)}")
    cq = a.parts[0][1] if a.parts else None
    for field_, text in a.evidence.items():
        if span_in(text, question) or (field_ == "measure" and cq is not None and cq.measure in lexicon_measures):
            continue
        r.strong.append(f"o trecho citado para '{field_}' ('{text}') não está na pergunta")
    for _, part in a.parts:
        required = {"measure", "stations", "time"}
        if part.scope.instant is None or part.aggregation is not None:
            required.add("calc")
        if part.conditions or part.daily:
            required.add("conditions")
        if part.group_by or part.order or part.attributes:
            required.add("shape")
        if part.unit:
            required.add("unit")
        for key in sorted(required):
            if not a.evidence.get(key):
                r.strong.append(f"falta evidência explícita para {key}")
        if station_matches is not None:
            for station in part.stations:
                if station["iri"] not in station_matches:
                    r.strong.append(f"estação sem menção ou alias governado: {station['iri']}")
    cited = set(numbers(" ".join(a.evidence.values())))                            # números inteiros: 6 não está em 2016
    for n in dict.fromkeys(numbers(question)):
        if n not in cited and n not in name_numbers:              # o 20 de "P-20" é parte do nome da estação, não uma restrição
            r.strong.append(f"o número '{n}' da pergunta não foi usado na interpretação")
    if conservation:
        r.strong += conserved(a.evidence, [q for _, q in a.parts])
    if cq is not None:
        if not cq.stations and not a.evidence.get("stations"):
            r.weak.append("sem estação na pergunta: todas as estações")
        if cq.scope.start is None and cq.scope.instant is None and not a.evidence.get("time"):
            r.weak.append("sem período na pergunta: todo o histórico")
        if not cq.stations and not a.evidence.get("stations") and cq.scope.start is None and cq.scope.instant is None and not a.evidence.get("time"):
            r.strong.append("a pergunta não diz estação nem período: responderia sobre tudo")
    if not has_exemplar:
        r.weak.append("nenhuma pergunta parecida já verificada")
    return r
