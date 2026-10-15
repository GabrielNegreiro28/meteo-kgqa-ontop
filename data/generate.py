"""Gerador reproduzível do grafo meteorológico SINTÉTICO.

Saídas (em data/):
  observations.csv  – registros brutos (fonte para o oráculo independente)
  forecasts.csv     – previsões (não são observações)
  synthetic.nt      – grafo RDF canônico (N-Triples ordenado => byte a byte reprodutível)
  synthetic.ttl     – mesmo grafo em Turtle, para leitura humana

Convenções (ver DECISOES.md):
  * Fuso: todos os instantes em hora local fixa UTC-03:00 (offset explícito).
  * Temperatura do ar: °C, instantânea.  Umidade relativa: %, instantânea.
  * Precipitação: mm acumulados no intervalo [h, h+6h).
  * Ausência de registro = dado ausente (NÃO é zero). Chuva zero é registrada como 0.0.

Uso:  python data/generate.py
"""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef

SEED = 20260302
TZ = timezone(timedelta(hours=-3))
DAYS = [datetime(2026, 3, d, tzinfo=TZ) for d in range(2, 9)]  # 02..08/03/2026 (7 dias)
HOURS = [0, 6, 12, 18]
OUT = Path(__file__).resolve().parent

MET = Namespace("https://example.org/kgqa-met/ontology#")
D = Namespace("https://example.org/kgqa-met/data/")
SOSA = Namespace("http://www.w3.org/ns/sosa/")
TIME = Namespace("http://www.w3.org/2006/time#")
QUDT = Namespace("http://qudt.org/schema/qudt/")
UNIT = Namespace("http://qudt.org/vocab/unit/")
PROV = Namespace("http://www.w3.org/ns/prov#")
DCT = Namespace("http://purl.org/dc/terms/")

STATIONS = {
    "EST-A": {"name": "Estação Serra Azul", "temp_base": 22.0, "rh_base": 75.0, "sensors": ["TEMP", "RH", "PREC"]},
    "EST-B": {"name": "Estação Vale Verde", "temp_base": 25.0, "rh_base": 65.0, "sensors": ["TEMP", "RH", "PREC"]},
    "EST-C": {"name": "Estação Litoral Sul", "temp_base": 27.0, "rh_base": None, "sensors": ["TEMP", "PREC"]},  # sem higrômetro
}
PROPS = {  # código -> (propriedade observável, unidade, tipo)
    "TEMP": ("AirTemperature", "DEG_C", "instant"),
    "RH": ("RelativeHumidity", "PERCENT", "instant"),
    "PREC": ("Precipitation", "MilliM", "interval"),
}
TEMP_DIURNAL = {0: -3.0, 6: -4.0, 12: 4.0, 18: 1.0}
RH_DIURNAL = {0: 10.0, 6: 15.0, 12: -15.0, 18: -5.0}

# Casos planejados (documentados; o oráculo NÃO depende destas listas, só do CSV).
OVERRIDES = {  # (estação, sensor, data-hora local) -> valor
    ("EST-A", "TEMP", "2026-03-04T12:00"): 30.0,   # limite exato: entra em ">= 30", não em "> 30"
    ("EST-C", "TEMP", "2026-03-06T12:00"): 34.6,   # máximo observado do período
    ("EST-B", "PREC", "2026-03-04T12:00"): 18.4,   # maior acumulado de 6 h
}
MISSING = {  # registros ausentes (sensor sem dado) – ausência ≠ zero
    ("EST-B", "TEMP", "2026-03-05T00:00"), ("EST-B", "TEMP", "2026-03-05T06:00"),
    ("EST-B", "TEMP", "2026-03-05T12:00"), ("EST-B", "TEMP", "2026-03-05T18:00"),
    ("EST-C", "PREC", "2026-03-07T18:00"),
}
FORECASTS = [  # previsão: valor maior que qualquer observação (armadilha para "maior temperatura registrada")
    {"id": "FC-EST-A-TEMP-20260309T1200", "station": "EST-A", "prop": "TEMP",
     "valid": "2026-03-09T12:00", "issued": "2026-03-08T18:00", "value": 35.0},
]


