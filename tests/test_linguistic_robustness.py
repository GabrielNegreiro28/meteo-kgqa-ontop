"""Robustez das regras de linguagem (L4) a VARIAÇÕES de frase (docs/ANALISE_CRITICA.md, A-23).

As pistas de agrupamento, ordenação e atributo são listas de padrões em português escritas a partir de poucos exemplos. Aqui elas são
medidas em variações geradas (preposição, plural, sinônimo, caixa, acento, "-mente"), nos dois sentidos:
  - PRECISÃO: a interpretação correta de cada variação tem de passar sem nenhum achado (falso positivo = abstenção desnecessária);
  - COBERTURA: omitir a forma pedida tem de ser pego (falso negativo = resposta de outra pergunta, entregue como certa).
Sem LLM. Cada caso é uma frase + a interpretação que um modelo correto produziria.
"""
import itertools
from datetime import date
from pathlib import Path

import pytest

from pipeline.validators import PipelineInterpretation, validate_interpretation
from pipeline.vocab import STATION_NS, OntologyIndex

ROOT = Path(__file__).resolve().parent.parent
IDX = OntologyIndex.load().with_profile_from_obda(ROOT / "mapping" / "met.obda")
IDX.entities = {STATION_NS + s: [s] for s in ("SBGR", "SBPA", "SBRJ", "SBSP")}
IDX.properties_with_data = set(IDX.properties)
IDX.coverage = (date(2016, 1, 1), date(2025, 12, 31))

P = lambda a, b: {"start": a, "end": b, "tz": "-03:00", "inclusive_end": True}
Y2019 = P("2019-01-01", "2019-12-31")
E = lambda s: [{"text": s, "iri": f"st:{s}"}]

# (palavra na pergunta, IRI, agregação, palavra da agregação)
QUANT = [("temperatura", "met:AirTemperature", "avg", "média"), ("pressão", "met:PressureQNH", "avg", "média"),
         ("chuva", "met:Precipitation", "sum", "total"), ("umidade", "met:RelativeHumidity", "avg", "média")]


def interp(prop, agg, **kw):
    base = dict(entities=E("SBGR"), filters=[], period=None, record_kind="observation")
    return PipelineInterpretation(**{**base, "properties": [prop], "aggregation": agg, **kw})


def codes(i, q, structured=True):
    return {f.diag.code for f in validate_interpretation(i, IDX, q, (), structured)}


def case_id(c):
    return c[0][:60]


# ---------- 1. agrupar por tempo ou estação: muitas formas de dizer a mesma coisa ----------
GROUP_PHRASES = {
    "year": ["por ano", "em cada ano", "a cada ano", "de cada ano", "ano a ano", "anual", "anualmente", "Por Ano", "POR ANO"],
    "month": ["por mês", "por mes", "em cada mês", "a cada mês", "de cada mês", "mês a mês", "mensal", "mensalmente"],
    "day": ["por dia", "em cada dia", "a cada dia", "de cada dia", "dia a dia", "diária", "diário", "diariamente"],
}
GROUP_CASES = []
for dim, phrases in GROUP_PHRASES.items():
    for (word, iri, agg, agg_word), phrase in itertools.product(QUANT[:3], phrases):
        question = f"Qual a {word} {agg_word} de SBGR {phrase} em 2019?"
        GROUP_CASES.append((question, interp(iri, agg, period=Y2019, group_by=[dim]), dim))


@pytest.mark.parametrize("case", GROUP_CASES, ids=case_id)
def test_group_phrasings_accept_the_correct_interpretation(case):
    question, i, _ = case
    assert codes(i, question) == set(), question


@pytest.mark.parametrize("case", GROUP_CASES, ids=case_id)
def test_group_phrasings_catch_the_missing_grouping(case):
    question, i, dim = case
    missing = PipelineInterpretation(**{**i.__dict__, "group_by": []})
    assert "GROUP_BY_OMITTED" in codes(missing, question), question


STATION_PHRASES = ["por estação", "por aeródromo", "por estacao", "em cada estação", "de cada aeródromo", "a cada estação"]


