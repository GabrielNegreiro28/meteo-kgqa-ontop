"""Catálogo de grandezas: a ÚNICA tabela de grandezas, unidades, faixas físicas e origem dos dados (plano, D6).

Gerado da ontologia (`met.ttl` + `met-structure.ttl`): cada grandeza declara a unidade canônica (met:canonicalUnit), a classe de observação
(met:observedAs), as agregações (met:allowsAggregation) e, na camada de dados, a tabela e a coluna de origem, o arquivo da fonte, o tipo do
valor, a faixa física e o sensor virtual. Cada unidade declara símbolo, dimensão e, quando não é a base, o fator para a unidade base.

Quem consome (nenhum deles mantém tabela própria; `tests/test_catalog.py` confere):
  ingest/transform.py (faixas)  ·  ingest/export_pg.py, ingest/finalize_pg.py, ingest/constraints.py (tabelas)
  mapping/build_mapping.py (mapeamento)  ·  ontology/shapes.ttl (faixas e unidades do SHACL, gerados por `render_shapes`)
  pipeline/vocab.py (conversão de unidades)  ·  metqa/knowledge/catalog.py (dimensões e símbolos)

  python -m ontology.catalog            # regera ontology/shapes.ttl (um teste confere que está em dia)
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from rdflib import Graph, Namespace

HERE = Path(__file__).resolve().parent
MET = Namespace("https://example.org/kgqa-met/ontology#")
UNIT = "http://qudt.org/vocab/unit/"
XSD = "http://www.w3.org/2001/XMLSchema#"


@dataclass(frozen=True)
class Unit:
    iri: str
    name: str                       # DEG_C, KiloM...
    symbol: str
    dimension: str
    base: str                       # nome da unidade base da dimensão (KiloM -> M); a própria, se é base
    factor: Decimal                 # valor na base = valor * factor


@dataclass(frozen=True)
class Quantity:
    iri: str
    name: str                       # AirTemperature
    unit: str                       # nome da unidade canônica (DEG_C); "" para a nebulosidade categórica
    observed_as: str                # InstantaneousObservation | AccumulatedObservation | CloudLayerObservation
    table: str                      # tabela no PostgreSQL (obs_air_temp)
    column: str                     # coluna do valor na tabela
    sensor: str                     # sensor virtual / nome no IRI da observação (air_temp)
    source_file: str                # arquivo da fonte (temperatura.csv)
    datatype: str                   # decimal | integer ("" sem valor numérico)
    low: Decimal | None             # faixa física na unidade canônica (inclusiva); fora dela, a ingestão põe em quarentena
    high: Decimal | None
    provisional: bool = False       # grandeza proposta, à espera da equipe de ontologia

    @property
    def accumulated(self) -> bool:
        return self.observed_as == "AccumulatedObservation"


def _graph() -> Graph:
    g = Graph()
    for f in ("met.ttl", "met-structure.ttl"):
        g.parse(HERE / f, format="turtle")
    return g


def _local(iri) -> str:
    return str(iri).rsplit("#", 1)[-1].rsplit("/", 1)[-1] if iri is not None else ""


@lru_cache(maxsize=1)
def load() -> tuple[dict[str, Quantity], dict[str, Unit]]:
    g = _graph()
    units = {}
    for u in set(g.subjects(MET.dimension, None)):
        base = g.value(u, MET.baseUnit)
        units[_local(u)] = Unit(str(u), _local(u), str(g.value(u, MET.symbol) or ""), str(g.value(u, MET.dimension)),
                                _local(base) if base else _local(u), Decimal(str(g.value(u, MET.multiplier) or 1)))
    quantities = {}
    for q in sorted(set(g.subjects(MET.sourceTable, None)), key=str):
        dec = lambda p: Decimal(str(g.value(q, p))) if g.value(q, p) is not None else None
        quantities[_local(q)] = Quantity(
            iri=str(q), name=_local(q), unit=_local(g.value(q, MET.canonicalUnit)), observed_as=_local(g.value(q, MET.observedAs)),
            table=str(g.value(q, MET.sourceTable)), column=str(g.value(q, MET.sourceColumn) or "value"),
            sensor=str(g.value(q, MET.sensorName)), source_file=str(g.value(q, MET.sourceFileName)),
            datatype=_local(g.value(q, MET.valueDatatype)), low=dec(MET.physicalMin), high=dec(MET.physicalMax),
            provisional=bool(g.value(q, MET.provisional)))
    return quantities, units


def quantities() -> dict[str, Quantity]:
    return load()[0]


def units() -> dict[str, Unit]:
    return load()[1]


def quantity_by_sensor(sensor: str) -> Quantity:
    return next(q for q in quantities().values() if q.sensor == sensor)


def tables() -> list[str]:
    """Tabelas de observação, na ordem do catálogo, sem repetir (as camadas de nuvem dão duas grandezas numa tabela)."""
    return list(dict.fromkeys(q.table for q in quantities().values()))


def convert(value, from_unit: str | None, to_unit: str | None) -> Decimal | None:
    """Valor de uma unidade para outra da MESMA dimensão; None se a conversão não é conhecida (quem chama recusa, não chuta)."""
    us = units()
    a, b = (from_unit or to_unit or "").rsplit(":", 1)[-1].rsplit("/", 1)[-1], (to_unit or "").rsplit(":", 1)[-1].rsplit("/", 1)[-1]
    if a == b:
        return Decimal(str(value))
    ua, ub = us.get(a), us.get(b)
    if not ua or not ub or ua.dimension != ub.dimension or ua.base != ub.base:
        return None
    return Decimal(str(value)) * ua.factor / ub.factor


# ---------------------------------------------------------------------------------------------------------------------------------
# SHACL gerado: as unidades que o mapeamento emite e a faixa física de cada grandeza (as mesmas da ingestão, por construção)
# ---------------------------------------------------------------------------------------------------------------------------------
SHAPES_HEAD = (HERE / "shapes.head.ttl")


def render_shapes() -> str:
    qs = quantities()
    emitted = sorted({q.unit for q in qs.values() if q.unit})
    rows = " ||\n".join(f"              (?p = <{q.iri}> && (?v < {q.low} || ?v > {q.high}))" for q in qs.values() if q.low is not None)
    return SHAPES_HEAD.read_text(encoding="utf-8").replace("{UNITS}", " ".join(f"unit:{u}" for u in emitted)).replace("{RANGES}", rows)


def main() -> int:
    (HERE / "shapes.ttl").write_text(render_shapes(), encoding="utf-8")
    print("ontology/shapes.ttl regerado do catálogo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
