"""Equivalência medida entre as duas formas de dizer um período no grafo REAL (Ontop):

  A) por dia local:           ?o met:localDate ?d . FILTER(?d >= D1 && ?d <= D2)
  B) por data-e-hora (UTC−3): intervalo INTEIRO dentro do período (acumulados) ou instante dentro do período (instantâneas)

Para cada (estação, grandeza, período) compara SUM, COUNT, MIN e MAX das duas formas. Se QUALQUER divergência aparecer, a regra que
aceita met:localDate (D-37) não vale e a recomendação passa a ser manter só os intervalos.

    python -m eval.equivalencia_localdate            # precisa do Ontop no ar; grava docs/EQUIVALENCIA_LOCALDATE.md
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from metqa.execution.store import PREFIXES, OntopBackend
from metqa.knowledge.index import OntologyIndex

ROOT = Path(__file__).resolve().parent.parent
PROPS = {"met:Precipitation": "accumulated", "met:AirTemperature": "instant", "met:PressureQNH": "instant", "met:WindSpeed": "instant"}
# bordas do que pode dar errado: limites dos dados, dia bissexto, artefato de horário de verão (P-16), virada de ano, mês e ano
PERIODS = [
    ("primeiro dia dos dados", "2016-01-01", "2016-01-01"),
    ("último dia dos dados", "2025-12-31", "2025-12-31"),
    ("dia bissexto", "2020-02-29", "2020-02-29"),
    ("início do horário de verão 2016 (P-16)", "2016-10-16", "2016-10-16"),
    ("início do horário de verão 2018 (P-16)", "2018-11-04", "2018-11-04"),
    ("virada de ano", "2018-12-31", "2019-01-01"),
    ("um mês", "2019-03-01", "2019-03-31"),
    ("um ano", "2019-01-01", "2019-12-31"),
]


def forms(prop: str, kind: str, station: str, a: str, b: str) -> tuple[str, str]:
    """(forma por dia local, forma por data-e-hora) da MESMA pergunta, projetando SUM, COUNT, MIN e MAX."""
    head = "SELECT (SUM(?v) AS ?sum) (COUNT(?v) AS ?n) (MIN(?v) AS ?min) (MAX(?v) AS ?max) WHERE {"
    base = (f" st:{station} sosa:hosts ?s . ?o sosa:madeBySensor ?s ; sosa:observedProperty {prop} ; "
            "sosa:hasResult/qudt:numericValue ?v .")
    lo = f"{a}T00:00:00-03:00"
    hi = (date.fromisoformat(b) + timedelta(days=1)).isoformat() + "T00:00:00-03:00"
    day = f'{head}{base} ?o met:localDate ?d . FILTER(?d >= "{a}"^^xsd:date && ?d <= "{b}"^^xsd:date) }}'
    if kind == "accumulated":
        clock = (f'{head}{base} ?o sosa:phenomenonTime ?iv . ?iv time:hasBeginning/time:inXSDDateTime ?ini ; time:hasEnd/time:inXSDDateTime ?fim . '
                 f'FILTER(?ini >= "{lo}"^^xsd:dateTime && ?fim <= "{hi}"^^xsd:dateTime) }}')
    else:
        clock = (f'{head}{base} ?o sosa:phenomenonTime/time:inXSDDateTime ?t . '
                 f'FILTER(?t >= "{lo}"^^xsd:dateTime && ?t < "{hi}"^^xsd:dateTime) }}')
    return day, clock


def run(backend: OntopBackend, query: str) -> tuple[dict | None, float]:
    t0 = time.perf_counter()
    r = backend.select(PREFIXES + query, timeout_s=120)
    dt = time.perf_counter() - t0
    if not r.ok:
        return {"erro": f"{r.error_kind}: {str(r.error)[:120]}"}, dt
    row = r.results["results"]["bindings"][0]
    return {k: (str(Decimal(v["value"])) if k != "n" and "value" in v else v.get("value")) for k, v in row.items()}, dt


def main() -> int:
    backend = OntopBackend()
    stations = sorted(s.rsplit("/", 1)[-1] for s in OntologyIndex.from_ontop(backend).entities)
    sample = stations[::22][:8]                 # 8 estações espalhadas pela lista ordenada, determinístico
    rows, bad = [], []
    t_all = time.perf_counter()
    for st in sample:
        for prop, kind in PROPS.items():
            for label, a, b in PERIODS:
                q_day, q_clock = forms(prop, kind, st, a, b)
                r_day, t_day = run(backend, q_day)
                r_clock, t_clock = run(backend, q_clock)
                same = r_day == r_clock and "erro" not in r_day
                rows.append({"estacao": st, "grandeza": prop, "periodo": label, "n_dia": r_day.get("n"), "n_relogio": r_clock.get("n"),
                             "igual": same, "t_dia": round(t_day, 2), "t_relogio": round(t_clock, 2)})
                if not same:
                    bad.append({"estacao": st, "grandeza": prop, "periodo": label, "dia_local": r_day, "relogio": r_clock})
        print(f"{st}: {sum(r['igual'] for r in rows if r['estacao'] == st)}/{sum(1 for r in rows if r['estacao'] == st)} iguais", flush=True)
    total_s = time.perf_counter() - t_all
    empty = sum(1 for r in rows if r["n_dia"] in ("0", None))
    avg = lambda k: sum(r[k] for r in rows) / len(rows)
    (ROOT / "eval" / "reports").mkdir(exist_ok=True)
    (ROOT / "eval" / "reports" / "equivalencia_localdate.json").write_text(json.dumps({"rows": rows, "divergencias": bad}, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# Equivalência `met:localDate` × data-e-hora no grafo real", "",
          "Gerado por `python -m eval.equivalencia_localdate`. Compara SUM, COUNT, MIN e MAX das duas formas de dizer o mesmo período.", "",
          f"- Estações: {', '.join(sample)} (1 a cada 22 da lista ordenada, de {len(stations)})",
          f"- Grandezas: {', '.join(PROPS)}; períodos: {len(PERIODS)} (bordas, ver tabela)",
          f"- Comparações: **{len(rows)}**; **iguais: {sum(r['igual'] for r in rows)}**; divergentes: **{len(bad)}**",
          f"- Comparações em que ambas as formas devolveram 0 linhas: {empty} (igualdade vazia não prova nada; foram contadas à parte)",
          f"- Tempo médio por consulta: dia local {avg('t_dia'):.2f} s, data-e-hora {avg('t_relogio'):.2f} s; total {total_s/60:.1f} min", ""]
    if bad:
        md += ["## Divergências", "", "| estação | grandeza | período | dia local | data-e-hora |", "|---|---|---|---|---|"]
        md += [f"| {b['estacao']} | {b['grandeza']} | {b['periodo']} | `{b['dia_local']}` | `{b['relogio']}` |" for b in bad]
    else:
        md += ["## Divergências", "", "Nenhuma."]
    md += ["", "## Por período", "", "| período | comparações | iguais | linhas (n) mínimo–máximo na forma por dia |", "|---|---:|---:|---|"]
    for label, _, _ in PERIODS:
        sel = [r for r in rows if r["periodo"] == label]
        ns = [int(r["n_dia"]) for r in sel if r["n_dia"] is not None]
        md.append(f"| {label} | {len(sel)} | {sum(r['igual'] for r in sel)} | {min(ns)}–{max(ns)} |")
    (ROOT / "docs" / "EQUIVALENCIA_LOCALDATE.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\n{sum(r['igual'] for r in rows)}/{len(rows)} iguais; {len(bad)} divergentes; {empty} vazias; {total_s/60:.1f} min")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
