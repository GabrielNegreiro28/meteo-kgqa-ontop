"""Placar adjudicado de condições medidas no MESMO conjunto, sem LLM e sem custo.

  python -m eval.adjudicate novo_a v4=v4_a v5_v1=v5_l1_1,v5_l1_2 v5_v2=v5_l2 v7=v7_a

O padrão compara linhas tipadas, com cardinalidade e identificadores preservados. Referência ausente é erro.
As regras abaixo só são usadas com --historical para inspecionar julgamentos antigos, não para validar o contrato 0.4.0:
- `correto`: a resposta contém todas as linhas da referência (rótulos de período em qualquer formato), OU divergiu por diferença de limpeza declarada
  em `docs/julgamento_<set>_veredictos.yaml` (`cleaning_difference` ou `oracle_error`) e outra condição deu o mesmo valor (a diferença vem do conjunto de regras, não do acaso);
- `errado`: respondeu e não bate (`pipeline_error`, ou divergência sem veredito); respondeu onde devia recusar ou esclarecer;
- `absteve`: não respondeu pergunta respondível (não é erro de valor, mas não ajuda quem perguntou).
Pergunta que alguma condição não executou (`BUDGET_EXCEEDED`: nem chegou ao LLM) sai do placar de TODAS: só se compara o que todas rodaram.
Os vereditos do arquivo são julgamento do Claude, sem revisão humana: o placar é reproduzível, não um gabarito independente.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from eval.stats import mcnemar_exact, wilson

ROOT = Path(__file__).resolve().parent.parent


def robust_match(system_rows, oracle_rows):
    from eval.matching import match_rows
    return match_rows(system_rows, oracle_rows)


def signature(rows):
    # Preserve row boundaries, types, identities and multiplicity.
    return tuple(sorted(json.dumps(r, ensure_ascii=False) for r in rows))


def load(name: str, files: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in files.split(","):
        for r in json.loads((ROOT / "eval" / "reports" / f"independent_run_{name}_{f}.json").read_text(encoding="utf-8"))["rows"]:
            out[r["id"]] = r
    return out


def not_run(r: dict) -> bool:
    return r["status"] == "execution_error" and "BUDGET_EXCEEDED" in r.get("diagnostics", [])


def classify(conds: dict[str, dict[str, dict]], verdicts: dict[str, dict], *, historical: bool = False) -> dict[str, dict[str, str]]:
    ids = sorted(set.intersection(*[set(d) for d in conds.values()]))
    ids = [i for i in ids if not any(not_run(d[i]) for d in conds.values())]
    out: dict[str, dict[str, str]] = {c: {} for c in conds}
    for i in ids:
        for c, d in conds.items():
            r = d[i]
            if not historical:
                if r['expected_behavior'] != 'answerable':
                    out[c][i] = 'correto' if r['status_ok'] else 'errado'
                elif r.get('oracle_rows') is None:
                    raise ValueError(f'missing reference: {i}')
                elif r['status'] not in ('answered', 'no_results'):
                    out[c][i] = 'absteve'
                else:
                    out[c][i] = 'correto' if robust_match(r['pipeline_rows'], r['oracle_rows']) else 'errado'
                continue
            v = (verdicts.get(i) or {}).get("verdict")
            if r["expected_behavior"] == "answerable":
                # o oráculo errou ou limpou diferente, e outra condição deu a MESMA resposta: é o conjunto de regras, não acaso
                # (com uma condição só, vale o veredito conferido na base limpa)
                agreed = v in ("cleaning_difference", "oracle_error") and (len(conds) == 1 or any(
                    d[i]["status"] == r["status"] and signature(d[i]["pipeline_rows"]) == signature(r["pipeline_rows"])
                    for k, d in conds.items() if k != c))
                if v == "ok":
                    out[c][i] = "correto"
                elif r["status"] == "no_results" and agreed and v == "oracle_error":
                    out[c][i] = "correto"                 # "não há registros" certo: o oráculo contou um valor que a limpeza descarta
                elif r["status"] != "answered":
                    out[c][i] = "absteve"
                elif robust_match(r["pipeline_rows"], r.get("oracle_rows")) or agreed:
                    out[c][i] = "correto"
                else:
                    out[c][i] = "errado"
            else:
                out[c][i] = "correto" if (r["status_ok"] or v == "ok") else "errado"
    return out


def main(argv: list[str]) -> int:
    historical = '--historical' in argv
    argv = [a for a in argv if a != '--historical']
    name, spec = argv[0], dict(a.split("=", 1) for a in argv[1:])
    conds = {c: load(name, f) for c, f in spec.items()}
    verdict_file = ROOT / "docs" / f"julgamento_{name}_veredictos.yaml"
    verdicts = (yaml.safe_load(verdict_file.read_text(encoding="utf-8")) or {}) if historical else {}
    res = classify(conds, verdicts, historical=historical)
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
