"""Evidência: liga o VALOR normalizado ao TRECHO da pergunta que o justifica (plano, D1 e D2).

Duas leituras do LLM podem errar juntas ("dia 3 de março" virar o mês inteiro nas duas). Concordância não pega isso; a conservação pega:
todo número citado no trecho de um campo tem de aparecer no valor normalizado desse campo. É aritmética sobre o que o LLM já normalizou, sem
tentar entender a frase (o único padrão de texto é o tokenizador de números e a lista fechada dos nomes dos meses, vocabulário do calendário).

A comparação do trecho com a pergunta é tolerante na FORMA (aspas, pontuação, caixa, acento, reticências) e rígida no CONTEÚDO: as palavras do
trecho precisam estar na pergunta, na mesma ordem.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from ..domain import CanonicalQuery

NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
WORD = re.compile(r"\w+")
MONTHS = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text).lower())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def words(text: str) -> list[str]:
    return WORD.findall(norm(text))


def span_in(span: str, question: str) -> bool:
    """As palavras do trecho aparecem na pergunta, na mesma ordem (podem ter palavras no meio: o LLM às vezes junta dois pedaços)."""
    q = iter(words(question))
    return all(any(w == x for x in q) for w in words(span))


def numbers(text: str) -> list[Decimal]:
    """Números como escritos em português: 1.000 = mil, 2,5 = dois e meio; '18h' dá 18."""
    out = []
    for tok in NUMBER.findall(norm(text)):
        t = tok.replace(".", "") if re.fullmatch(r"\d{1,3}(\.\d{3})+", tok) else tok.replace(",", ".")
        try:
            out.append(Decimal(t))
        except InvalidOperation:
            continue
    return out


def _time_values(parts: list[CanonicalQuery]) -> tuple[set[int], set[int]]:
    """(números que o tempo normalizado justifica sempre, números que só valem como mês)."""
    always, months = set(), set()
    for cq in parts:
        s = cq.scope
        for d in (s.start, s.end):
            if d is not None:
                always |= {d.year, d.day}
                months.add(d.month)
        if s.instant is not None:
            always |= {s.instant.year, s.instant.day, s.instant.hour, s.instant.minute, s.instant.hour % 12 or 12}
            months.add(s.instant.month)
        if s.hours:
            always |= set(s.hours) | {(h + 1) % 24 for h in s.hours} | ({24} if 23 in s.hours else set())
    return always, months


def conservation(evidence: dict[str, str], parts: list[CanonicalQuery]) -> list[str]:
    """Sinais fortes: números do trecho que o valor normalizado não carrega."""
    out = []
    time = evidence.get("time", "") + " " + evidence.get("period", "")
    if time.strip() and parts:
        always, months = _time_values(parts)
        named_month = any(m in words(time) for m in MONTHS)
        for n in dict.fromkeys(numbers(time)):
            if n != n.to_integral_value():
                continue
            i = int(n)
            if i in always or (not named_month and i in months):
                continue
            out.append(f"o número '{i}' do trecho de tempo ('{time.strip()}') não está no período normalizado")
    cond = evidence.get("conditions", "")
    if cond and parts:
        given = {Decimal(str(c["value"])) for cq in parts for c in [*cq.conditions, *([cq.daily] if cq.daily else [])]}
        for n in dict.fromkeys(numbers(cond)):
            if n not in given:
                out.append(f"o número '{n}' do trecho das condições ('{cond}') não está nas condições normalizadas")
    shape = evidence.get("shape", "")
    if shape and parts:
        allowed = {Decimal(cq.order["limit"]) for cq in parts if cq.order} | {Decimal(x) for x in _time_values(parts)[0]}
        for n in dict.fromkeys(numbers(shape)):
            if n not in allowed:
                out.append(f"o número '{n}' do trecho da forma ('{shape}') não está na forma normalizada")
    return out


def time_key(parts: list[CanonicalQuery]) -> list[tuple]:
    """O tempo normalizado, para comparar com a releitura isolada do trecho."""
    return sorted((s.start, s.end, s.hours, s.weekdays, s.instant) for s in (cq.scope for cq in parts))


def needs_reread(evidence: dict[str, str], parts: list[CanonicalQuery]) -> bool:
    """Releitura isolada vale a chamada quando o trecho de tempo pode ter sido alargado: janela de mais de um dia ou nome de mês."""
    if not evidence.get("time") or not parts:
        return False
    wide = any(cq.scope.start is not None and cq.scope.end != cq.scope.start for cq in parts)
    return wide or any(m in words(evidence["time"]) for m in MONTHS)