@pytest.mark.parametrize("phrase", STATION_PHRASES)
def test_by_station_phrasings(phrase):
    q = f"Qual a temperatura média {phrase} em 2019?"
    ok = interp("met:AirTemperature", "avg", entities=[], period=Y2019, group_by=["station"])
    assert codes(ok, q) == set(), q
    assert "GROUP_BY_OMITTED" in codes(PipelineInterpretation(**{**ok.__dict__, "group_by": []}), q), q


# ---------- 2. cabeceira ----------
RUNWAY = ["Quantas medições de vento cada cabeceira de SBGR registrou em 2019?", "Quantas medições de vento SBGR registrou em cada cabeceira em 2019?",
          "Quantas medições de vento por cabeceira SBGR registrou em 2019?", "quantas medições de vento cada cabeceira de SBGR teve em 2019",
          "QUANTAS MEDIÇÕES DE VENTO CADA CABECEIRA DE SBGR REGISTROU EM 2019?"]


@pytest.mark.parametrize("q", RUNWAY)
def test_runway_phrasings(q):
    ok = interp("met:WindSpeed", "count", period=Y2019, group_by=["met:runwayDesignator"])
    assert codes(ok, q) == set(), q
    assert "ATTRIBUTE_OMITTED" in codes(PipelineInterpretation(**{**ok.__dict__, "group_by": []}), q), q


# ---------- 3. ranking com número ----------
NUMBERS = [("2", 2), ("3", 3), ("5", 5), ("10", 10), ("duas", 2), ("dois", 2), ("três", 3), ("cinco", 5), ("dez", 10)]
RANK_TEMPLATES = ["Quais as {n} estações com maior {p} média em 2019?", "Quais os {n} aeródromos com maior {p} média em 2019?",
                  "Quais são as {n} estações com maior {p} média em 2019?", "Liste as {n} estações com maior {p} média em 2019.",
                  "Quais as {n} estações que tiveram maior {p} média em 2019?"]
RANK_CASES = [(t.format(n=n, p="temperatura"), lim) for t, (n, lim) in itertools.product(RANK_TEMPLATES, NUMBERS)]


@pytest.mark.parametrize("case", RANK_CASES, ids=case_id)
def test_ranking_phrasings_accept_the_right_limit_and_catch_the_wrong_one(case):
    q, limit = case
    ok = interp("met:AirTemperature", "avg", entities=[], period=Y2019, group_by=["station"],
                order={"by": "aggregate", "direction": "desc", "limit": limit})
    assert codes(ok, q) == set(), q
    wrong = PipelineInterpretation(**{**ok.__dict__, "order": {**ok.order, "limit": limit + 1}})
    assert "ORDER_LIMIT_MISMATCH" in codes(wrong, q), q


@pytest.mark.parametrize("direction,word", [("asc", "menor"), ("asc", "menos"), ("desc", "maior")])
def test_ranking_direction_words(direction, word):
    q = f"Quais as 3 estações com {word} temperatura média em 2019?"
    ok = interp("met:AirTemperature", "avg", entities=[], period=Y2019, group_by=["station"],
                order={"by": "aggregate", "direction": direction, "limit": 3})
    assert codes(ok, q) == set(), q


# ---------- 4. superlativo no singular ----------
SINGULAR = [("Qual foi o dia mais chuvoso de 2022 em SBPA?", "met:Precipitation", "sum", "day"),
            ("Qual o dia mais chuvoso de 2022 em SBPA?", "met:Precipitation", "sum", "day"),
            ("Em SBPA, qual foi o mês mais chuvoso de 2022?", "met:Precipitation", "sum", "month"),
            ("Qual foi o mês menos chuvoso de 2022 em SBPA?", "met:Precipitation", "sum", "month"),
            ("Qual a direção de vento mais frequente em SBRJ em 2020?", "met:WindDirection", "count", "value"),
            ("Qual a direção do vento mais frequente em SBRJ em 2020?", "met:WindDirection", "count", "value"),
            ("Qual foi a direção de vento menos frequente em SBRJ em 2020?", "met:WindDirection", "count", "value")]


