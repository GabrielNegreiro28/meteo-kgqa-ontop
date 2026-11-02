"""Período por dia local (`met:localDate`) aceito pelas regras, com mutações que provam o que elas barram.

Opção B de DECISOES.md (D-37): `met:localDate` vale para períodos de DIAS inteiros; instante e fuso diferente de UTC−3 não passam por ele;
não se mistura com limites por data-e-hora. Sem LLM e sem Ontop: o índice usa o perfil do `.obda`, que declara met:localDate.
"""
from pathlib import Path

import pytest
import yaml

from metqa.verification.rules import PipelineInterpretation, validate_query
from metqa.knowledge.index import STATION_NS, OntologyIndex

ROOT = Path(__file__).resolve().parent.parent
REAL = {q["id"]: q for q in yaml.safe_load((ROOT / "eval" / "questions_real.yaml").read_text(encoding="utf-8"))["questions"]}

IDX = OntologyIndex.load().with_profile_from_obda(ROOT / "mapping" / "met.obda")
for s in ("SBBE", "SBGR"):
    IDX.entities[STATION_NS + s] = [s]

YEAR = {"start": "2019-01-01", "end": "2019-12-31", "tz": "-03:00", "inclusive_end": True}
DAY = {"start": "2024-01-19", "end": "2024-01-19", "tz": "-03:00", "inclusive_end": True}
HALF_OPEN = {"start": "2019-01-01", "end": "2020-01-01", "tz": "-03:00", "inclusive_end": False}


def interp(period=YEAR, prop="met:Precipitation", agg="sum", station=("SBBE", "st:SBBE"), instant=None):
    return PipelineInterpretation(entities=[{"text": station[0], "iri": station[1]}], properties=[prop], filters=[], period=period,
                                  aggregation=agg, record_kind="observation", instant=instant)


def query(where: str) -> str:
    return f"""SELECT (SUM(?v) AS ?total) (COUNT(?v) AS ?n) WHERE {{
  st:SBBE sosa:hosts ?s .
  ?o a met:AccumulatedObservation ; sosa:madeBySensor ?s ; sosa:observedProperty met:Precipitation ;
     sosa:hasResult/qudt:numericValue ?v . {where} }}"""


def codes(sparql, i):
    _, findings = validate_query(sparql, i, IDX, True)
    return sorted({f.diag.code for f in findings})


D = lambda x: f'"{x}"^^xsd:date'
LD = "?o met:localDate ?d ."
RANGE = lambda a, b, lo=">=", hi="<=": f"{LD} FILTER(?d {lo} {D(a)} && ?d {hi} {D(b)})"


# ---------- o que passa ----------

def test_the_real_reference_query_for_a_year_is_accepted():
    """RD02: a consulta de referência real, que as regras recusavam com PERIOD_MISMATCH."""
    assert codes(REAL["RD02"]["sparql"], interp()) == []


def test_the_real_reference_query_for_a_single_day_constant_is_accepted():
    """RT07: a data é uma constante no padrão (met:localDate "2024-01-19"), sem FILTER."""
    assert codes(REAL["RT07"]["sparql"], interp(DAY, station=("SBGR", "st:SBGR"))) == []


def test_the_real_reference_query_grouped_by_runway_is_accepted():
    """RT01: contagem por cabeceira em 2019 (agrupamento + intervalo de dias)."""
    assert codes(REAL["RT01"]["sparql"], interp(YEAR, "met:WindSpeed", "count", ("SBGR", "st:SBGR"))) == []


@pytest.mark.parametrize("where,period", [
    (RANGE("2019-01-01", "2019-12-31"), YEAR),
    (RANGE("2019-01-01", "2020-01-01", hi="<"), YEAR),                  # fim exclusivo = dia seguinte
    (RANGE("2018-12-31", "2019-12-31", lo=">"), YEAR),                  # início exclusivo = dia anterior
    (f"{LD} FILTER(?d = {D('2024-01-19')})", DAY),                      # um dia, por igualdade
    (RANGE("2019-01-01", "2020-01-01", hi="<"), HALF_OPEN),             # período com fim exclusivo
])
def test_equivalent_ways_of_writing_the_same_days_are_accepted(where, period):
    assert codes(query(where), interp(period)) == []


# ---------- o que a regra barra (mutações) ----------

@pytest.mark.parametrize("name,where,period", [
    ("início deslocado um dia", RANGE("2019-01-02", "2019-12-31"), YEAR),
    ("fim exclusivo contado como inclusivo (perde o último dia)", RANGE("2019-01-01", "2019-12-31", hi="<"), YEAR),
    ("fim além do período", RANGE("2019-01-01", "2020-01-01"), YEAR),
    ("sem limite superior", f"{LD} FILTER(?d >= {D('2019-01-01')})", YEAR),
    ("sem limite inferior", f"{LD} FILTER(?d <= {D('2019-12-31')})", YEAR),
    ("met:localDate ligado mas sem nenhum limite", LD, YEAR),
    ("data constante para um período de um ano", f"?o met:localDate {D('2019-01-01')} .", YEAR),
    ("data constante errada para um dia", f"?o met:localDate {D('2024-01-20')} .", DAY),
    ("dois dias constantes para um dia", f"?o met:localDate {D('2024-01-19')} ; met:localDate {D('2024-01-20')} .", DAY),
    ("igualdade para um período de vários dias", f"{LD} FILTER(?d = {D('2019-01-01')})", YEAR),
])
def test_wrong_day_boundaries_are_rejected(name, where, period):
    assert "PERIOD_MISMATCH" in codes(query(where), interp(period)), name


