"""Regressões da medição de GENERALIZAÇÃO (conjunto RG, 23/10/2026, v4 × v6 no grafo real). Cada teste usa a consulta ou a pergunta que falhou.

Falhas medidas e causa:
  RG09 (v6) e RG18 (v4): falsa ausência. Estação via VALUES/variável com `met:reportOf` ao contrário; WeatherStation, WeatherReport e
      Observation não eram incompatíveis, então o verificador de tipos nunca via o choque (a correção do RD02 cobria só estação constante).
  RG11 (v6): "quantas vezes" era pista de agrupar-por-valor; a contagem com filtro virava unsupported.
  RG13/RG14 (v4): o compilador de reserva respondia o total quando a pergunta pedia série mensal/anual.
  RG17/RG18 (v6): superlativo no SINGULAR sobre grupos ("a direção mais frequente", "o dia mais chuvoso") não virava ranking de 1.
  RG19 (v6): "capital de São Paulo" foi descartado em silêncio e a média de TODAS as estações saiu como se fosse dele.
Sem LLM; os testes contra o oráculo rodam só com o Ontop no ar.
"""
import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from eval.run_reference import SUITES, load_questions
from kgqa.contract import Status
from kgqa.store import LocalRdflibBackend, OntopBackend
from pipeline.compiler import compile_query, compile_structured
from pipeline.llm import ScriptedLLM
from pipeline.orchestrator import run_pipeline
from pipeline.validators import (PipelineInterpretation, unresolved_places, validate_interpretation, validate_query)
from pipeline.vocab import STATION_NS, OntologyIndex
from tests.test_real_pipeline import needs_duck, needs_ontop

ROOT = Path(__file__).resolve().parent.parent
GEN = {q["id"]: q for q in yaml.safe_load((ROOT / "eval" / "questions_real_gen.yaml").read_text(encoding="utf-8"))["questions"]}
P = lambda a, b: {"start": a, "end": b, "tz": "-03:00", "inclusive_end": True}
E = lambda s: [{"text": s, "iri": f"st:{s}"}]

# as consultas EXATAS que o modelo escreveu e que devolveram "sem registros" onde há dados
RG09_V6 = """SELECT ?station (SUM(?value) AS ?total) (COUNT(?obs) AS ?n) WHERE { VALUES ?station { st:SBRF st:SBSV } ?station met:reportOf ?report . ?obs met:inReport ?report ; a met:AccumulatedObservation ; sosa:observedProperty met:Precipitation ; sosa:phenomenonTime ?iv ; sosa:hasResult ?quantity ; met:localDate ?d . ?quantity qudt:numericValue ?value ; qudt:unit unit:MilliM . ?iv time:hasBeginning/time:inXSDDateTime ?hasBeginning ; time:hasEnd/time:inXSDDateTime ?hasEnd . FILTER(?d >= "2020-01-01"^^xsd:date && ?d <= "2020-12-31"^^xsd:date) } GROUP BY ?station"""
RG18_V4 = """SELECT ?d (MAX(?value) AS ?max) (COUNT(?obs) AS ?n) WHERE { ?station met:reportOf ?report . ?report met:reportOf st:SBPA . ?obs met:inReport ?report ; a met:AccumulatedObservation ; sosa:observedProperty met:Precipitation ; sosa:hasResult/qudt:numericValue ?value ; met:localDate ?d . FILTER(?d >= "2022-01-01"^^xsd:date && ?d <= "2022-12-31"^^xsd:date) } GROUP BY ?d ORDER BY DESC(?max) LIMIT 1"""


def real_index(stations=("SBRF", "SBSV", "SBPA", "SBGL", "SBRJ", "SBCT", "SBSP")):
    idx = OntologyIndex.load().with_profile_from_obda(ROOT / "mapping" / "met.obda")
    idx.entities = {STATION_NS + s: [s] for s in stations}
    idx.properties_with_data = set(idx.properties)
    idx.coverage = (date(2016, 1, 1), date(2025, 12, 31))
    return idx


IDX = real_index()


def qcodes(sparql, interp=None):
    return sorted({f.diag.code for f in validate_query(sparql, interp, IDX, True)[1]})


def icodes(i, question, structured=True):
    return sorted({f.diag.code for f in validate_interpretation(i, IDX, question, (), structured)})


def interp(**kw):
    return PipelineInterpretation(**{**dict(entities=[], filters=[], period=None, record_kind="observation", aggregation=None), **kw})


# ---------- RG09 / RG18: tipos incompatíveis ----------

def test_the_empty_by_construction_queries_are_caught_before_execution():
    assert "TYPE_CLASH" in qcodes(RG09_V6)                      # estação por VALUES + reportOf ao contrário
    assert "TYPE_CLASH" in qcodes(RG18_V4)                      # ?station met:reportOf ?report . ?report met:reportOf st:SBPA