@pytest.mark.parametrize("case", SINGULAR, ids=case_id)
def test_singular_superlative_is_a_ranking_of_one(case):
    q, iri, agg, dim = case
    station = "SBRJ" if dim == "value" else "SBPA"
    year = 2020 if dim == "value" else 2022
    direction = "asc" if "menos" in q else "desc"
    ok = interp(iri, agg, entities=E(station), period=P(f"{year}-01-01", f"{year}-12-31"), group_by=[dim],
                order={"by": "aggregate", "direction": direction, "limit": 1})
    assert codes(ok, q) == set(), q
    assert "ORDER_OMITTED" in codes(PipelineInterpretation(**{**ok.__dict__, "order": None}), q), q


# ---------- 5. o que NÃO é agrupamento nem ranking (falso positivo custa abstenção) ----------
PLAIN = [("Qual foi a temperatura média de SBGR em 2019?", "met:AirTemperature", "avg"),
         ("Qual a maior temperatura de SBGR em 2019?", "met:AirTemperature", "max"),
         ("Qual foi a menor pressão de SBGR em 2019?", "met:PressureQNH", "min"),
         ("Quanto choveu em SBGR em 2019?", "met:Precipitation", "sum"),
         ("Qual a chuva total de SBGR em 2019?", "met:Precipitation", "sum"),
         ("Qual foi a umidade média de SBGR no ano de 2019?", "met:RelativeHumidity", "avg"),
         ("Qual foi a temperatura mínima de SBGR em 2019?", "met:AirTemperature", "min"),
         ("Quantas vezes a velocidade do vento passou de 25 nós em SBGR em 2019?", "met:WindSpeed", "count"),
         ("Qual a temperatura média de SBGR durante o dia em 2019?", "met:AirTemperature", "avg")]


@pytest.mark.parametrize("case", PLAIN, ids=case_id)
def test_plain_questions_are_never_forced_into_a_grouping_or_ranking(case):
    q, iri, agg = case
    filters = [{"op": ">", "value": 25}] if "passou de 25" in q else []
    bad = {c for c in codes(interp(iri, agg, period=Y2019, filters=filters), q) if c.startswith(("GROUP_BY", "ORDER", "ATTRIBUTE"))}
    assert bad == set(), (q, bad)


# ---------- 6. lugar que não é estação ----------
PLACES_REFUSED = ["Qual a temperatura média em Curitiba em 2020?", "Qual a temperatura média na capital de São Paulo?",
                  "Qual a temperatura média no Sul em 2020?", "Quanto choveu em Manaus em 2020?", "Quanto choveu em Porto Alegre em 2020?"]
PLACES_FINE = ["Qual a temperatura média no Brasil em 2020?", "Qual a temperatura média de SBGR em 2020?", "Qual a temperatura média de todas as estações?",
               "Qual a temperatura média em 2020?", "Qual a temperatura média em janeiro de 2020?"]


@pytest.mark.parametrize("q", PLACES_REFUSED)
def test_a_named_place_that_is_not_a_station_is_caught(q):
    assert "UNRESOLVED_PLACE" in codes(interp("met:AirTemperature", "avg", entities=[]), q, structured=False), q


@pytest.mark.parametrize("q", PLACES_FINE)
def test_ordinary_questions_are_not_taken_for_places(q):
    assert "UNRESOLVED_PLACE" not in codes(interp("met:AirTemperature", "avg", entities=[]), q, structured=False), q


@pytest.mark.parametrize("q", ["Qual a temperatura média em curitiba em 2020?", "Quanto choveu em manaus em 2020?",
                               "qual a temperatura média na capital de são paulo?"])
def test_a_place_typed_in_lowercase_is_caught_too(q):
    """A-24: a regra dependia de maiúscula e 'curitiba' em minúsculas passava."""
    assert "UNRESOLVED_PLACE" in codes(interp("met:AirTemperature", "avg", entities=[]), q, structured=False), q