@dataclass
class Rec:
    obs_id: str
    station: str
    sensor: str
    prop: str
    kind: str
    start: str  # ISO local com offset
    end: str    # igual a start para instantâneas
    value: Decimal
    unit: str


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")  # ex.: 2026-03-02T00:00:00-03:00


def gen_records() -> list[Rec]:
    rng = random.Random(SEED)
    recs: list[Rec] = []
    for day in DAYS:
        for h in HOURS:
            t = day.replace(hour=h)
            key_t = t.strftime("%Y-%m-%dT%H:%M")
            for st, cfg in STATIONS.items():
                for sensor in cfg["sensors"]:
                    prop, unit, kind = PROPS[sensor]
                    # Sorteia SEMPRE, mesmo se ausente/sobrescrito, para não deslocar a sequência aleatória.
                    if sensor == "TEMP":
                        v = cfg["temp_base"] + TEMP_DIURNAL[h] + rng.uniform(-1.5, 1.5)
                    elif sensor == "RH":
                        v = min(100.0, max(0.0, cfg["rh_base"] + RH_DIURNAL[h] + rng.uniform(-5, 5)))
                    else:
                        rain = rng.random() < 0.25
                        amt = rng.uniform(0.2, 15.0)
                        v = amt if rain else 0.0
                    if (st, sensor, key_t) in MISSING:
                        continue
                    v = OVERRIDES.get((st, sensor, key_t), v)
                    value = Decimal(f"{v:.1f}")
                    end = t + timedelta(hours=6) if kind == "interval" else t
                    recs.append(Rec(
                        obs_id=f"{st}-{sensor}-{t.strftime('%Y%m%dT%H%M')}",
                        station=st, sensor=f"{st}-{sensor}", prop=prop, kind=kind,
                        start=iso(t), end=iso(end), value=value, unit=unit))
    return recs


def instant(g: Graph, dt_iso: str) -> URIRef:
    # D-07: time:inXSDDateTime (obsoleta na OWL-Time) com xsd:dateTime, porque o rdflib 7.6.0
    # compara xsd:dateTimeStamp de forma incorreta e silenciosa. Revisar ao trocar de backend.
    node = D[f"time/{dt_iso[:16].replace(':', '-')}"]
    g.add((node, RDF.type, TIME.Instant))
    g.add((node, TIME.inXSDDateTime, Literal(dt_iso, datatype=XSD.dateTime)))
    return node


