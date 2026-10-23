"""Forma do resultado (prompt v6): group_by / attributes / order. A consulta é MONTADA por código a partir da interpretação validada.

Origem: no split test limpo (12 perguntas reais), 4 respondíveis foram recusadas porque a interpretação não tinha como dizer
"por cabeceira", "em cada ano", "em qual cabeceira" nem "as três mais frequentes". Sem LLM; os testes com Ontop comparam com o
oráculo independente em pandas.
"""
import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from kgqa.contract import Status
from kgqa.store import LocalRdflibBackend, OntopBackend
from pipeline.compiler import compile_structured
from pipeline.dialogue import describe
from pipeline.llm import ScriptedLLM
from pipeline.orchestrator import run_pipeline
from pipeline.validators import PipelineInterpretation, validate_interpretation, validate_query
from pipeline.vocab import STATION_NS, OntologyIndex
from tests.test_real_pipeline import needs_duck, needs_ontop

ROOT = Path(__file__).resolve().parent.parent
REAL = {q["id"]: q for q in yaml.safe_load((ROOT / "eval" / "questions_real.yaml").read_text(encoding="utf-8"))["questions"]}

IDX = OntologyIndex.load().with_profile_from_obda(ROOT / "mapping" / "met.obda")
IDX.entities = {STATION_NS + s: [s] for s in ("SBGR", "SBBR", "SBBE")}
IDX.properties_with_data = set(IDX.properties)
IDX.coverage = (date(2016, 1, 1), date(2025, 12, 31))       # como no grafo real (senão a porta de cobertura recusa 2019 antes da etapa 2)

P = lambda a, b: {"start": a, "end": b, "tz": "-03:00", "inclusive_end": True}
E = lambda s: [{"text": s, "iri": f"st:{s}"}]


def interp(**kw) -> PipelineInterpretation:
    base = dict(entities=[], filters=[], period=None, record_kind="observation", aggregation=None)
    return PipelineInterpretation(**{**base, **kw})


# as 5 formas, com a pergunta real que cada uma responde
RT01 = (REAL["RT01"]["question"], interp(properties=["met:WindSpeed"], entities=E("SBGR"), period=P("2019-01-01", "2019-12-31"),
                                          aggregation="count", group_by=["met:runwayDesignator"]))
RT02 = (REAL["RT02"]["question"], interp(properties=["met:WindGust"], entities=E("SBGR"), period=P("2019-01-01", "2019-12-31"),
                                          aggregation="max", attributes=["met:runwayDesignator"]))
RT05 = (REAL["RT05"]["question"], interp(properties=["met:AirTemperature"], entities=E("SBBR"), aggregation="avg", group_by=["year"]))
RT06 = (REAL["RT06"]["question"], interp(properties=["met:PressureQNH"], period=P("2020-01-01", "2020-12-31"), aggregation="avg",
                                          group_by=["station"], order={"by": "aggregate", "direction": "desc", "limit": 5}))
RT12 = (REAL["RT12"]["question"], interp(properties=["met:WindDirection"], entities=E("SBGR"), period=P("2019-01-01", "2019-12-31"),
                                          aggregation="count", group_by=["value"], order={"by": "aggregate", "direction": "desc", "limit": 3}))
SHAPES = {"RT01": RT01, "RT02": RT02, "RT05": RT05, "RT06": RT06, "RT12": RT12}


def codes(i, question=None, structured=True):
    return sorted({f.diag.code for f in validate_interpretation(i, IDX, question, (), structured)})


def mutate(i: PipelineInterpretation, **kw) -> PipelineInterpretation:
    return PipelineInterpretation(**{**i.__dict__, **kw})


# ---------- as interpretações corretas passam por TODAS as regras (controle de falso positivo) ----------

@pytest.mark.parametrize("qid", sorted(SHAPES))
def test_the_correct_interpretation_of_each_shape_has_no_findings(qid):
    question, i = SHAPES[qid]
    assert codes(i, question) == []


