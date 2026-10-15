"""Oráculo INDEPENDENTE: calcula as respostas esperadas em Python puro a partir do CSV bruto.

Não usa rdflib, SPARQL, nem a ontologia. Assim, uma consulta de referência errada (ou um bug
do motor SPARQL, ou da conversão CSV->RDF) aparece como divergência.
Limitação: CSV e grafo saem do mesmo gerador; o oráculo NÃO detecta erro no próprio gerador.
Valores-chave também estão conferidos à mão em tests/test_oracle_handchecked.py.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TZ = timezone(timedelta(hours=-3))
NAMES = {"Estação Serra Azul": "EST-A", "Estação Vale Verde": "EST-B", "Estação Litoral Sul": "EST-C"}


def load_obs() -> list[dict]:
    with open(ROOT / "data" / "observations.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["value"] = Decimal(r["value"])
        r["start"] = datetime.fromisoformat(r["start"])
        r["end"] = datetime.fromisoformat(r["end"])
    return rows


def load_fc() -> list[dict]:
    with open(ROOT / "data" / "forecasts.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["value"] = Decimal(r["value"])
        r["valid_time"] = datetime.fromisoformat(r["valid_time"])
        r["issued_at"] = datetime.fromisoformat(r["issued_at"])
    return rows


def day(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=TZ)


def avg(vals: list[Decimal]) -> Decimal | None:
    return (sum(vals) / len(vals)) if vals else None


def q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def sel(rows, prop=None, station=None, kind=None):
    return [r for r in rows if (prop is None or r["property"] == prop)
            and (station is None or r["station"] == station) and (kind is None or r["kind"] == kind)]


# Cada função devolve lista de tuplas na ordem de `compare.columns` da pergunta.
def D01(o, f):
    return [(s,) for s in sorted({r["station"] for r in sel(o, "AirTemperature")})]

def D02(o, f):
    return [(s,) for s in sorted({r["station"] for r in sel(o, "RelativeHumidity")})]

def D03(o, f):
    return [(r["obs_id"], r["value"]) for r in sel(o, "AirTemperature") if r["value"] > 30]

def D04(o, f):
    a, b = day(2026, 3, 3), day(2026, 3, 6)
    g = defaultdict(list)
    for r in sel(o, "AirTemperature"):
        if a <= r["start"] < b:
            g[r["station"]].append(r["value"])
    return [(s, avg(v), len(v)) for s, v in sorted(g.items())]

def D05(o, f):
    a, b = day(2026, 3, 4), day(2026, 3, 5)
    v = [r["value"] for r in sel(o, "Precipitation", "EST-B") if r["start"] >= a and r["end"] <= b]
    return [(sum(v) if v else None, len(v))]

def D08(o, f):
    return [(r["obs_id"], r["value"]) for r in sel(o, "AirTemperature") if r["value"] > 40]

def T01(o, f):
    g = defaultdict(int)
    for r in sel(o, "AirTemperature"):
        g[r["station"]] += 1
    return sorted(g.items())

def T02(o, f):
    return [(r["obs_id"], r["value"]) for r in sel(o, "AirTemperature") if r["value"] >= 30]

def T03(o, f):
    a, b = day(2026, 3, 2), day(2026, 3, 9)
    rows = [r for r in sel(o, "AirTemperature") if a <= r["start"] < b]
    m = max(r["value"] for r in rows)
    return [(r["station"], r["value"], r["start"]) for r in rows if r["value"] == m]

def T04(o, f):
    v = [r["value"] for r in sel(o, "RelativeHumidity", "EST-A")]
    return [(min(v) if v else None, len(v))]

def T05(o, f):
    rows = sorted(sel(o, "Precipitation"), key=lambda r: r["value"], reverse=True)
    return [(r["obs_id"], r["value"]) for r in rows[:3]]

def T06(o, f):
    a, b = day(2026, 3, 2), day(2026, 3, 9)
    g = defaultdict(list)
    for r in sel(o, "Precipitation"):
        if r["start"] >= a and r["end"] <= b:
            g[r["station"]].append(r["value"])
    return [(s, sum(v), len(v)) for s, v in sorted(g.items())]

def T07(o, f):
    g = defaultdict(list)
    for r in sel(o, "AirTemperature", "EST-C"):
        g[r["start"].astimezone(TZ).date().isoformat()].append(r["value"])
    return [(d,) for d, v in sorted(g.items()) if avg(v) > 28]

def T08(o, f):
    return [(len(sel(o, "RelativeHumidity", "EST-C")),)]

def T09(o, f):
    t = datetime(2026, 3, 5, 12, tzinfo=TZ)
    return [(r["obs_id"], r["value"]) for r in sel(o, "AirTemperature", "EST-B") if r["start"] == t]

def T10(o, f):
    t = datetime(2026, 3, 9, 12, tzinfo=TZ)
    return [(r["forecast_id"], r["value"], r["issued_at"]) for r in f
            if r["station"] == "EST-A" and r["property"] == "AirTemperature" and r["valid_time"] == t]

def T11(o, f):
    a, b = day(2026, 3, 2), day(2026, 3, 9)
    v = [r["value"] for r in sel(o, "AirTemperature", "EST-B") if a <= r["start"] < b]
    return [(avg(v), len(v))]

def T12(o, f):
    tot = {s: sum(r["value"] for r in sel(o, "Precipitation", s)) for s in ("EST-A", "EST-B")}
    return sorted(tot.items(), key=lambda kv: kv[1], reverse=True)

def T16(o, f):
    g = defaultdict(list)
    for r in sel(o, "AirTemperature", "EST-A"):
        g[r["start"].astimezone(TZ).date().isoformat()].append(r["value"])
    return [(d, max(v)) for d, v in sorted(g.items())]


def expected(qid: str) -> list[tuple] | None:
    fn = globals().get(qid)
    return fn(load_obs(), load_fc()) if fn else None
