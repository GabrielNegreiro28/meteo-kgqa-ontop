"""Verificação da resposta em linguagem natural (etapa 3) e resposta determinística de reserva.

O LLM redige; as regras conferem que o texto não afirma o que os resultados não sustentam.
Além do conjunto de números, confere a ASSOCIAÇÃO: quando uma oração cita uma só entidade (estação), os números dela
têm de ser os da linha dessa entidade (ENTITY_VALUE_SWAP). Limite que sobra: troca dentro da mesma oração com duas
entidades, e afirmações qualitativas ("a mais alta"), que nenhuma regra de número alcança.
Ver docs/ESTUDO_SEGURANCA_PIPELINE.md.
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from kgqa.contract import Diagnostic, Status

from .validators import Finding

NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
TRUNCATION_WORDS = ("parcial", "truncad", "limite de linhas", "primeiras linhas", "não inclui todas")
UNIT_SYMBOLS = {"DEG_C": "°C", "PERCENT": "%", "MilliM": "mm", "HectoPA": "hPa", "KN": "kt", "M": "m",
                "DEG": "°", "MIN": "min"}


# Unidades que NUNCA são a unidade de uma grandeza deste grafo; "20,4 K" para um resultado em °C é número certo com unidade errada.
FOREIGN_UNIT_RE = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*\s*(°\s?F|°\s?K|K|F|kelvin|fahrenheit|mph|km/h|m/s|kPa|Pa|mmHg|inHg|polegadas?)(?![\w/])", re.IGNORECASE)


def _variants(token: str) -> list[tuple[Decimal, int]]:
    """Interpretações possíveis do token (pt-BR e en): lista de (valor, casas decimais)."""
    out: list[tuple[Decimal, int]] = []

    def add(txt: str, places: int):
        try:
            out.append((Decimal(txt), places))
        except InvalidOperation:
            pass

    if "," in token and "." in token:
        txt = token.replace(".", "").replace(",", ".")
        add(txt, len(txt.split(".")[1]) if "." in txt else 0)
    elif "," in token:
        parts = token.split(",")
        if len(parts) == 2:
            add(f"{parts[0]}.{parts[1]}", len(parts[1]))
        add(token.replace(",", ""), 0)                      # "1,234" como milhar
    elif "." in token:
        parts = token.split(".")
        if len(parts) == 2:
            add(token, len(parts[1]))
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", token):
            add(token.replace(".", ""), 0)
    else:
        add(token, 0)
    return out


def _digit_groups(text: str) -> set[Decimal]:
    return {Decimal(t) for t in re.findall(r"\d+", text)}


def _numbers_in_results(results: dict[str, Any] | None) -> set[Decimal]:
    nums: set[Decimal] = set()
    if not results:
        return nums
    rows = results.get("results", {}).get("bindings", [])
    nums.update(Decimal(i) for i in range(1, len(rows) + 1))     # contagem de linhas e ordinais
    for b in rows:
        for term in b.values():
            v = term.get("value", "")
            try:
                nums.add(Decimal(v))
            except InvalidOperation:
                pass
            nums |= _digit_groups(v)                             # componentes de datas, códigos
    return nums


def _matches(value: Decimal, places: int, allowed: set[Decimal]) -> bool:
    q = Decimal(1).scaleb(-places)
    for a in allowed:
        if a == value:
            return True
        for mode in (ROUND_HALF_UP, ROUND_HALF_EVEN):
            try:
                if a.quantize(q, rounding=mode) == value:
                    return True
            except InvalidOperation:        # número gigante vindo do texto: não casa, e a checagem não pode quebrar
                break
    return False


def _fold(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


SENTENCE_SPLIT = re.compile(r"\.(?!\d)|\n")
NO_RECORDS = re.compile(r"\b(nao ha (?:registros?|dados)|sem (?:registros?|dados)|nenhum registro|nao (?:foram )?encontrad)")


COUNT_VARS = {"n", "count", "cnt"}


def _row_facts(results: dict[str, Any], entity_labels: dict[str, list[str]] | None,
               main_only: bool = False) -> list[tuple[set[str], set[Decimal]]]:
    """Por linha: (nomes da entidade, números da própria linha). O nome vem do IRI e dos rótulos conhecidos.
    `main_only` deixa de fora a contagem ?n quando há outro valor numérico (ela aparece por acaso em qualquer texto)."""
    rows = []
    for b in results.get("results", {}).get("bindings", []):
        names, nums, main = set(), set(), set()
        for var, term in b.items():
            v = term.get("value", "")
            if term.get("type") == "uri":
                names.add(_fold(v.rstrip("/").rsplit("/", 1)[-1]))
                names.update(_fold(l) for l in (entity_labels or {}).get(v, []))
            else:
                try:
                    d = Decimal(v)
                except InvalidOperation:
                    continue
                nums.add(d)
                if var.lower() not in COUNT_VARS:
                    main.add(d)
        rows.append(({n for n in names if n}, (main or nums) if main_only else nums))
    return rows


def _owned(tok_vars: list[tuple[Decimal, int]], nums: set[Decimal]) -> bool:
    return any(_matches(v, p, nums) for v, p in tok_vars)


AMBIGUITY_RATIO = 3.0     # a menção mais próxima tem de estar ao menos 3x mais perto que a de outra entidade


def check_association(text: str, results: dict[str, Any] | None, entity_labels: dict[str, list[str]] | None = None) -> list[Finding]:
    """Valores trocados entre entidades. Em cada frase, cada número é atribuído à menção de entidade MAIS PRÓXIMA (antes ou
    depois dele, em caracteres) e tem de ser um valor DA entidade dessa menção, ou não ser de nenhuma outra. Se a menção
    mais próxima de outra entidade está a menos de 3x a distância, o número não é atribuível e fica de fora: 'choveu 55,4 mm,
    menos que os 80,0 mm da Vale Verde' tem o 80,0 colado à entidade DEPOIS dele, e atribuí-lo à anterior seria falso positivo
    (foi o que a 1ª versão desta regra fez numa resposta correta)."""
    if not results or "boolean" in results:
        return []
    rows = _row_facts(results, entity_labels)
    groups: dict[frozenset, set[Decimal]] = {}
    for names, nums in rows:
        if names:
            groups.setdefault(frozenset(names), set()).update(nums)
    if len(groups) < 2:
        return []
    out = []
    for sentence in SENTENCE_SPLIT.split(_fold(text)):
        marks = [(m.start(), m.end(), key) for key in groups for n in key
                 for m in re.finditer(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", sentence)]
        if not marks:
            continue
        for tok in NUM_RE.finditer(sentence):
            vs = _variants(tok.group())
            if not vs:
                continue
            dist: dict[frozenset, int] = {}
            for ms, me, key in marks:
                d = ms - tok.end() if ms >= tok.end() else tok.start() - me if me <= tok.start() else 0
                dist[key] = min(dist.get(key, 10**9), max(d, 0))
            ranked = sorted(dist.items(), key=lambda kv: kv[1])
            (key, d0), rest = ranked[0], ranked[1:]
            if rest and rest[0][1] < AMBIGUITY_RATIO * max(d0, 1):
                continue
            others = set().union(*(nums for g, nums in groups.items() if g != key))
            if not _owned(vs, groups[key]) and _owned(vs, others):
                out.append(Finding("L5", Diagnostic("ENTITY_VALUE_SWAP", "error",
                                                    f"O número {tok.group()} pertence a outra linha dos resultados, não à entidade citada junto dele",
                                                    {"token": tok.group(), "trecho": sentence[max(0, tok.start() - 60):tok.end() + 40]})))
    return out


def check_scope(text: str, entity_labels: dict[str, list[str]] | None, scope: set[str] | None) -> list[Finding]:
    """A resposta só pode falar das estações que a consulta cobriu. Medido no diálogo de confirmação: o usuário trocou a estação
    e o texto, escrito a partir da pergunta ORIGINAL, rotulou o número da Vale Verde como sendo da Serra Azul."""
    if not scope or not entity_labels:
        return []
    out, t = [], _fold(text)
    for iri, labels in entity_labels.items():
        if iri in scope:
            continue
        for name in [*labels, iri.rstrip("/").rsplit("/", 1)[-1]]:
            n = _fold(name)
            if n and re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", t):
                out.append(Finding("L5", Diagnostic("ANSWER_MENTIONS_OTHER_ENTITY", "error",
                                                    f"A resposta cita '{name}', que não está no escopo da consulta", {"entity": iri})))
                break
    return out


def check_answer(text: str, question: str, results: dict[str, Any] | None, status: Status,
                 truncated: bool = False, units: dict[str, str] | None = None,
                 entity_labels: dict[str, list[str]] | None = None, scope: set[str] | None = None) -> list[Finding]:
    out: list[Finding] = check_scope(text, entity_labels, scope)
    allowed = _digit_groups(question) | (_numbers_in_results(results) if status == Status.ANSWERED else set())
    for tok in NUM_RE.findall(text):
        variants = _variants(tok)
        if not any(_matches(v, p, allowed) for v, p in variants):
            out.append(Finding("L5", Diagnostic("UNGROUNDED_NUMBER", "error",
                                                f"Número sem respaldo nos resultados: {tok}", {"token": tok})))
    if status == Status.ANSWERED:
        if NO_RECORDS.search(_fold(text)):
            out.append(Finding("L5", Diagnostic("ANSWER_CONTRADICTS_STATUS", "error", "O texto diz que não há registros, mas a consulta devolveu dados")))
        out += check_association(text, results, entity_labels)
        rows = results.get("results", {}).get("bindings", []) if results else []
        if 0 < len(rows) <= 8:                      # resposta que cala linhas inteiras (ex.: lista só uma de três estações)
            text_vars = [v for tok in NUM_RE.findall(text) for v in _variants(tok)]
            for i, (names, nums) in enumerate(_row_facts(results, entity_labels, main_only=True)):
                if nums and not any(_matches(v, p, nums) for v, p in text_vars):
                    out.append(Finding("L5", Diagnostic("ANSWER_OMITS_ROW", "error",
                                                        f"A resposta não traz o valor da linha {i + 1} dos resultados", {"row": i + 1})))
    if status == Status.ANSWERED and truncated and not any(w in text.lower() for w in TRUNCATION_WORDS):
        out.append(Finding("L5", Diagnostic("TRUNCATION_NOT_DISCLOSED", "error",
                                            "Resultado truncado apresentado como completo")))
    if status == Status.ANSWERED and units:
        expected = {UNIT_SYMBOLS.get(u.rsplit("/", 1)[-1].split(":")[-1], "").lower() for u in units.values()}
        for m in FOREIGN_UNIT_RE.finditer(text):
            foreign = re.sub(r"\s", "", m.group(1)).lower()
            if foreign not in expected:
                out.append(Finding("L5", Diagnostic("WRONG_UNIT", "error", f"Unidade incompatível com o resultado: {m.group(1)}", {"unit": m.group(1)})))
        symbols = {UNIT_SYMBOLS.get(u.rsplit("/", 1)[-1].split(":")[-1]) for u in units.values()} - {None}
        if symbols and NUM_RE.search(text) and not any(s in text for s in symbols):
            out.append(Finding("L5", Diagnostic("MISSING_UNIT", "warning", f"Unidade esperada ausente: {sorted(symbols)}")))
    return out


def _fmt(term: dict[str, str]) -> str:
    v = term["value"]
    return v.rstrip("/").rsplit("/", 1)[-1] if term["type"] == "uri" else v


def render_fallback(status: Status, results: dict[str, Any] | None, units: dict[str, str] | None = None,
                    truncated: bool = False) -> str:
    """Resposta sem LLM: cada valor é copiado dos resultados, nada é calculado nem interpretado."""
    if status == Status.NO_RESULTS or not results:
        return "Não há registros para os critérios da pergunta na fonte consultada."
    if "boolean" in results:
        return "Sim." if results["boolean"] else "Não."
    cols = results["head"]["vars"]
    sym = {v: UNIT_SYMBOLS.get(u.rsplit("/", 1)[-1].split(":")[-1], "") for v, u in (units or {}).items()}
    lines = []
    for b in results["results"]["bindings"]:
        parts = [f"{c} = {_fmt(b[c])}{(' ' + sym[c]) if sym.get(c) else ''}" for c in cols if c in b]
        lines.append("- " + "; ".join(parts))
    head = f"Resultado ({len(lines)} linha(s)):"
    if truncated:
        head += " resultado parcial: limite de linhas atingido."
    return head + "\n" + "\n".join(lines)
