"""Oráculo do conjunto "fresh": Python puro sobre o CSV, independente de SPARQL e da ontologia."""
from __future__ import annotations

from collections import defaultdict

from eval.oracle import day, load_obs, sel


def G01():
    v = [r["value"] for r in sel(load_obs(), "RelativeHumidity", "EST-B") if day(2026, 3, 3) <= r["start"] < day(2026, 3, 6)]
    return [(min(v), len(v))]


def G02():
    a, b = day(2026, 3, 2), day(2026, 3, 9)
    v = [r["value"] for r in sel(load_obs(), "Precipitation") if r["start"] >= a and r["end"] <= b]
    return [(sum(v), len(v))]


def G03():
    t = day(2026, 3, 4).replace(hour=6)
    return [(r["value"],) for r in sel(load_obs(), "RelativeHumidity", "EST-A") if r["start"] == t]


def G04():
    v = [r for r in sel(load_obs(), "AirTemperature", "EST-C") if day(2026, 3, 12) <= r["start"] < day(2026, 3, 13)]
    return [(len(v),)]


def G05():
    return [(len(sel(load_obs(), "RelativeHumidity", "EST-B")),)]


def G06():
    return [(s,) for s in sorted({r["station"] for r in sel(load_obs(), "RelativeHumidity") if r["value"] > 80})]


def G10():
    g = defaultdict(list)
    for r in sel(load_obs(), "AirTemperature"):
        g[r["station"]].append(r["value"])
    return [(s, min(v), len(v)) for s, v in sorted(g.items())]


def expected(qid: str):
    fn = globals().get(qid)
    return fn() if fn else None