@pytest.mark.parametrize("qid", sorted(SHAPES))
def test_the_compiled_query_of_each_shape_passes_every_query_rule(qid):
    _, i = SHAPES[qid]
    sparql = compile_structured(i, IDX)
    assert sparql, qid
    _, findings = validate_query(sparql, i, IDX, True)
    assert not findings, [f.diag.code for f in findings]


# ---------- vocabulário e esquema ----------

def test_schema_rejects_malformed_structure_fields():
    q, base = RT12
    assert "BAD_SCHEMA" in codes(mutate(base, group_by="value"), q)
    assert "BAD_SCHEMA" in codes(mutate(base, order={"by": "aggregate", "direction": "desc", "limit": 0}), q)
    assert "BAD_SCHEMA" in codes(mutate(base, order={"by": "aggregate", "direction": "desc", "limit": 1000}), q)
    assert "BAD_SCHEMA" in codes(mutate(base, order={"by": "aggregate", "direction": "up", "limit": 3}), q)
    assert "BAD_SCHEMA" in codes(mutate(base, order={"by": "value", "direction": "desc", "limit": 3}), q)
    assert "BAD_SCHEMA" in codes(mutate(base, order={"by": "aggregate", "direction": "desc", "limit": True}), q)


@pytest.mark.parametrize("name,change,expected", [
    ("dimensão inventada", dict(group_by=["cidade"]), "UNKNOWN_DIMENSION"),
    ("atributo de outra grandeza", dict(properties=["met:AirTemperature"], group_by=["met:runwayDesignator"]), "UNKNOWN_DIMENSION"),
    ("dimensão repetida", dict(group_by=["year", "year"]), "DUPLICATE_DIMENSION"),
    ("duas dimensões de tempo", dict(group_by=["year", "month"]), "ONE_TIME_DIMENSION"),
    ("agrupar sem agregar", dict(aggregation=None), "GROUP_BY_NEEDS_AGGREGATION"),
    ("valor medido sem contar", dict(properties=["met:WindDirection"], group_by=["value"], aggregation="avg"), "VALUE_GROUP_NEEDS_COUNT"),
    ("filtro numérico com agrupamento", dict(filters=[{"op": ">", "value": 10}]), "GROUPED_FILTER_AMBIGUOUS"),
    ("atributo desconhecido", dict(group_by=[], attributes=["met:foo"], aggregation="max"), "UNKNOWN_ATTRIBUTE"),
    ("atributo com agrupamento", dict(attributes=["met:runwayDesignator"], group_by=["year"]), "ATTRIBUTES_WITH_GROUPING"),
    ("atributo sem superlativo", dict(group_by=[], attributes=["met:runwayDesignator"], aggregation="avg"), "ATTRIBUTES_NEED_SUPERLATIVE"),
    ("ordem sem agrupar", dict(group_by=[], order={"by": "aggregate", "direction": "desc", "limit": 3}), "ORDER_NEEDS_GROUP_BY"),
    ("duas grandezas", dict(properties=["met:WindSpeed", "met:WindGust"]), "STRUCTURE_NEEDS_ONE_PROPERTY"),
])
def test_vocabulary_rules_reject_impossible_structure(name, change, expected):
    base = RT01[1] if "group_by" not in change or change.get("group_by") != ["year", "year"] else RT05[1]
    if name in ("valor medido sem contar",):
        base = RT12[1]
    assert expected in codes(mutate(base, **change)), name


def test_time_dimensions_need_the_local_day_in_the_graph():
    synthetic = OntologyIndex.load()                  # sem met:localDate
    i = interp(properties=["met:AirTemperature"], aggregation="avg", group_by=["year"])
    assert "DIMENSION_WITHOUT_DATA" in {f.diag.code for f in validate_interpretation(i, synthetic)}


# ---------- fundamentação na pergunta (L4) ----------

