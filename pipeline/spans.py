"""Analisadores determinísticos da pergunta (arquitetura v8, interpretação ancorada em trechos).

Por que existe: até o v7, o LLM interpretava a pergunta livremente e as regras de `validators._ground_in_question` tentavam ADIVINHAR o
que ele errou, com uma regex por jeito de escrever ("só dd/mm/aaaa é data"). Cada forma nova de escrever pedia uma regra nova, e o que
nenhuma regra conhecia passava em silêncio (medido no conjunto novo_a: "dia 15 de fevereiro" virou fevereiro inteiro em E07/E11/E43).

Aqui fica o que tem GRAMÁTICA FECHADA em português e por isso pode ser lido por código, sem LLM: datas (numéricas e por extenso), meses,
anos, intervalos, trimestre/semestre, estação do ano, parte do dia, fim de semana, horário, número com unidade e unidade citada sem número.
Cada fato traz o TRECHO e a posição na pergunta: a conciliação (pipeline/reconcile.py) confere a interpretação do LLM contra esses fatos,
e o que sobrar sem dono na pergunta vira pedido de esclarecimento, não resposta errada.

O texto é sempre lido já dobrado (`vocab.fold`: minúsculas, sem acento; "1º" vira "1o"), então as posições são do texto dobrado.
Decisões de calendário declaradas (DECISOES.md D-93): estações do ano austrais e meteorológicas (verão de 2022 = dez/2021 a fev/2022);
partes do dia madrugada [0,6), manhã [6,12), tarde [12,18), noite [18,24); "durante o dia" [6,18).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from .vocab import fold

MONTHS = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
_MES = "(" + "|".join(MONTHS) + ")"
_ANO = r"((?:19|20)\d{2})"
_DIA = r"(\d{1,2})(?:o)?"                          # "1º" dobrado é "1o"
_ORD = {"primeiro": 1, "1o": 1, "segundo": 2, "2o": 2, "terceiro": 3, "3o": 3, "quarto": 4, "4o": 4}
SEASONS = {"verao": (12, 2), "outono": (3, 5), "inverno": (6, 8), "primavera": (9, 11)}
DAY_PARTS = {"madrugada": (0, 6), "manha": (6, 12), "tarde": (12, 18), "noite": (18, 24), "dia": (6, 18)}
WEEKEND, WEEKDAYS = frozenset({5, 6}), frozenset({0, 1, 2, 3, 4})

# unidades: forma escrita -> (unidade QUDT curta, dimensão). A dimensão é o que confere a grandeza (minutos só casam com duração).
UNITS: dict[str, tuple[str, str]] = {
    "°c": ("DEG_C", "temperature"), "oc": ("DEG_C", "temperature"), "graus celsius": ("DEG_C", "temperature"), "graus": ("DEG_C", "temperature"),
    "c": ("DEG_C", "temperature"),
    "%": ("PERCENT", "ratio"), "por cento": ("PERCENT", "ratio"),
    "mm": ("MilliM", "precipitation_depth"), "milimetros": ("MilliM", "precipitation_depth"), "milimetro": ("MilliM", "precipitation_depth"),
    "hpa": ("HectoPA", "pressure"), "hectopascais": ("HectoPA", "pressure"), "hectopascal": ("HectoPA", "pressure"),
    "nos": ("KN", "speed"), "no": ("KN", "speed"), "kt": ("KN", "speed"), "kts": ("KN", "speed"),
    "km/h": ("KiloM-PER-HR", "speed"),
    "km": ("KiloM", "length"), "quilometros": ("KiloM", "length"), "quilometro": ("KiloM", "length"),
    "m": ("M", "length"), "metros": ("M", "length"), "metro": ("M", "length"),
    "oitavos": ("OKTA", "cover"), "oitavo": ("OKTA", "cover"),
    "minutos": ("MIN", "time"), "minuto": ("MIN", "time"), "min": ("MIN", "time"),
}
# dimensão de cada unidade da ontologia (index.properties[...].unit): a mesma grade acima, do lado da grandeza
UNIT_DIMENSION = {"DEG_C": "temperature", "PERCENT": "ratio", "MilliM": "precipitation_depth", "HectoPA": "pressure", "KN": "speed",
                  "M": "length", "KiloM": "length", "DEG": "angle", "MIN": "time", "OKTA": "cover"}
# unidade citada SEM número ("em metros", "quantos mm", "minutos de chuva"): só as que não são palavras comuns sozinhas
_BARE_UNITS = ("°c", "graus celsius", "por cento", "mm", "milimetros", "hpa", "hectopascais", "kt", "km", "quilometros", "metros",
               "oitavos", "minutos")

NUMBER_WORDS = {"zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8,
                "nove": 9, "dez": 10, "quinze": 15, "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "cem": 100}


@dataclass(frozen=True)
class Fact:
    kind: str                          # day | days | month | months | year | years | quarter | semester | season | day_part | weekdays | instant | relative
    span: str                          # trecho (texto dobrado)
    pos: tuple[int, int]
    start: date | None = None          # janela de calendário [start, end], fim INCLUSIVO (como `period` com inclusive_end)
    end: date | None = None
    hours: tuple[int, int] | None = None          # parte do dia: [h0, h1) em hora local
    weekdays: frozenset[int] | None = None        # 0 = segunda ... 6 = domingo
    hour: tuple[int, int] | None = None           # instante: (hora, minuto)


@dataclass(frozen=True)
class Quantity:
    value: Decimal | None              # None = unidade citada sem número ("em metros", "quantos mm")
    unit: str | None                   # unidade QUDT curta (DEG_C, MilliM...) ou None quando o número não tem unidade
    dimension: str | None
    span: str
    pos: tuple[int, int]


@dataclass
class Reading:
    """Tudo o que a pergunta diz de tempo e de quantidade, lido sem LLM."""
    text: str                                        # pergunta dobrada
    time: list[Fact] = field(default_factory=list)
    quantities: list[Quantity] = field(default_factory=list)

    @property
    def windows(self) -> list[tuple[date, date]]:
        """Janelas de calendário da pergunta, já combinadas: um fato mais específico DENTRO de outro (dia dentro do ano) vale o mais
        específico; janelas disjuntas ficam separadas (comparação: 'janeiro de 2016 ou janeiro de 2025')."""
        cal = sorted({(f.start, f.end) for f in self.time if f.start is not None}, key=lambda w: (w[1] - w[0], w[0]))
        out: list[tuple[date, date]] = []
        for s, e in cal:                                  # do mais curto ao mais longo: o longo que CONTÉM um curto já escolhido some
            if not any(s <= s2 and e2 <= e for s2, e2 in out):
                out.append((s, e))
        return sorted(out)

    @property
    def hours(self) -> tuple[int, int] | None:
        return next((f.hours for f in self.time if f.hours), None)

    @property
    def weekdays(self) -> frozenset[int] | None:
        return next((f.weekdays for f in self.time if f.weekdays), None)

    @property
    def relative(self) -> bool:
        return any(f.kind == "relative" for f in self.time)

    def covered(self) -> list[tuple[int, int]]:
        return [f.pos for f in self.time] + [q.pos for q in self.quantities]


def _month_end(y: int, m: int) -> date:
    return date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


class _Scanner:
    """Casa padrões do mais específico ao mais geral; um trecho já consumido não é relido por um padrão mais geral."""

    def __init__(self, text: str):
        self.text, self.taken = text, [False] * len(text)

    def scan(self, pattern: str):
        for m in re.finditer(pattern, self.text):
            if not any(self.taken[m.start():m.end()]):
                for i in range(m.start(), m.end()):
                    self.taken[i] = True
                yield m


_RELATIVE = (r"\b(?:hoje|ontem|anteontem|amanha|agora|atualmente|recentemente|ultim[oa]s?\s+(?:\d+\s+)?(?:dias?|semanas?|meses|mes|horas?|anos?)"
             r"|(?:esta|essa|nesta|nessa)\s+(?:semana|mes|ano)|(?:semana|mes|ano)\s+(?:passad[oa]|que\s+vem|proxim[oa]))\b")
_UNIT_GUARD = r"(?!\s*(?:m\b|mm\b|hpa|km|kt|°|%|graus|metros|nos\b))"


def parse_time(text: str) -> tuple[list[Fact], _Scanner]:
    t = fold(text)
    sc = _Scanner(t)
    facts: list[Fact] = []

    def add(kind, m, start=None, end=None, **kw):
        facts.append(Fact(kind, m.group(0).strip(), (m.start(), m.end()), start, end, **kw))

    for m in sc.scan(_RELATIVE):
        add("relative", m)
    # instante: data numérica ou por extenso + horário ("em 05/03/2026 às 12h", "ao meio-dia")
    hm = r"(?:as\s+|a\s+|ao\s+)?(?:(\d{1,2})\s*h(?:\s*(\d{2}))?\b|(meio-dia)|(meia-noite))"
    for m in sc.scan(rf"\b(\d{{1,2}})/(\d{{1,2}})/(\d{{4}})\s+{hm}"):
        d = _safe_date(int(m[3]), int(m[2]), int(m[1]))
        h = (12, 0) if m[6] else (0, 0) if m[7] else (int(m[4]), int(m[5] or 0))
        if d:
            add("instant", m, d, d, hour=h)
    # intervalo de datas numéricas: "entre 03/03/2026 e 05/03/2026"
    for m in sc.scan(r"\b(?:entre|de)\s+(\d{1,2})/(\d{1,2})/(\d{4})\s+(?:e|a|ate)\s+(\d{1,2})/(\d{1,2})/(\d{4})\b"):
        a, b = _safe_date(int(m[3]), int(m[2]), int(m[1])), _safe_date(int(m[6]), int(m[5]), int(m[4]))
        if a and b:
            add("days", m, min(a, b), max(a, b))
    for m in sc.scan(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"):
        d = _safe_date(int(m[3]), int(m[2]), int(m[1]))
        if d:
            add("day", m, d, d)
    # intervalo de dias no mesmo mês: "entre 1º e 15 de setembro de 2022", "de 1 a 15 de março de 2021"
    for m in sc.scan(rf"\b(?:entre|de|do dia)\s+(?:o\s+)?(?:dia\s+)?{_DIA}\s+(?:e|a|ate)\s+(?:o\s+)?(?:dia\s+)?{_DIA}\s+de\s+{_MES}\s+de\s+{_ANO}\b"):
        y, mo = int(m[4]), MONTHS.index(m[3]) + 1
        a, b = _safe_date(y, mo, int(m[1])), _safe_date(y, mo, int(m[2]))
        if a and b:
            add("days", m, min(a, b), max(a, b))
    # dia por extenso: "dia 15 de fevereiro de 2024", "14 de outubro de 2019"
    for m in sc.scan(rf"\b(?:(?:no\s+)?dia\s+)?{_DIA}\s+de\s+{_MES}\s+de\s+{_ANO}\b"):
        d = _safe_date(int(m[3]), MONTHS.index(m[2]) + 1, int(m[1]))
        if d:
            add("day", m, d, d)
    # intervalo de meses: "de dezembro de 2021 a fevereiro de 2022", "entre março e maio de 2021". Com "e" só depois de "entre":
    # "janeiro de 2016 e janeiro de 2025" sem "entre" é comparação de dois meses, não intervalo.
    for m in sc.scan(rf"\b(?:entre\s+{_MES}\s+de\s+{_ANO}\s+e|(?:de\s+)?{_MES}\s+de\s+{_ANO}\s+(?:a|ate))\s+{_MES}\s+de\s+{_ANO}\b"):
        m1, y1 = (m[1], m[2]) if m[1] else (m[3], m[4])
        a, b = date(int(y1), MONTHS.index(m1) + 1, 1), _month_end(int(m[6]), MONTHS.index(m[5]) + 1)
        if a <= b:
            add("months", m, a, b)
    for m in sc.scan(rf"\b(?:entre\s+{_MES}\s+e|de\s+{_MES}\s+(?:a|ate))\s+{_MES}\s+de\s+{_ANO}\b"):
        y, a, b = int(m[4]), MONTHS.index(m[1] or m[2]) + 1, MONTHS.index(m[3]) + 1
        if a <= b:
            add("months", m, date(y, a, 1), _month_end(y, b))
    # dois meses com o ano dito uma vez: "em abril ou em outubro de 2021" (comparação; cada mês é uma janela)
    for m in sc.scan(rf"\b{_MES}\s+(?:ou|e)\s+(?:em\s+|no\s+mes\s+de\s+)?{_MES}\s+de\s+{_ANO}\b"):
        y = int(m[3])
        for name in (m[1], m[2]):
            mo = MONTHS.index(name) + 1
            facts.append(Fact("month", m.group(0).strip(), (m.start(), m.end()), date(y, mo, 1), _month_end(y, mo)))
    for m in sc.scan(r"\b(?:meia-noite|meio-dia)\b"):            # horário solto: não é a parte do dia "noite"
        add("clock", m, hour=(0, 0) if m.group(0) == "meia-noite" else (12, 0))
    for m in sc.scan(rf"\b{_MES}\s+(?:de\s+|do\s+ano\s+de\s+)?{_ANO}\b"):
        y, mo = int(m[2]), MONTHS.index(m[1]) + 1
        add("month", m, date(y, mo, 1), _month_end(y, mo))
    # trimestre/semestre/estação do ano
    ords = "|".join(_ORD)
    for m in sc.scan(rf"\b({ords})\s+trimestre\s+(?:de|do\s+ano\s+de)\s+{_ANO}\b"):
        y, q = int(m[2]), _ORD[m[1]]
        add("quarter", m, date(y, 3 * q - 2, 1), _month_end(y, 3 * q))
    for m in sc.scan(rf"\b({ords})\s+semestre\s+(?:de|do\s+ano\s+de)\s+{_ANO}\b"):
        y, s = int(m[2]), _ORD[m[1]]
        if s <= 2:
            add("semester", m, date(y, 6 * s - 5, 1), _month_end(y, 6 * s))
    for m in sc.scan(rf"\b({'|'.join(SEASONS)})\s+de\s+{_ANO}\b"):
        y, (a, b) = int(m[2]), SEASONS[m[1]]
        add("season", m, date(y - 1 if a > b else y, a, 1), _month_end(y, b))
    # anos
    for m in sc.scan(rf"(?<![\d/])(?:de|entre|desde)?\s*{_ANO}\s*(?:a|ate|ao|e|-)\s*{_ANO}(?![\d/])"):
        a, b = int(m[1]), int(m[2])
        if a <= b:
            add("years", m, date(a, 1, 1), date(b, 12, 31))
    for m in sc.scan(rf"(?<![\d/.,]){_ANO}(?![\d/.,]){_UNIT_GUARD}"):
        y = int(m[1])
        add("year", m, date(y, 1, 1), date(y, 12, 31))
    # mês sem ano ("a média de julho"): lido, mas SEM janela; quem concilia decide (todos os julhos? qual ano?), não o analisador
    for m in sc.scan(rf"\b{_MES}\b"):
        add("month_any", m)
    # recortes que não são janela de calendário: parte do dia e dias da semana
    for m in sc.scan(r"\b(?:(?:de|da|na|pela|durante\s+a|a)\s+)?(madrugada|manha|tarde|noite)s?\b|\bdurante\s+o\s+(dia)\b|\b(noturn|diurn)\w*"):
        part = m[1] or m[2] or ("noite" if m[3] == "noturn" else "dia")
        add("day_part", m, hours=DAY_PARTS[part])
    for m in sc.scan(r"\b(?:(?:nos|no|aos|ao)\s+)?(?:fins?|finais)\s+de\s+semana\b"):
        add("weekdays", m, weekdays=WEEKEND)
    for m in sc.scan(r"\b(?:(?:nos|aos|em)\s+)?dias\s+uteis\b"):
        add("weekdays", m, weekdays=WEEKDAYS)
    for m in sc.scan(r"\b(?:(?:nos|aos)\s+)?(sabados|domingos)\b"):
        add("weekdays", m, weekdays=frozenset({5}) if m[1] == "sabados" else frozenset({6}))
    return facts, sc


def parse_quantities(text: str, sc: _Scanner | None = None) -> list[Quantity]:
    """Números com unidade (limiares, valores) e unidades citadas sem número. Lê o que o tempo NÃO consumiu: '2024' não é limiar."""
    t = fold(text)
    sc = sc or _Scanner(t)
    out: list[Quantity] = []
    units = "|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True))
    num = r"(-?\d+(?:[.,]\d+)?|" + "|".join(NUMBER_WORDS) + ")"
    for m in sc.scan(rf"(?<![\w.,/-]){num}(?:\s*({units})(?![a-z]))?"):
        raw = m[1]
        try:
            v = Decimal(NUMBER_WORDS[raw]) if raw in NUMBER_WORDS else Decimal(raw.replace(",", "."))
        except InvalidOperation:
            continue
        if m[2] is None and raw in NUMBER_WORDS:      # "um", "uma" sem unidade são artigo, não número
            for i in range(m.start(), m.end()):
                sc.taken[i] = False
            continue
        unit, dim = UNITS.get(m[2], (None, None)) if m[2] else (None, None)
        out.append(Quantity(v, unit, dim, m.group(0).strip(), (m.start(), m.end())))
    bare = "|".join(re.escape(u) for u in sorted(_BARE_UNITS, key=len, reverse=True))
    for m in sc.scan(rf"(?<![\w°])({bare})(?![\w])"):
        unit, dim = UNITS[m[1]]
        out.append(Quantity(None, unit, dim, m[1], (m.start(), m.end())))
    return sorted(out, key=lambda q: q.pos)


def read(question: str) -> Reading:
    facts, sc = parse_time(question)
    return Reading(sc.text, sorted(facts, key=lambda f: f.pos), parse_quantities(question, sc))
