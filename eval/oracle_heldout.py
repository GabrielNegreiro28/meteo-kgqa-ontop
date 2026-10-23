"""Oráculo do conjunto held-out: Python puro sobre o CSV, independente de SPARQL e da ontologia."""
from __future__ import annotations

from eval.oracle import day, load_fc, load_obs, sel


def H01():
    v = [r["value"] for r in sel(load_obs(), "AirTemperature", "EST-B") if day(2026, 3, 2) <= r["start"] < day(2026, 3, 5)]
    return [(max(v), len(v))]


def H02():
    a, b = day(2026, 3, 5), day(2026, 3, 7)
    v = [r["value"] for r in sel(load_obs(), "Precipitation", "EST-A") if r["start"] >= a and r["end"] <= b]
    return [(sum(v), len(v))]


def H03():
    v = [r["value"] for r in sel(load_obs(), "RelativeHumidity", "EST-A") if day(2026, 3, 3) <= r["start"] < day(2026, 3, 4)]
    return [(sum(v) / len(v), len(v))]


def H04():
    return [(len(sel(load_obs(), "AirTemperature", "EST-C")),)]


def H05():
    v = [r["value"] for r in sel(load_obs(), "Precipitation")]
    return [(max(v), len(v))]


def H06():
    return [(s,) for s in sorted({r["station"] for r in sel(load_obs(), "AirTemperature") if r["value"] > 32})]


def H07():
    return [(f["issued_at"],) for f in load_fc() if f["station"] == "EST-A" and f["property"] == "AirTemperature"]


def H08():
    a, b = day(2026, 3, 7), day(2026, 3, 8)
    v = [r["value"] for r in sel(load_obs(), "Precipitation", "EST-C") if r["start"] >= a and r["end"] <= b]
    return [(sum(v), len(v))]


def expected(qid: str):
    fn = globals().get(qid)
    return fn() if fn else None