@pytest.mark.parametrize("name,pattern", [
    ("boletim -> estação", "?r met:reportOf ?st . ?o met:inReport ?r ."),
    ("estação por VALUES, boletim do jeito certo", "VALUES ?st { st:SBRF } ?r met:reportOf ?st . ?o met:inReport ?r ."),
    ("caminho por sensor", "?st sosa:hosts ?s . ?o sosa:madeBySensor ?s ."),
    ("estação constante pelo sensor", "st:SBRF sosa:hosts ?s . ?o sosa:madeBySensor ?s ."),
])
def test_the_right_ways_to_reach_an_observation_are_not_flagged(name, pattern):
    q = f"SELECT ?o WHERE {{ {pattern} ?o sosa:observedProperty met:Precipitation . }}"
    assert "TYPE_CLASH" not in qcodes(q), name


def test_no_reference_query_trips_a_type_clash():
    for suite in SUITES:
        for q in load_questions(None, suite):
            if "sparql" not in q:
                continue
            idx = real_index(tuple(set(__import__("re").findall(r"st:([A-Z0-9]+)", q["sparql"]))) or ("SBGR",)) if suite.startswith("real") else OntologyIndex.load()
            got = {f.diag.code for f in validate_query(q["sparql"], None, idx, True)[1]}
            assert not got & {"TYPE_CLASH", "DISJOINT_TYPES"}, (suite, q["id"], got)


def test_the_incompatible_pairs_do_not_change_the_llm_context():
    """São só para checar consultas: os prompts já medidos (v1–v4 no sintético) não podem mudar."""
    syn = OntologyIndex.load()
    ctx = syn.prompt_context("ontology")
    assert "incompat" not in ctx and "WeatherReport" not in ctx.split("Classes disjuntas")[1].split("Grandezas")[0]
    assert frozenset((STATION_NS.replace("data/station/", "ontology#") + "WeatherStation",
                      STATION_NS.replace("data/station/", "ontology#") + "WeatherReport")) in syn.check_disjoint


# ---------- RG11 ----------

RG11 = interp(properties=["met:WindSpeed"], entities=E("SBGL"), period=P("2020-01-01", "2020-12-31"), aggregation="count",
              filters=[{"op": ">", "value": 25}])


def test_a_count_with_a_filter_is_not_forced_into_a_value_grouping():
    assert icodes(RG11, GEN["RG11"]["question"]) == []


# ---------- RG13 / RG14: o compilador de reserva não pode trocar a série pelo total ----------

@pytest.mark.parametrize("qid", ["RG13", "RG14"])
def test_the_fallback_compiler_refuses_a_monthly_or_annual_series(qid):
    i = interp(properties=["met:Precipitation"], entities=E("SBCT"), period=P("2019-01-01", "2019-12-31"), aggregation="sum")
    assert compile_query(i, IDX, GEN[qid]["question"]) is None
    assert compile_query(i, IDX, "Qual a precipitação total de SBCT em 2019?")          # a pergunta de um total continua compilando


# ---------- RG17 / RG18: superlativo no singular ----------

RG17 = interp(properties=["met:WindDirection"], entities=E("SBRJ"), period=P("2020-01-01", "2020-12-31"), aggregation="count",
              group_by=["value"], order={"by": "aggregate", "direction": "desc", "limit": 1})
RG18 = interp(properties=["met:Precipitation"], entities=E("SBPA"), period=P("2022-01-01", "2022-12-31"), aggregation="sum",
              group_by=["day"], order={"by": "aggregate", "direction": "desc", "limit": 1})


def with_(i, **kw):
    return PipelineInterpretation(**{**i.__dict__, **kw})


@pytest.mark.parametrize("qid,i", [("RG17", RG17), ("RG18", RG18)])
def test_the_singular_superlative_is_a_ranking_of_one(qid, i):
    q = GEN[qid]["question"]
    assert icodes(i, q) == []
    assert "ORDER_OMITTED" in icodes(with_(i, order=None), q)                              # o que o v6 devolveu: a tabela inteira ordenada por valor


def test_the_wrong_reading_of_the_rainiest_day_is_caught():
    """O v6 respondeu o MÁXIMO de uma leitura horária (35,2 mm) no lugar da soma do dia (45,6 mm): sem agrupar por dia."""
    wrong = interp(properties=["met:Precipitation"], entities=E("SBPA"), period=P("2022-01-01", "2022-12-31"), aggregation="max")
    assert "GROUP_BY_OMITTED" in icodes(wrong, GEN["RG18"]["question"])


def test_a_superlative_per_group_does_not_demand_a_ranking():
    """'a maior temperatura em cada ano' é um máximo POR ano, não o ano de maior temperatura."""
    i = interp(properties=["met:AirTemperature"], entities=E("SBGL"), aggregation="max", group_by=["year"])
    assert "ORDER_OMITTED" not in icodes(i, "Qual foi a maior temperatura de SBGL em cada ano?")


