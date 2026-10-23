"""Incerteza das medições (docs/ANALISE_CRITICA.md, A-01): intervalo de confiança e comparação pareada para placares de n pequeno.

Até aqui os relatórios davam contagens ("22/24 contra 21/24") como se a diferença significasse algo. Com n entre 8 e 24 e uma execução por
condição, quase nenhuma diferença sai do ruído. Este módulo diz isso em números:
  - intervalo de Wilson (95%) para uma proporção, que se comporta bem com n pequeno e perto de 0 ou 1;
  - teste de McNemar EXATO para duas versões nas MESMAS perguntas (conta só as que mudaram de resultado);
  - o menor efeito que o n atual consegue enxergar.

    python -m eval.stats eval/reports/llm_run_v4_real_gen_v4.json eval/reports/llm_run_v6_real_gen_v6.json
"""
from __future__ import annotations

import json
import sys
from math import comb, sqrt
from pathlib import Path

Z95 = 1.959964


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Intervalo de Wilson para k sucessos em n tentativas."""
    if n == 0:
        return 0.0, 1.0
    p, z2 = k / n, z * z
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = z * sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """p bilateral exato: entre as perguntas em que as versões DISCORDAM, quantas favorecem cada uma (binomial com p = 0,5)."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(min(only_a, only_b) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def succeeded(row: dict) -> bool:
    """Comportamento final certo: o status esperado E nenhum resultado conferido como errado."""
    return bool(row["status_ok"]) and row.get("result_match") is not False


def harmful(row: dict) -> bool:
    """O que o usuário não percebe sozinho: número errado entregue, 'sem registros' onde há dados, ou resposta ao que devia ser recusado."""
    s, exp = row["status"], row["expected_status"]
    if s == "answered" and row.get("result_match") is False:
        return True
    if s == "no_results" and exp == "answered":
        return True
    return exp not in ("answered", "no_results") and s in ("answered", "no_results")


def load(path: str | Path) -> dict[str, dict]:
    """Um relatório de execução. Vários arquivos de UMA condição (rodada principal + perguntas rodadas à parte) se juntam com vírgula:
    `a.json,a_rg24.json`. Pergunta repetida entre os arquivos é erro: não há como saber qual vale."""
    out: dict[str, dict] = {}
    for part in str(path).split(","):
        for r in json.loads(Path(part).read_text(encoding="utf-8")):
            if r["id"] in out:
                raise ValueError(f"pergunta {r['id']} aparece em mais de um arquivo de {path}")
            out[r["id"]] = r
    return out


def fmt(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.0f}%  [IC95% {100 * lo:.0f}–{100 * hi:.0f}%]"


def compare(runs: dict[str, dict[str, dict]], allow_partial: bool = False) -> str:
    """Relatório em texto de uma ou mais execuções sobre as mesmas perguntas.

    As execuções têm de ter as MESMAS perguntas: a interseção silenciosa deixava de fora RG24 (rodada à parte) e o placar saía 19/23 em vez de
    20/24 (Codex, C15). Com `allow_partial=True` a interseção é usada e as perguntas excluídas aparecem no relatório."""
    names = list(runs)
    common = sorted(set.intersection(*(set(r) for r in runs.values())))
    dropped = {n: sorted(set(r) - set(common)) for n, r in runs.items() if set(r) - set(common)}
    if dropped and not allow_partial:
        raise ValueError(f"execuções com perguntas diferentes (fora da interseção: {dropped}); junte os arquivos da mesma condição com vírgula "
                         f"ou use allow_partial=True")
    out = [f"Perguntas em comum: {len(common)}", ""]
    if dropped:
        out.insert(1, f"ATENÇÃO, perguntas excluídas da comparação: {dropped}")
    for name in names:
        rows = [runs[name][i] for i in common]
        ok, bad = sum(succeeded(r) for r in rows), sum(harmful(r) for r in rows)
        out.append(f"{name:12} comportamento certo {fmt(ok, len(rows))}   |   dano silencioso {fmt(bad, len(rows))}")
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            only_a = sum(succeeded(runs[a][q]) and not succeeded(runs[b][q]) for q in common)
            only_b = sum(succeeded(runs[b][q]) and not succeeded(runs[a][q]) for q in common)
            out.append(f"\n{a} × {b}: só {a} acerta em {only_a}, só {b} acerta em {only_b}; McNemar exato p = {mcnemar_exact(only_a, only_b):.2f}")
            if only_a + only_b < 6:
                out.append("  (menos de 6 perguntas mudaram de resultado: o McNemar exato bilateral a 5% não rejeita nem se todas favorecerem um lado; a diferença observada é compatível com ruído, e isso NÃO prova que as versões são equivalentes)")
    return "\n".join(out)


def main(paths: list[str]) -> int:
    print(compare({Path(p).stem.replace("llm_run_", ""): load(p) for p in paths}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) if len(sys.argv) > 1 else print(__doc__) or 2)
