"""Monta a folha de julgamento humano de um conjunto medido (sem LLM, sem custo).

  python -m eval.judgment_sheet novo_a v4=v4_a v5_v1=v5_l1_1,v5_l1_2,... v5_v2=v5_l2 v7=v7_a

Para cada pergunta em que ALGUMA condição não foi `match` automático (diverge, respondeu o que devia recusar, ou abstenção de pergunta respondível),
mostra a pergunta, a referência (oráculo), o que cada condição respondeu e as premissas de limpeza. Grava `docs/JULGAMENTO_<set>.md` e um modelo de vereditos
`docs/julgamento_<set>_veredictos.yaml` para preencher: `pipeline_error | oracle_error | cleaning_difference | ok`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "eval" / "reports"
FLAG = {"diverge", "answered_unanswerable", "abstained"}


def _fmt(rows, n=4) -> str:
    if not rows:
        return "—"
    shown = "; ".join("(" + ", ".join(str(round(v, 3)) if isinstance(v, float) else str(v) for v in r) + ")" for r in rows[:n])
    return shown + (f" … +{len(rows) - n} linhas" if len(rows) > n else "")


def main(argv: list[str]) -> int:
    name, conds = argv[0], dict(a.split("=", 1) for a in argv[1:])
    data: dict[str, dict[str, dict]] = {}
    for cond, files in conds.items():
        rows = []
        for f in files.split(","):
            rows += json.loads((REPORTS / f"independent_run_{name}_{f}.json").read_text(encoding="utf-8"))["rows"]
        data[cond] = {r["id"]: r for r in rows}
    ids = sorted({i for d in data.values() for i, r in d.items() if r["auto"] in FLAG})
    first = next(iter(data.values()))
    out = [f"# Julgamento humano: conjunto `{name}`", "",
           f"{len(ids)} perguntas em que alguma condição não bateu automaticamente com a referência. Condições: {', '.join(conds)}.",
           "`diverge` não é erro: pode ser erro do sistema, erro do oráculo ou diferença de limpeza declarada. Dê um veredito por pergunta "
           "(o mesmo vale para todas as condições que deram o mesmo valor) no arquivo de vereditos.", ""]
    template = {}
    for i in ids:
        q = first[i]
        out += [f"## {i} · {q['category']} · esperado `{q['expected_behavior']}`", "", f"**Pergunta:** {q['question']}", ""]
        if q["expected_behavior"] == "answerable":
            out += [f"**Referência (oráculo):** {_fmt(q.get('oracle_rows'))}", "", f"**Premissas do oráculo:** {q.get('assumptions') or '—'}", ""]
        out += ["| condição | status | automático | resposta do sistema (linhas) |", "|---|---|---|---|"]
        for cond, d in data.items():
            r = d[i]
            out.append(f"| {cond} | {r['status']} | {r['auto'] or '—'} | {_fmt(r.get('pipeline_rows'))} |")
        notes = {r["auto_note"] for d in data.values() for r in [d[i]] if r["auto_note"] and r["auto"] == "diverge"}
        if notes:
            out += ["", "Nota automática: " + " / ".join(sorted(notes))[:300]]
        out.append("")
        template[i] = {"verdict": "", "note": ""}
    (ROOT / "docs" / f"JULGAMENTO_{name}.md").write_text("\n".join(out), encoding="utf-8")
    import yaml
    (ROOT / "docs" / f"julgamento_{name}_veredictos.yaml").write_text(
        "# verdict: pipeline_error | oracle_error | cleaning_difference | ok  (um por pergunta)\n" + yaml.safe_dump(template, allow_unicode=True), encoding="utf-8")
    print(f"{len(ids)} perguntas -> docs/JULGAMENTO_{name}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