def test_a_limit_of_one_needs_a_singular_superlative_in_the_question():
    i = with_(RG17, order={"by": "aggregate", "direction": "desc", "limit": 1})
    assert "ORDER_NOT_IN_QUESTION" in icodes(i, "Quais as direções de vento de SBRJ em 2020?")


# ---------- RG19: lugar que não é estação ----------

def test_a_place_that_is_not_a_station_is_not_silently_dropped():
    i = interp(properties=["met:AirTemperature"], aggregation="avg")                       # o v6 interpretou como "todas as estações"
    assert "UNRESOLVED_PLACE" in icodes(i, GEN["RG19"]["question"], structured=False)
    assert unresolved_places(GEN["RG19"]["question"], IDX) == ["São", "Paulo"]


@pytest.mark.parametrize("question", [
    "Qual a temperatura média no Brasil em 2020?",                      # 'Brasil' = todas as estações
    "Qual a temperatura média de SBGR em 2020?",                        # código, não nome próprio
    "Qual foi a temperatura média em janeiro de 2022?",                 # mês em minúsculas
    "Qual a umidade média das estações em 2021?",
])
def test_ordinary_questions_have_no_unresolved_place(question):
    assert unresolved_places(question, IDX) == []


def test_the_rule_is_off_when_the_interpretation_has_a_station():
    i = interp(properties=["met:AirTemperature"], entities=E("SBSP"), aggregation="avg")
    assert "UNRESOLVED_PLACE" not in icodes(i, "Qual a temperatura média de SBSP em São Paulo?", structured=False)


def test_the_pipeline_answers_unsupported_not_a_national_average():
    bad = {"status": "ok", "properties": ["met:AirTemperature"], "entities": [], "filters": [], "period": None, "aggregation": "avg",
           "record_kind": "observation"}
    llm = ScriptedLLM({"interpret": [json.dumps(bad)], "generate": ["{}"], "answer": ["x"]})
    res = run_pipeline(GEN["RG19"]["question"], llm, LocalRdflibBackend(), IDX, timeout_s=20, prompts_version="v4")
    assert res.response.status == Status.UNSUPPORTED
    assert not [c for c in llm.calls if c["stage"] == "generate"]


def test_the_known_place_questions_in_every_suite_are_exactly_the_ones_to_refuse():
    """Falso positivo custa abstenção: em todas as perguntas dos conjuntos, só as que citam cidade/lugar são sinalizadas."""
    flagged = []
    for suite in SUITES:
        idx = real_index() if suite.startswith("real") else OntologyIndex.load()
        for q in load_questions(None, suite):
            if unresolved_places(q["question"], idx):
                flagged.append((suite, q["id"], q["expected_status"]))
    assert flagged and all(status == "unsupported" for _, _, status in flagged), flagged


# ---------- as formas de generalização, montadas por código, conferem com o oráculo ----------

GEN_SHAPES = {
    "RG13": interp(properties=["met:Precipitation"], entities=E("SBCT"), period=P("2019-01-01", "2019-12-31"), aggregation="sum", group_by=["month"]),
    "RG14": interp(properties=["met:AirTemperature"], entities=E("SBSV"), aggregation="avg", group_by=["year"]),
    "RG15": interp(properties=["met:WindSpeed"], period=P("2021-01-01", "2021-12-31"), aggregation="avg", group_by=["station"],
                   order={"by": "aggregate", "direction": "desc", "limit": 5}),
    "RG16": interp(properties=["met:WindSpeed"], entities=E("SBCF"), period=P("2022-01-01", "2022-12-31"), aggregation="count",
                   group_by=["met:runwayDesignator"]),
    "RG17": RG17,
    "RG18": RG18,
}
for _s in ("SBCF",):
    IDX.entities[STATION_NS + _s] = [_s]


@pytest.mark.parametrize("qid", sorted(GEN_SHAPES))
def test_generalisation_shapes_pass_every_rule(qid):
    i = GEN_SHAPES[qid]
    assert icodes(i, GEN[qid]["question"]) == [], qid
    sparql = compile_structured(i, IDX)
    assert sparql and not validate_query(sparql, i, IDX, True)[1]


@needs_ontop
@needs_duck
@pytest.mark.parametrize("qid", sorted(GEN_SHAPES))
def test_generalisation_shapes_match_the_oracle_on_the_real_graph(qid):
    from eval import oracle_real_gen
    from eval.compare import judge
    from kgqa.store import PREFIXES
    backend = OntopBackend()
    idx = OntologyIndex.from_ontop(backend)
    sparql = compile_structured(GEN_SHAPES[qid], idx)
    ex = backend.select(PREFIXES + sparql, timeout_s=60)
    assert ex.ok, ex.error
    same, why, _ = judge(ex.results, oracle_real_gen.expected(qid), GEN[qid]["compare"])
    assert same, (qid, why)
