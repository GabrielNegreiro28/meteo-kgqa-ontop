"""Placar adjudicado de condições medidas no MESMO conjunto, sem LLM e sem custo.

  python -m eval.adjudicate novo_a v4=v4_a v5_v1=v5_l1_1,v5_l1_2 v5_v2=v5_l2 v7=v7_a

O comparador automático de `run_independent` só vê números e trata período escrito como texto (`2019-09`, `07`) como divergência. Aqui:
- `correto`: a resposta contém todas as linhas da referência (rótulos de período em qualquer formato), OU divergiu por diferença de limpeza declarada
  em `docs/julgamento_<set>_veredictos.yaml` (`cleaning_difference`) e outra condição deu o mesmo valor (a diferença vem do conjunto de regras, não do acaso);
- `errado`: respondeu e não bate (`pipeline_error`, ou divergência sem veredito); respondeu onde devia recusar ou esclarecer;
- `absteve`: não respondeu pergunta respondível (não é erro de valor, mas não ajuda quem perguntou).
Pergunta que alguma condição não executou (`BUDGET_EXCEEDED`: nem chegou ao LLM) sai do placar de TODAS: só se compara o que todas rodaram.
Os vereditos do arquivo são julgamento do Claude, sem revisão humana: o placar é reproduzível, não um gabarito independente.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

from eval.run_independent import _close
from eval.stats import mcnemar_exact, wilson

ROOT = Path(__file__).resolve().parent.parent


def _nums(row: list) -> list[float]:
    out: list[float] = []
    for x in row:
        if isinstance(x, bool):
            continue
        if isinstance(x, (int, float)):
            out.append(float(x))
        elif isinstance(x, str):
            t = re.sub(r"(\d{4})-(\d{2})(?:-(\d{2}))?", lambda m: " ".join(str(int(g)) for g in m.groups() if g), x)
            out += [float(v) for v in re.findall(r"(?<![\d.])-?\d+(?:\.\d+)?", t)]
    return out


def _row_has(oracle_row: list, system_row: list) -> bool:
    pool = _nums(system_row)
    for w in _nums(oracle_row):
        i = next((k for k, h in enumerate(pool) if _close(w, h)), None)
        if i is None:
            return False
        pool.pop(i)
    return True


def robust_match(system_rows: list[list], oracle_rows: list[list]) -> bool:
    left = list(system_rows)
    for o in oracle_rows:
        i = next((k for k, s in enumerate(left) if _row_has(o, s)), None)
        if i is None:
            return False
        left.pop(i)
    return True


def signature(rows: list[list]) -> frozenset:
    return frozenset(round(v, 1) for r in rows for v in _nums(r))


def load(name: str, files: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in files.split(","):
        for r in json.loads((ROOT / "eval" / "reports" / f"independent_run_{name}_{f}.json").read_text(encoding="utf-8"))["rows"]:
            out[r["id"]] = r
    return out


def not_run(r: dict) -> bool:
    return r["status"] == "execution_error" and "BUDGET_EXCEEDED" in r.get("diagnostics", [])


def classify(conds: dict[str, dict[str, dict]], verdicts: dict[str, dict]) -> dict[str, dict[str, str]]:
    ids = sorted(set.intersection(*[set(d) for d in conds.values()]))
    ids = [i for i in ids if not any(not_run(d[i]) for d in conds.values())]
    out: dict[str, dict[str, str]] = {c: {} for c in conds}
    for i in ids:
        sigs = {c: signature(d[i]["pipeline_rows"]) for c, d in conds.items() if d[i]["status"] == "answered"}
        for c, d in conds.items():
            r = d[i]
            v = (verdicts.get(i) or {}).get("verdict")
            if r["expected_behavior"] == "answerable":
                if r["status"] != "answered":
                    out[c][i] = "absteve"
                elif robust_match(r["pipeline_rows"], r.get("oracle_rows") or []):
                    out[c][i] = "correto"
                elif v == "cleaning_difference" and any(s == sigs[c] for k, s in sigs.items() if k != c):
                    out[c][i] = "correto"
                else:
                    out[c][i] = "errado"
            else:
                out[c][i] = "correto" if (r["status_ok"] or v == "ok") else "errado"
    return out


def main(argv: list[str]) -> int:
    name, spec = argv[0], dict(a.split("=", 1) for a in argv[1:])
    conds = {c: load(name, f) for c, f in spec.items()}
    verdicts = yaml.safe_load((ROOT / "docs" / f"julgamento_{name}_veredictos.yaml").read_text(encoding="utf-8")) or {}
    res = classify(conds, verdicts)
    ids = sorted(next(iter(res.values())))
    skipped = sorted(set.intersection(*[set(d) for d in conds.values()]) - set(ids))
    n = len(ids)
    print(f"{n} perguntas comparáveis (fora do placar por não terem rodado em alguma condição: {skipped or 'nenhuma'})\n")
    print("| condição | correto | errado (resposta entregue) | absteve | IC95% do acerto |\n|---|---|---|---|---|")
    for c, d in res.items():
        k = sum(v == "correto" for v in d.values())
        lo, hi = wilson(k, n)
        print(f"| {c} | {k}/{n} | {sum(v == 'errado' for v in d.values())} | {sum(v == 'absteve' for v in d.values())} | {lo:.0%}–{hi:.0%} |")
    print("\nMcNemar exato (pares discordantes de acerto; p bilateral):")
    names = list(res)
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            oa = sum(res[names[a]][i] == "correto" and res[names[b]][i] != "correto" for i in ids)
            ob = sum(res[names[b]][i] == "correto" and res[names[a]][i] != "correto" for i in ids)
            print(f"  {names[a]} vs {names[b]}: só {names[a]} {oa} · só {names[b]} {ob} · p={mcnemar_exact(oa, ob):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