@pytest.mark.parametrize("name,question,i,expected", [
    ("agrupa sem a pergunta pedir", "Qual a temperatura média de SBBR?", mutate(RT05[1], group_by=["year"]), "GROUP_BY_NOT_IN_QUESTION"),
    ("atributo inventado", "Qual foi a maior rajada em SBGR em 2019?", RT02[1], "ATTRIBUTE_NOT_IN_QUESTION"),
    ("a pergunta pede por ano e a interpretação não agrupa", RT05[0], mutate(RT05[1], group_by=[]), "GROUP_BY_OMITTED"),
    ("a pergunta cita a cabeceira e a interpretação a ignora", RT01[0], mutate(RT01[1], group_by=[]), "ATTRIBUTE_OMITTED"),
    ("limite diferente do pedido", RT12[0], mutate(RT12[1], order={"by": "aggregate", "direction": "desc", "limit": 5}), "ORDER_LIMIT_MISMATCH"),
    ("ordena sem a pergunta pedir", RT05[0], mutate(RT05[1], order={"by": "aggregate", "direction": "desc", "limit": 3}), "ORDER_NOT_IN_QUESTION"),
    ("sentido oposto", RT06[0], mutate(RT06[1], order={"by": "aggregate", "direction": "asc", "limit": 5}), "ORDER_DIRECTION_MISMATCH"),
    ("a pergunta pede os N primeiros e não há ordem", RT12[0], mutate(RT12[1], order=None), "ORDER_OMITTED"),
])
def test_the_requested_shape_must_be_in_the_question(name, question, i, expected):
    assert expected in codes(i, question), name


def test_the_shape_rules_are_off_for_prompts_without_the_fields():
    """v1–v5 não têm esses campos no JSON: as regras novas não podem mudar o que já foi medido."""
    q = "Qual a temperatura média por estação em 2019?"
    i = interp(properties=["met:AirTemperature"], period=P("2019-01-01", "2019-12-31"), aggregation="avg")
    assert not [c for c in codes(i, q, structured=False) if c.startswith(("GROUP_BY", "ORDER", "ATTRIBUTE"))]
    assert "GROUP_BY_OMITTED" in codes(i, q, structured=True)


# ---------- montagem ----------

@pytest.mark.parametrize("name,change", [
    ("com filtro numérico", dict(filters=[{"op": ">", "value": 1}])),
    ("instante", dict(instant="2019-06-01T12:00:00-03:00")),
    ("várias estações sem agrupar por estação", dict(entities=E("SBGR") + E("SBBR"))),
    ("fuso diferente de UTC−3", dict(period={**P("2019-01-01", "2019-12-31"), "tz": "+00:00"})),
])
def test_compiler_refuses_what_it_cannot_assemble_faithfully(name, change):
    assert compile_structured(mutate(RT01[1], **change), IDX) is None, name


def test_compiler_needs_the_local_day_for_a_period():
    synthetic = OntologyIndex.load()
    i = interp(properties=["met:AirTemperature"], period=P("2019-01-01", "2019-12-31"), aggregation="avg",
               group_by=["station"])
    assert compile_structured(i, synthetic) is None


def test_compiled_text_has_the_expected_shape():
    q = compile_structured(RT12[1], IDX)
    assert "GROUP BY ?measured" in q and "ORDER BY DESC(?n) ASC(?measured) LIMIT 3" in q
    sup = compile_structured(RT02[1], IDX)
    assert sup.count("MAX(") == 1 and "OPTIONAL { ?obs met:runwayDesignator ?runway . }" in sup      # o máximo não some se não tiver cabeceira
    yr = compile_structured(RT05[1], IDX)
    assert "GROUP BY (YEAR(?d) AS ?year)" in yr and "ORDER BY ASC(?year)" in yr
    st = compile_structured(RT06[1], IDX)
    assert "GROUP BY ?station" in st and "ORDER BY DESC(?value) ASC(?station) LIMIT 5" in st


def test_the_user_is_told_the_shape_that_was_understood():
    text = describe(RT12[1], IDX)
    assert "resultado por: valor medido" in text and "ordem: decrescente" in text and "só os 3 primeiros" in text
    assert "mostrando também: runwayDesignator" in describe(RT02[1], IDX)


