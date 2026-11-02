"""Catálogo de Domínio: a ÚNICA fonte, dentro do MVP, de grandezas, unidades, agregações, atributos, estações e capacidades.

Gerado da ontologia (`ontology/met.ttl` + `met-structure.ttl`) e do perfil do grafo (Ontop: estações, cobertura, grandezas com dados),
pelo `pipeline/vocab.py::OntologyIndex` já existente. Os estágios do MVP perguntam ao catálogo e não mantêm tabelas próprias.

Faz também o papel do "catálogo de capacidades" do roteador (documento da arquitetura, §9) reduzido a UMA fonte: com um só banco não há o que
rotear, mas continua havendo abstenção honesta quando a grandeza não tem dados, o período está fora da cobertura ou a forma pedida não existe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from pipeline.validators import GROUP_DIMS, own_attributes
from pipeline.vocab import OntologyIndex, PropertyInfo, convert_filter_value, expand

ROOT = Path(__file__).resolve().parent.parent.parent
UNIT_NS = "http://qudt.org/vocab/unit/"
# dimensão física de cada unidade QUDT usada pelos dados e pelas perguntas: é o que confere uma condição contra a grandeza (análise
# dimensional sobre valores já normalizados, sem olhar a forma de escrever). Fonte única do MVP.
UNIT_DIMENSION = {"DEG_C": "temperature", "PERCENT": "ratio", "MilliM": "precipitation_depth", "HectoPA": "pressure", "KN": "speed",
                  "M": "length", "KiloM": "length", "DEG": "angle", "MIN": "time", "OKTA": "cover"}
# unidades em que o usuário pode DIZER um valor, sem met:symbol na ontologia (nenhuma grandeza as tem como canônica). Sai daqui quando o
# catálogo virar a fonte única das unidades (plano, D6).
EXTRA_SYMBOLS = {"KiloM": "km", "OKTA": "oitavos"}
GROUP_NAMES ={"station": "estação", "year": "ano", "month": "mês", "day": "dia", "value": "valor medido"}


@dataclass(frozen=True)
class Measure:
    iri: str
    label: str
    labels: tuple[str, ...]
    unit: str | None                  # IRI QUDT
    symbol: str                       # "°C", "mm"...
    dimension: str | None             # temperature, precipitation_depth... (mesma grade do leitor de unidades)
    aggregations: frozenset[str]
    accumulated: bool
    caveat: str
    attributes: tuple[str, ...]       # atributos próprios (ex.: met:runwayDesignator)
    has_data: bool

    @property
    def short(self) -> str:
        return "met:" + self.iri.rsplit("#", 1)[-1]


class DomainCatalog:
    def __init__(self, index: OntologyIndex):
        self.index = index
        self.measures: dict[str, Measure] = {iri: self._measure(info) for iri, info in index.properties.items()}

    # ---------------- construção ----------------
    @classmethod
    def from_ontop(cls, backend) -> "DomainCatalog":
        return cls(OntologyIndex.from_ontop(backend))

    @classmethod
    def from_ontology(cls, **kw) -> "DomainCatalog":
        """Sem grafo real (testes, grafo sintético): ontologia + dados sintéticos."""
        return cls(OntologyIndex.load(**kw))

    def _measure(self, info: PropertyInfo) -> Measure:
        short_unit = info.unit.rsplit("/", 1)[-1] if info.unit else None
        return Measure(iri=info.iri, label=(info.labels or [info.iri.rsplit("#", 1)[-1]])[0], labels=tuple(info.labels), unit=info.unit,
                       symbol=self.index.unit_symbols.get(info.unit or "", ""), dimension=UNIT_DIMENSION.get(short_unit or ""),
                       aggregations=frozenset(info.aggregations), accumulated=info.accumulated, caveat=info.caveat,
                       attributes=tuple(sorted(own_attributes(self.index, info.iri))),
                       has_data=not self.index.properties_with_data or info.iri in self.index.properties_with_data)

    # ---------------- consultas ----------------
    def measure(self, iri: str) -> Measure | None:
        return self.measures.get(expand(iri))

    @property
    def coverage(self) -> tuple[date, date] | None:
        return self.index.coverage

    def stations_in(self, text: str) -> dict[str, str]:
        """Estações citadas no texto (código ICAO ou rótulo), sem LLM: IRI -> trecho."""
        return self.index.link_entities(text)

    def station_label(self, iri: str) -> str:
        iri = expand(iri)
        return iri.rsplit("/", 1)[-1]

    def measures_in(self, text: str) -> dict[str, str]:
        """Grandezas que o texto nomeia pelos rótulos da ontologia, sem LLM: IRI -> rótulo."""
        return self.index.link_properties(text)

    def symbol(self, unit_iri: str | None) -> str:
        short = (unit_iri or "").rsplit("/", 1)[-1]
        return self.index.unit_symbols.get(unit_iri or "") or EXTRA_SYMBOLS.get(short, "")

    def unit_names(self) -> list[str]:
        return sorted(UNIT_DIMENSION)

    def dimension_of(self, unit: str | None) -> str | None:
        return UNIT_DIMENSION.get((unit or "").rsplit(":", 1)[-1].rsplit("/", 1)[-1])

    def to_canonical(self, value, unit: str | None, measure_iri: str) -> Decimal | None:
        """Valor de uma condição na unidade canônica da grandeza; None se a escala não é conhecida (o chamador recusa, não chuta)."""
        m = self.measure(measure_iri)
        return convert_filter_value(value, unit, m.unit if m else None)

    @property
    def group_dims(self) -> tuple[str, ...]:
        return GROUP_DIMS

    # ---------------- o cardápio do intérprete ----------------
    def menu(self, candidates: dict[str, str], stations: dict[str, str]) -> str:
        """O que o LLM pode escolher: todas as grandezas (são poucas), marcando as que a pergunta cita; só as estações reconhecidas na
        pergunta (a lista completa tem 178 e ocupava o prompt). Tudo em IRIs da ontologia."""
        lines = ["<cardapio>", "Grandezas (use o IRI):"]
        for m in self.measures.values():
            if not m.has_data:
                continue
            aggs = ", ".join(sorted(m.aggregations)) or "nenhuma"
            attrs = f" | atributos próprios: {', '.join('met:' + a.rsplit('#', 1)[-1] for a in m.attributes)}" if m.attributes else ""
            cited = f"  <- citada na pergunta como '{candidates[m.iri]}'" if m.iri in candidates else ""
            lines.append(f"- {m.short} | {', '.join(m.labels[:4])} | unidade: {m.symbol or 'sem unidade'} | "
                         f"{'acumulada' if m.accumulated else 'instantânea'} | agregações: {aggs}{attrs}{cited}")
        lines.append("Estações reconhecidas na pergunta (use o IRI):")
        lines += [f"- st:{iri.rsplit('/', 1)[-1]} | trecho: '{text}'" for iri, text in stations.items()] or \
                 ["- nenhuma (sem estação = todas; se a pergunta cita cidade, estado ou estação fora dos dados, status \"unsupported\")"]
        lines.append(f"Dimensões de agrupamento: {', '.join(GROUP_DIMS)}")
        lines.append("</cardapio>")
        return "\n".join(lines)
