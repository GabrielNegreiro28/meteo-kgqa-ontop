"""Interpretação de referência (escrita à mão) das perguntas respondíveis que a suíte de segurança ainda não cobria.

Serve de CONTROLE: antes de gastar com o LLM, toda regra nova de validação é conferida contra interpretações corretas;
se barrar uma delas, a regra tem falso positivo. Junto com safety_experiment.CASES cobre as perguntas respondíveis das
suítes sintética e held-out. Perguntas a recusar/esclarecer (D06, D07, T13–T15, H09, H10) não têm interpretação.
"""
from __future__ import annotations

from eval.safety_experiment import CASES
from pipeline.validators import PipelineInterpretation

A, B, C = ("Serra Azul", "st:EST-A"), ("Vale Verde", "st:EST-B"), ("Litoral Sul", "st:EST-C")
P = lambda a, b: {"start": a, "end": b, "tz": "-03:00", "inclusive_end": True}


def _i(prop, agg=None, ents=(), filters=(), period=None, kind="observation", instant=None):
    return PipelineInterpretation(properties=[f"met:{prop}"], aggregation=agg, filters=list(filters), period=period,
                                  entities=[{"text": t, "iri": i} for t, i in ents], record_kind=kind, instant=instant)


EXTRA = {
    "D01": _i("AirTemperature"),
    "D02": _i("RelativeHumidity"),
    "D08": _i("AirTemperature", filters=[{"op": ">", "value": 40}]),
    "T01": _i("AirTemperature", "count"),
    "T02": _i("AirTemperature", filters=[{"op": ">=", "value": 30}]),
    "T05": _i("Precipitation"),
    "T09": _i("AirTemperature", ents=[B], instant="2026-03-05T12:00:00-03:00"),
    "T10": _i("AirTemperature", ents=[A], kind="forecast", instant="2026-03-09T12:00:00-03:00"),
    "T12": _i("Precipitation", "sum", [A, B]),
    "T16": _i("AirTemperature", "max", [A]),
    "H01": _i("AirTemperature", "max", [B], period=P("2026-03-02", "2026-03-04")),
    "H02": _i("Precipitation", "sum", [A], period=P("2026-03-05", "2026-03-06")),
    "H03": _i("RelativeHumidity", "avg", [A], period=P("2026-03-03", "2026-03-03")),
    "H04": _i("AirTemperature", "count", [C]),
    "H05": _i("Precipitation", "max"),
    "H06": _i("AirTemperature", filters=[{"op": ">", "value": 32}]),
    "H07": _i("AirTemperature", ents=[A], kind="forecast"),
    "H08": _i("Precipitation", "sum", [C], period=P("2026-03-07", "2026-03-07")),
    # conjunto "fresh" (G07-G09 são recusas: sem interpretação de referência)
    "G01": _i("RelativeHumidity", "min", [B], period=P("2026-03-03", "2026-03-05")),
    "G02": _i("Precipitation", "sum", period=P("2026-03-02", "2026-03-08")),
    "G03": _i("RelativeHumidity", ents=[A], instant="2026-03-04T06:00:00-03:00"),
    "G04": _i("AirTemperature", "avg", [C], period=P("2026-03-12", "2026-03-12")),
    "G05": _i("RelativeHumidity", "count", [B]),
    "G06": _i("RelativeHumidity", filters=[{"op": ">", "value": 80}]),
    "G10": _i("AirTemperature", "min"),
}


def all_reference_interpretations() -> dict[str, PipelineInterpretation]:
    return {**{k: v[0] for k, v in CASES.items()}, **EXTRA}
