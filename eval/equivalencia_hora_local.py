"""Equivalência medida no grafo real: hora e dia da semana locais declarados no grafo (met:localHour, met:localWeekday) contra a forma
anterior do compilador (hora UTC convertida na consulta e lista de datas locais da janela). Sem LLM.

  python -m eval.equivalencia_hora_local          # grava eval/reports/equivalencia_hora_local.json
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

from kgqa.store import PREFIXES, OntopBackend
from metqa.knowledge import DomainCatalog
from metqa.planning.compiler import compile_query
from metqa.understanding import parse
from tests.test_metqa import nir

ROOT = Path(__file__).resolve().parent.parent
NIGHT = list(range(18, 24)) + list(range(0, 6))
CASES = [  # grandeza, estação, agregação, início, fim, horas, dias da semana
    ("met:WindSpeed", "SBRB", "avg", "2024-01-01", "2024-12-31", None, [0, 1, 2, 3, 4]),        # E149 do novo_b
    ("met:WindSpeed", "SBRB", "avg", "2024-01-01", "2024-06-30", None, [0, 1, 2, 3, 4]),        # a forma antiga cabe no limite
    ("met:WindSpeed", "SBNT", "avg", "2024-01-01", "2024-12-31", None, [5, 6]),
    ("met:AirTemperature", "SBBR", "avg", "2016-01-01", "2016-12-31", None, [5, 6]),            # E143
    ("met:Precipitation", "SBBE", "sum", "2019-01-01", "2019-12-31", list(range(0, 6)), None),
    ("met:PressureQNH", "SBEG", "min", "2017-05-01", "2017-05-31", list(range(0, 6)), None),    # E144
    ("met:RelativeHumidity", "SBMA", "avg", "2018-08-01", "2018-08-31", list(range(12, 18)), None),
    ("met:PrevailingVisibility", "SBME", "min", "2019-07-01", "2019-07-31", NIGHT, None),
    ("met:RelativeHumidity", "SBNF", "avg", "2020-07-01", "2020-07-31", NIGHT, None),
    ("met:DewPointTemperature", "SBVC", "min", "2025-09-01", "2025-09-30", list(range(6, 12)), None),
    ("met:AirTemperature", "SBGL", "max", "2023-01-01", "2023-12-31", list(range(12, 18)), [5, 6]),
]


def old_form(sparql: str, start: date, end: date) -> str:
    """A consulta como o compilador a montava antes: hora UTC = (hora local + 3) mod 24; dia da semana = lista de datas."""
    def hours(m):
        utc = sorted({(int(h) + 3) % 24 for h in m.group(1).split(", ")})
        return f"?obs sosa:resultTime ?t .\n  FILTER(HOURS(?t) IN ({', '.join(map(str, utc))}))"

    def weekdays(m):
        wd = {int(x) for x in m.group(1).split(", ")}
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        return "FILTER(?d IN (" + ", ".join(f'"{x.isoformat()}"^^xsd:date' for x in days if x.weekday() in wd) + "))"
    sparql = re.sub(r"\?obs met:localHour \?h \.\n  FILTER\(\?h IN \(([\d, ]+)\)\)", hours, sparql)
    return re.sub(r"\?obs met:localWeekday \?wd \.\n  FILTER\(\?wd IN \(([\d, ]+)\)\)", weekdays, sparql)


def main() -> int:
    source = OntopBackend()
    catalog = DomainCatalog.from_ontop(source)
    out = []
    for prop, st, agg, a, b, hours, wd in CASES:
        ir = nir(prop, [f"st:{st}"], agg, a, b, hours=hours, weekdays=wd)
        cq = parse(ir).parts[0][1]
        new = compile_query(cq, catalog).sparql
        old = old_form(new, date.fromisoformat(a), date.fromisoformat(b))
        row = {"case": f"{st} {prop} {agg} {a}..{b} horas={hours} dias={wd}", "old_chars": len(old), "new_chars": len(new)}
        for name, q in (("new", new), ("old", old)):
            t0 = time.time()
            r = source.select(PREFIXES + q, timeout_s=300, max_rows=10)
            row[name] = r.results["results"]["bindings"] if r.ok else f"erro: {r.error}"
            row[f"{name}_s"] = round(time.time() - t0, 1)
        row["equal"] = isinstance(row["new"], list) and row["new"] == row["old"]
        out.append(row)
        print(row["equal"], row["case"], row["new_s"], row["old_s"], row["old_chars"], row["new_chars"])
    (ROOT / "eval" / "reports" / "equivalencia_hora_local.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{sum(r['equal'] for r in out)}/{len(out)} iguais")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