# ---------- pipeline (LLM roteirizado) ----------

def scripted(i: PipelineInterpretation) -> ScriptedLLM:
    d = {k: v for k, v in i.__dict__.items() if k in ("properties", "entities", "filters", "period", "aggregation", "record_kind",
                                                      "group_by", "attributes", "order", "daily")}
    return ScriptedLLM({"interpret": [json.dumps({"status": "ok", **d})], "generate": ["{}"], "answer": ["x"]})


def test_v6_never_asks_the_llm_for_the_query_or_the_answer():
    llm = scripted(RT05[1])
    res = run_pipeline(RT05[0], llm, LocalRdflibBackend(), IDX, timeout_s=20, prompts_version="v6")
    assert {c["stage"] for c in llm.calls} == {"interpret"}                     # montada por código e respondida sem LLM
    assert next(t for t in res.trace if t["event"] == "compile_structured")["sparql"]


def test_v6_without_a_deterministic_assembly_is_unsupported_not_a_guess():
    llm = scripted(mutate(RT01[1], period={**P("2019-01-01", "2019-12-31"), "tz": "+00:00"}))
    res = run_pipeline(RT01[0], llm, LocalRdflibBackend(), IDX, timeout_s=20, prompts_version="v6")
    assert res.response.status == Status.UNSUPPORTED
    assert not [c for c in llm.calls if c["stage"] in ("generate", "answer")]


def test_older_prompt_versions_cannot_return_the_structure_fields():
    """v4 devolvendo group_by cai como saída inválida: sem as regras L4 de v6 esses campos passariam sem conferência."""
    llm = scripted(RT05[1])
    res = run_pipeline(RT05[0], llm, LocalRdflibBackend(), IDX, timeout_s=20, prompts_version="v4")
    assert res.response.status in (Status.EXECUTION_ERROR, Status.REJECTED, Status.UNSUPPORTED)
    assert not [c for c in llm.calls if c["stage"] == "generate"]


# ---------- grafo real: a consulta montada confere com o oráculo independente ----------

JUDGE_SPEC = {   # os nomes de coluna são os da convenção do compilador (value, measured…), não os da consulta de referência
    "RT01": REAL["RT01"]["compare"], "RT02": REAL["RT02"]["compare"],
    "RT05": {"mode": "ordered", "columns": ["year", "value", "n"], "order_key": "year", "descending": False, "tolerance": {"value": 0.001}},
    "RT06": {"mode": "ordered", "columns": ["station", "value", "n"], "order_key": "value", "descending": True, "tolerance": {"value": 0.001}},
    "RT12": {"mode": "ordered", "columns": ["measured", "n"], "order_key": "n", "descending": True},
}


@needs_ontop
@needs_duck
@pytest.mark.parametrize("qid", sorted(SHAPES))
def test_compiled_shapes_match_the_independent_oracle_on_the_real_graph(qid):
    from eval import oracle_real
    from eval.compare import judge
    from kgqa.store import PREFIXES
    backend = OntopBackend()
    idx = OntologyIndex.from_ontop(backend)
    _, i = SHAPES[qid]
    sparql = compile_structured(i, idx)
    _, findings = validate_query(sparql, i, idx, True)
    assert not findings
    ex = backend.select(PREFIXES + sparql, timeout_s=60)
    assert ex.ok, ex.error
    same, why, _ = judge(ex.results, oracle_real.expected(qid), JUDGE_SPEC[qid])
    assert same, (qid, why)


@needs_ontop
@needs_duck
def test_v6_pipeline_answers_a_per_runway_question_end_to_end_with_one_llm_call():
    from eval import oracle_real
    backend = OntopBackend()
    llm = scripted(RT01[1])
    res = run_pipeline(RT01[0], llm, backend, OntologyIndex.from_ontop(backend), timeout_s=60, prompts_version="v6")
    assert res.response.status == Status.ANSWERED
    assert {c["stage"] for c in llm.calls} == {"interpret"}
    got = {b["runway"]["value"]: int(b["n"]["value"]) for b in res.response.results["results"]["bindings"]}
    assert got == {r: int(n) for r, n in oracle_real.expected("RT01")}
    assert "runway = 09R" in res.response.answer_text and "resultado por: runwayDesignator" in res.response.answer_text


