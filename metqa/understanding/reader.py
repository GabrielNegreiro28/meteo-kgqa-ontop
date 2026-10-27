"""Leitor determinístico: o que a pergunta diz de tempo, números e unidades, lido por código (gramática fechada, sem LLM).

A implementação é a de `pipeline/spans.py` (testada contra todas as perguntas de todos os conjuntos). Aqui ficam só duas coisas do MVP:
uma correção do usuário que fala de tempo SUBSTITUI o tempo da pergunta, e a divisão de uma comparação ("janeiro de 2016 ou janeiro de 2025")
em uma leitura por janela, que o planejador transforma em duas subconsultas.
"""
from __future__ import annotations

from pipeline.spans import Fact, Reading, read

CALENDAR = {"day", "days", "month", "months", "year", "years", "quarter", "semester", "season"}


def read_question(question: str, corrections: list[str] | tuple[str, ...] = ()) -> Reading:
    r = read(question)
    for c in corrections:
        rc = read(c)
        if rc.time:
            r.time = rc.time
        r.quantities += rc.quantities
    return r


def split_windows(r: Reading) -> list[tuple[str, Reading]]:
    """Uma leitura por janela de calendário disjunta. Com uma janela (ou nenhuma), devolve a própria leitura. Os recortes que não são janela
    (parte do dia, dias da semana) valem para todas as partes."""
    windows = r.windows
    if len(windows) <= 1:
        return [("", r)]
    shared = [f for f in r.time if f.kind not in CALENDAR and f.start is None]
    out = []
    for s, e in windows:
        own = next((f for f in r.time if (f.start, f.end) == (s, e) and f.kind in CALENDAR and f.span.count(" ou ") == 0), None)
        label = own.span if own else (f"{s:%d/%m/%Y}" if s == e else f"{s:%d/%m/%Y} a {e:%d/%m/%Y}")
        window = Fact("window", label, own.pos if own else (0, 0), s, e)
        out.append((label, Reading(r.text, [window, *shared], list(r.quantities))))
    return out