CLOCK = ("?o sosa:phenomenonTime ?iv . ?iv time:hasBeginning/time:inXSDDateTime ?b ; time:hasEnd/time:inXSDDateTime ?e . "
         "FILTER(?b >= \"{lo}\"^^xsd:dateTime && ?e <= \"{hi}\"^^xsd:dateTime)")
JAN = "2019-01-01T00:00:00-03:00"
JAN_NEXT = "2020-01-01T00:00:00-03:00"


def test_both_forms_together_are_accepted_when_each_one_matches_the_period():
    """Medido no grafo real (RD02): o modelo escreveu as duas formas, a consulta estava certa. Filtros se somam: não há dupla contagem."""
    where = RANGE("2019-01-01", "2019-12-31") + " " + CLOCK.format(lo=JAN, hi=JAN_NEXT)
    assert not [c for c in codes(query(where), interp()) if c.startswith("PERIOD")]


@pytest.mark.parametrize("name,where", [
    ("dia local certo, data-e-hora com fim errado", RANGE("2019-01-01", "2019-12-31") + " " + CLOCK.format(lo=JAN, hi="2020-06-01T00:00:00-03:00")),
    ("dia local certo, data-e-hora em outro fuso", RANGE("2019-01-01", "2019-12-31") + " " + CLOCK.format(lo="2019-01-01T00:00:00Z", hi="2020-01-01T00:00:00Z")),
    ("dia local errado, data-e-hora certa", RANGE("2019-01-03", "2019-12-31") + " " + CLOCK.format(lo=JAN, hi=JAN_NEXT)),
])
def test_both_forms_together_are_rejected_when_either_one_is_wrong(name, where):
    assert "PERIOD_MISMATCH" in codes(query(where), interp()), name


def test_local_date_when_the_interpretation_has_no_period_is_rejected():
    assert "PERIOD_UNEXPECTED" in codes(query(RANGE("2019-01-01", "2019-12-31")), interp(period=None))


def test_instant_questions_cannot_use_local_date():
    """'às 12h' é um instante: o dia local não o representa."""
    i = interp(period=None, prop="met:AirTemperature", agg=None, instant="2019-06-01T12:00:00-03:00")
    q = ("SELECT ?v WHERE { st:SBBE sosa:hosts ?s . ?o a met:InstantaneousObservation ; sosa:madeBySensor ?s ; "
         "sosa:observedProperty met:AirTemperature ; sosa:hasResult/qudt:numericValue ?v ; "
         f"met:localDate {D('2019-06-01')} . }}")
    got = codes(q, i)
    assert "PERIOD_UNEXPECTED" in got and "INSTANT_MISMATCH" in got


def test_local_date_is_only_valid_in_the_local_timezone():
    other_tz = {**YEAR, "tz": "+00:00"}
    assert "LOCALDATE_TZ" in codes(query(RANGE("2019-01-01", "2019-12-31")), interp(other_tz))


def test_local_date_used_only_to_group_does_not_trigger_the_day_rule():
    """Projetar/agrupar por met:localDate com o período por data-e-hora segue o caminho antigo, sem achados de período."""
    q = ("SELECT ?d (AVG(?v) AS ?avg) (COUNT(?v) AS ?n) WHERE { st:SBBE sosa:hosts ?s . ?o a met:InstantaneousObservation ; "
         "sosa:madeBySensor ?s ; sosa:observedProperty met:AirTemperature ; sosa:phenomenonTime/time:inXSDDateTime ?t ; "
         "met:localDate ?d ; sosa:hasResult/qudt:numericValue ?v . "
         "FILTER(?t >= \"2019-01-01T00:00:00-03:00\"^^xsd:dateTime && ?t < \"2020-01-01T00:00:00-03:00\"^^xsd:dateTime) } GROUP BY ?d")
    assert not [c for c in codes(q, interp(YEAR, "met:AirTemperature", "avg")) if c.startswith("PERIOD")]


# ---------- contexto ----------

def test_context_teaches_local_date_only_where_the_graph_has_it():
    assert "met:localDate" not in OntologyIndex.load().prompt_context("ontology")             # sintético: não muda
    real = IDX.prompt_context("ontology")
    assert "Dia local da observação: ?obs met:localDate ?d" in real and "Não misture as duas formas" in real
    assert "UTC" in real                                                                      # o texto vem do rdfs:comment da ontologia