# ---------- conjunto NOVO (questions_real_fresh.yaml): frases que as regras não viram ao serem escritas ----------

FRESH = {q["id"]: q for q in yaml.safe_load((ROOT / "eval" / "questions_real_fresh.yaml").read_text(encoding="utf-8"))["questions"]}
FRESH_SHAPES = {
    "RF01": interp(properties=["met:Precipitation"], entities=E("SBSP"), period=P("2021-01-01", "2021-12-31"), aggregation="sum", group_by=["month"]),
    "RF02": interp(properties=["met:AirTemperature"], period=P("2022-01-01", "2022-12-31"), aggregation="avg", group_by=["station"],
                   order={"by": "aggregate", "direction": "desc", "limit": 3}),
    "RF03": interp(properties=["met:WindSpeed"], entities=E("SBPA"), period=P("2020-01-01", "2020-12-31"), aggregation="avg",
                   group_by=["met:runwayDesignator"]),
    "RF04": interp(properties=["met:WindSpeed"], entities=E("SBCT"), period=P("2020-01-01", "2020-12-31"), aggregation="max",
                   attributes=["met:runwayDesignator"]),
    "RF05": interp(properties=["met:Precipitation"], entities=E("SBRJ"), period=P("2022-03-01", "2022-03-31"), aggregation="sum", group_by=["day"]),
    "RF06": interp(properties=["met:PressureQNH"], entities=E("SBCF"), aggregation="count", group_by=["year"]),
    "RF07": interp(properties=["met:WindDirection"], entities=E("SBFZ"), period=P("2021-01-01", "2021-12-31"), aggregation="count",
                   group_by=["value"], order={"by": "aggregate", "direction": "desc", "limit": 2}),
    "RF08": interp(properties=["met:RelativeHumidity"], entities=E("SBRJ") + E("SBGL") + E("SBSP"), period=P("2019-01-01", "2019-12-31"),
                   aggregation="min", group_by=["station"]),
}
for _s in ("SBSP", "SBPA", "SBCT", "SBRJ", "SBCF", "SBFZ", "SBGL"):
    IDX.entities[STATION_NS + _s] = [_s]


@pytest.mark.parametrize("qid", sorted(FRESH_SHAPES))
def test_unseen_phrasings_are_grounded_by_the_l4_rules_without_findings(qid):
    """Generalização das regras de linguagem: perguntas escritas depois delas, com a interpretação correta, não podem ser barradas."""
    assert codes(FRESH_SHAPES[qid], FRESH[qid]["question"]) == [], FRESH[qid]["question"]


@pytest.mark.parametrize("qid", sorted(FRESH_SHAPES))
def test_unseen_shapes_compile_and_pass_the_query_rules(qid):
    sparql = compile_structured(FRESH_SHAPES[qid], IDX)
    assert sparql
    assert not validate_query(sparql, FRESH_SHAPES[qid], IDX, True)[1]


@needs_ontop
@needs_duck
@pytest.mark.parametrize("qid", sorted(FRESH_SHAPES))
def test_unseen_shapes_match_the_independent_oracle_on_the_real_graph(qid):
    from eval import oracle_real_fresh
    from eval.compare import judge
    from kgqa.store import PREFIXES
    backend = OntopBackend()
    idx = OntologyIndex.from_ontop(backend)
    sparql = compile_structured(FRESH_SHAPES[qid], idx)
    ex = backend.select(PREFIXES + sparql, timeout_s=60)
    assert ex.ok, ex.error
    same, why, _ = judge(ex.results, oracle_real_fresh.expected(qid), FRESH[qid]["compare"])
    assert same, (qid, why)