def build_graph(recs: list[Rec]) -> Graph:
    g = Graph()
    for p, ns in [("met", MET), ("d", D), ("sosa", SOSA), ("time", TIME), ("qudt", QUDT),
                  ("unit", UNIT), ("prov", PROV), ("dct", DCT)]:
        g.bind(p, ns)

    ds = D["dataset/synthetic-v1"]
    g.add((ds, RDF.type, PROV.Entity))
    g.add((ds, MET.isSynthetic, Literal(True)))
    g.add((ds, DCT.title, Literal("Grafo meteorológico sintético (protótipo)", lang="pt")))
    g.add((ds, DCT.description, Literal(f"Dados fictícios gerados por data/generate.py, seed={SEED}.", lang="pt")))
    g.add((ds, PROV.generatedAtTime, Literal("2026-09-30T00:00:00-03:00", datatype=XSD.dateTime)))  # fixo: reprodutível

    for st, cfg in STATIONS.items():
        s = D[f"station/{st}"]
        site = D[f"site/{st}"]
        g.add((s, RDF.type, MET.WeatherStation))
        g.add((s, RDFS.label, Literal(cfg["name"], lang="pt")))
        g.add((s, MET.stationCode, Literal(st)))
        g.add((s, MET.isSynthetic, Literal(True)))
        g.add((s, PROV.wasDerivedFrom, ds))
        g.add((site, RDF.type, MET.Site))
        g.add((site, MET.siteOf, s))
        g.add((site, RDFS.label, Literal(f"Atmosfera junto à {cfg['name']}", lang="pt")))
        for sensor in cfg["sensors"]:
            prop = PROPS[sensor][0]
            sn = D[f"sensor/{st}-{sensor}"]
            g.add((sn, RDF.type, SOSA.Sensor))
            g.add((sn, RDFS.label, Literal(f"Sensor {sensor} da {cfg['name']}", lang="pt")))
            g.add((sn, SOSA.observes, MET[prop]))
            g.add((s, SOSA.hosts, sn))

    for r in recs:
        o = D[f"obs/{r.obs_id}"]
        res = D[f"result/{r.obs_id}"]
        g.add((o, RDF.type, MET.InstantaneousObservation if r.kind == "instant" else MET.AccumulatedObservation))
        g.add((o, SOSA.madeBySensor, D[f"sensor/{r.sensor}"]))
        g.add((o, SOSA.observedProperty, MET[r.prop]))
        g.add((o, SOSA.hasFeatureOfInterest, D[f"site/{r.station}"]))
        g.add((o, PROV.wasDerivedFrom, ds))
        if r.kind == "instant":
            g.add((o, SOSA.phenomenonTime, instant(g, r.start)))
        else:
            iv = D[f"time/interval/{r.start[:16].replace(':', '-')}_PT6H"]
            g.add((iv, RDF.type, TIME.Interval))
            g.add((iv, TIME.hasBeginning, instant(g, r.start)))
            g.add((iv, TIME.hasEnd, instant(g, r.end)))
            g.add((o, SOSA.phenomenonTime, iv))
        g.add((o, SOSA.resultTime, Literal(r.end, datatype=XSD.dateTime)))
        g.add((o, SOSA.hasResult, res))
        g.add((res, RDF.type, QUDT.QuantityValue))
        g.add((res, QUDT.numericValue, Literal(r.value, datatype=XSD.decimal)))
        g.add((res, QUDT.unit, UNIT[r.unit]))

    for f in FORECASTS:
        fc = D[f"forecast/{f['id']}"]
        res = D[f"result/{f['id']}"]
        prop, unit, _ = PROPS[f["prop"]]
        valid = datetime.fromisoformat(f["valid"]).replace(tzinfo=TZ)
        issued = datetime.fromisoformat(f["issued"]).replace(tzinfo=TZ)
        g.add((fc, RDF.type, MET.Forecast))
        g.add((fc, MET.forStation, D[f"station/{f['station']}"]))
        g.add((fc, MET.forecastedProperty, MET[prop]))
        g.add((fc, MET.validTime, instant(g, iso(valid))))
        g.add((fc, MET.issuedAt, Literal(iso(issued), datatype=XSD.dateTime)))
        g.add((fc, PROV.wasDerivedFrom, ds))
        g.add((fc, SOSA.hasResult, res))
        g.add((res, RDF.type, QUDT.QuantityValue))
        g.add((res, QUDT.numericValue, Literal(Decimal(f"{f['value']:.1f}"), datatype=XSD.decimal)))
        g.add((res, QUDT.unit, UNIT[unit]))
    return g


def main() -> None:
    recs = gen_records()
    with open(OUT / "observations.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["obs_id", "station", "station_name", "sensor", "property", "kind", "start", "end", "value", "unit"])
        for r in recs:
            w.writerow([r.obs_id, r.station, STATIONS[r.station]["name"], r.sensor, r.prop, r.kind,
                        r.start, r.end, str(r.value), r.unit])
    with open(OUT / "forecasts.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["forecast_id", "station", "property", "valid_time", "issued_at", "value", "unit"])
        for f in FORECASTS:
            prop, unit, _ = PROPS[f["prop"]]
            w.writerow([f["id"], f["station"], prop, f["valid"] + ":00-03:00", f["issued"] + ":00-03:00",
                        f"{f['value']:.1f}", unit])
    g = build_graph(recs)
    lines = sorted(l for l in g.serialize(format="nt").splitlines() if l.strip())
    (OUT / "synthetic.nt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    g.serialize(destination=str(OUT / "synthetic.ttl"), format="turtle")
    print(f"{len(recs)} observações, {len(FORECASTS)} previsão(ões), {len(g)} triplas -> {OUT}")


if __name__ == "__main__":
    main()
