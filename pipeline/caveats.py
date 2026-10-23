"""Ressalvas determinísticas que acompanham a resposta (documento da arquitetura, §12: o sintetizador "reporta conflitos e abstenções"
e "o texto segue o nível de confiança").

Nenhuma é escrita por LLM e nenhuma depende da pergunta: saem do que a consulta devolveu e de anotações revisáveis da ontologia.
Existem porque a auditoria dos dados (docs/ANALISE_CRITICA.md, seção 4) achou coisas que um número sozinho esconde:
  - grandeza com leitura censurada (visibilidade: 80% das leituras estão no teto de 20 km);
  - ranking que premia estação com quase nenhuma leitura (n=149 ao lado de n=16.773);
  - "n" que conta LEITURAS e não boletins (32% das leituras de vento são extras: uma por cabeceira);
  - dias em horário de Brasília (UTC−3) para todas as estações (hipótese P-16).
"""
from __future__ import annotations

from statistics import median
from typing import Any

from .vocab import OntologyIndex, expand

COUNT_VARS = {"n", "count", "cnt"}
LOW_SAMPLE_RATIO = 0.10        # grupo com menos de 10% da mediana de leituras dos grupos exibidos
MIN_GROUPS = 3                 # com menos de 3 grupos a mediana não diz nada
ABS_MIN_READINGS = 30          # piso absoluto: valor agregado sobre menos leituras que isso é anedota, não estatística (Codex C10)


def _label(binding: dict[str, dict[str, str]]) -> str:
    """Nome curto do grupo de uma linha: a 1ª coluna que é IRI (estação) ou texto/data, na ordem em que o resultado a projeta."""
    for var, term in binding.items():
        if var.lower() in COUNT_VARS:
            continue
        v = term.get("value", "")
        if term.get("type") == "uri":
            return v.rstrip("/").rsplit("/", 1)[-1]
        try:
            float(v)
        except ValueError:
            return v
    return "?"


def low_sample_groups(results: dict[str, Any] | None) -> tuple[list[tuple[str, int]], float]:
    """([(grupo, n), …] com poucas leituras, mediana de n). Vazio quando não há contagem ou há poucos grupos."""
    if not results or "results" not in results:
        return [], 0.0
    rows = results["results"]["bindings"]
    n_var = next((v for v in results.get("head", {}).get("vars", []) if v.lower() in COUNT_VARS), None)
    if n_var is None or len(rows) < MIN_GROUPS:
        return [], 0.0
    counted = []
    for b in rows:
        try:
            counted.append((_label(b), int(float(b[n_var]["value"]))))
        except (KeyError, ValueError):
            continue
    if len(counted) < MIN_GROUPS:
        return [], 0.0
    med = median(n for _, n in counted)
    return [(g, n) for g, n in counted if n < LOW_SAMPLE_RATIO * med], med


def tiny_sample_groups(results: dict[str, Any] | None, floor: int = ABS_MIN_READINGS) -> list[tuple[str, int]]:
    """Grupos com menos de `floor` leituras, qualquer que seja o número de grupos. A regra relativa (acima) não vê top-1/top-2 nem o caso
    em que TODOS os grupos têm pouca cobertura, porque compara com a mediana dos próprios grupos exibidos."""
    if not results or "results" not in results:
        return []
    n_var = next((v for v in results.get("head", {}).get("vars", []) if v.lower() in COUNT_VARS), None)
    if n_var is None:
        return []
    out = []
    for b in results["results"]["bindings"]:
        try:
            n = int(float(b[n_var]["value"]))
        except (KeyError, ValueError):
            continue
        if 0 < n < floor:
            out.append((_label(b), n))
    return out


def answer_caveats(interp, results: dict[str, Any] | None, index: OntologyIndex) -> list[str]:
    """Ressalvas de uma resposta com resultado. A ordem é a de importância para quem lê."""
    out: list[str] = []
    for p in interp.properties:
        info = index.properties.get(expand(p)) if isinstance(p, str) else None
        if info and info.caveat and info.caveat not in out:
            out.append(info.caveat)
    low, med = low_sample_groups(results)
    if low:
        shown = ", ".join(f"{g} (n={n})" for g, n in low[:3]) + (f" e mais {len(low) - 3}" if len(low) > 3 else "")
        out.append(f"{len(low)} grupo(s) têm poucas leituras frente à mediana dos grupos (n={med:g}): {shown}. "
                   "Média e extremos de amostras pequenas são pouco confiáveis.")
    tiny = [] if interp.aggregation == "count" else [t for t in tiny_sample_groups(results) if t not in low]   # em contagem, o n É a resposta
    if tiny:
        shown = ", ".join(f"{g} (n={n})" for g, n in tiny[:3]) + (f" e mais {len(tiny) - 3}" if len(tiny) > 3 else "")
        out.append(f"{len(tiny)} resultado(s) vêm de menos de {ABS_MIN_READINGS} leituras: {shown}. Com tão pouca cobertura o valor não é representativo "
                   "(a estação pode ter quase não operado no período).")
    if interp.aggregation == "count":
        out.append("As contagens são de leituras, não de boletins: um boletim pode ter mais de uma leitura "
                   "(por exemplo, uma por cabeceira de pista).")
    return out


def format_caveats(caveats: list[str]) -> str:
    return "Ressalvas:\n" + "\n".join(f"- {c}" for c in caveats) if caveats else ""
