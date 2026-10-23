"""Prompt v7: agregação simples e limiar montados por código. As três falhas da avaliação independente (E05, E14, E23) não podem
ser escritas: período, unidade e agregação vêm da interpretação, não de um SPARQL livre."""
from datetime import date

from pipeline.compiler import canonical_filters, compile_structured
from pipeline.validators import PipelineInterpretation, validate_interpretation, validate_query
from pipeline.vocab import STATION_NS, OntologyIndex, convert_filter_value
from tests.test_structured import E, IDX, P, interp


def codes(i, q):
    return sorted({f.diag.code for f in validate_interpretation(i, IDX, q, (), True)})


def test_unit_conversion_is_explicit_and_refuses_unknown_scales():
    assert convert_filter_value(1, "unit:KiloM", "http://qudt.org/vocab/unit/M") == 1000
    assert convert_filter_value(35, "unit:DEG_C", "http://qudt.org/vocab/unit/DEG_C") == 35
    assert convert_filter_value(35, None, "http://qudt.org/vocab/unit/DEG_C") == 35
    assert convert_filter_value(1, "unit:KiloM", "http://qudt.org/vocab/unit/DEG_C") is None


def test_threshold_in_km_is_compiled_in_metres_E14():
    i = interp(properties=["met:PrevailingVisibility"], entities=E("SBGR"), period=P("2022-06-01", "2022-06-30"), aggregation="count",
               filters=[{"op": "<", "value": 1, "unit": "unit:KiloM"}])
    q = compile_structured(i, IDX, force=True)
    assert "FILTER(?v < 1000)" in q
    assert not validate_query(q, i, IDX, True)[1]


def test_km_in_the_question_without_the_unit_is_refused_E14():
    i = interp(properties=["met:PrevailingVisibility"], entities=E("SBGR"), period=P("2022-06-01", "2022-06-30"), aggregation="count",
               filters=[{"op": "<", "value": 1}])
    assert "FILTER_UNIT_MISMATCH" in codes(i, "Quantas horas tiveram visibilidade abaixo de 1 km em SBGR em junho de 2022?")


def test_partial_month_period_is_taken_from_the_interpretation_E05():
    i = interp(properties=["met:PressureQNH"], entities=E("SBGR"), period=P("2022-09-01", "2022-09-15"), aggregation="avg")
    q = compile_structured(i, IDX, force=True)
    assert '"2022-09-01"^^xsd:date' in q and '"2022-09-15"^^xsd:date' in q and "2022-09-30" not in q
    assert "GROUP BY" not in q                     # um valor só


def test_sum_by_station_is_never_a_max_E23():
    i = interp(properties=["met:Precipitation"], entities=[{"text": s, "iri": f"st:{s}"} for s in ("SBGR", "SBBR", "SBBE")],
               period=P("2023-01-01", "2023-12-31"), aggregation="sum", group_by=["station"],
               order={"by": "aggregate", "direction": "desc", "limit": 5})
    q = compile_structured(i, IDX, force=True)
    assert "SUM(?v)" in q and "MAX(" not in q and "DESC(?value)" in q


def test_unknown_unit_makes_the_compiler_refuse():
    i = interp(properties=["met:AirTemperature"], entities=E("SBGR"), aggregation="count", filters=[{"op": ">", "value": 90, "unit": "unit:DEG_F"}])
    assert compile_structured(i, IDX, force=True) is None
    assert canonical_filters(i, IDX) is None


def test_grouped_filter_stays_unsupported_and_v6_behaviour_is_unchanged():
    i = interp(properties=["met:AirTemperature"], entities=E("SBGR"), aggregation="avg", group_by=["year"], filters=[{"op": ">", "value": 30}])
    assert compile_structured(i, IDX, force=True) is None
    plain = interp(properties=["met:AirTemperature"], entities=E("SBGR"), aggregation="avg")
    assert compile_structured(plain, IDX) is None         # sem force (v6) a agregação simples continua com o LLM


def _daily(**kw):
    base = dict(properties=["met:AirTemperature"], entities=E("SBGR"), period=P("2024-01-01", "2024-01-31"), aggregation="count",
                daily={"agg": "max", "op": ">", "value": 30, "unit": "unit:DEG_C"})
    return interp(**{**base, **kw})


def test_days_over_a_threshold_are_counted_per_day_not_per_reading_E15():
    i = _daily()
    q = compile_structured(i, IDX)                      # daily conta como forma estruturada: vale já na v6 do compilador
    assert q and "GROUP BY ?d1 HAVING (MAX(?v1) > 30)" in q and "COUNT(?d0) AS ?n" in q
    assert not validate_query(q, i, IDX, True)[1]


def test_counting_days_in_the_question_requires_daily_not_filters():
    q = "Em quantos dias de janeiro de 2024 a máxima de SBGR ficou acima de 30 °C?"
    assert "DAILY_OMITTED" in codes(interp(properties=["met:AirTemperature"], entities=E("SBGR"), period=P("2024-01-01", "2024-01-31"),
                                           aggregation="count", filters=[{"op": ">", "value": 30}]), q)
    assert not [c for c in codes(_daily(), q) if c.startswith("DAILY") or c == "FILTER_OMITTED"]


def test_daily_shape_rules():
    assert "DAILY_SHAPE" in codes(_daily(aggregation="max"), "em quantos dias a máxima ficou acima de 30 em SBGR em janeiro de 2024")
    assert "DAILY_SHAPE" in codes(_daily(filters=[{"op": ">", "value": 30}]), "em quantos dias a máxima ficou acima de 30 em SBGR em janeiro de 2024")
    assert "BAD_SCHEMA" in codes(_daily(daily={"agg": "median", "op": ">", "value": 30}), "x")
    assert "DAILY_NOT_IN_QUESTION" in codes(_daily(), "quantas vezes a temperatura passou de 30 em SBGR em janeiro de 2024")


def test_negative_threshold_is_recognised_by_the_query_rules():
    i = interp(properties=["met:AirTemperature"], entities=E("SBGR"), aggregation="count", filters=[{"op": "<", "value": -2, "unit": "unit:DEG_C"}])
    q = compile_structured(i, IDX, force=True)
    assert "FILTER(?v < -2)" in q and not validate_query(q, i, IDX, True)[1]


def test_multi_year_range_is_not_a_false_positive_E22_E26():
    from pipeline.validators import question_years
    assert question_years("como variou o qnh medio anual de sbme de 2016 a 2025?") == {2016, 2025}
    assert question_years("liste a umidade relativa media de sbmo para cada ano de 2020 a 2025.") == {2020, 2025}
    assert question_years("entre 2018 e 2020 em sbgr") == {2018, 2020}
    assert question_years("em 2019 choveu 2000 mm") == {2019}
    i = interp(properties=["met:PressureQNH"], entities=E("SBGR"), period=P("2016-01-01", "2025-12-31"), aggregation="avg", group_by=["year"])
    assert not codes(i, "Como variou o QNH médio anual de SBGR de 2016 a 2025?")
    i2 = interp(properties=["met:PressureQNH"], entities=E("SBGR"), period=P("2016-01-01", "2025-12-31"), aggregation="avg")
    assert not codes(i2, "Qual a média do QNH de SBGR de 2016 a 2025?")
    bad = interp(properties=["met:PressureQNH"], entities=E("SBGR"), period=P("2016-01-01", "2024-12-31"), aggregation="avg")
    assert "PERIOD_PARTIAL_YEAR" in codes(bad, "Qual a média do QNH de SBGR de 2016 a 2025?")


def test_no_period_is_accepted_only_when_the_year_range_spans_the_whole_coverage():
    whole = interp(properties=["met:PressureQNH"], entities=E("SBGR"), aggregation="avg", group_by=["year"])
    assert "PERIOD_OMITTED" not in codes(whole, "Como variou o QNH anual de SBGR entre 2016 e 2025?")
    assert "PERIOD_OMITTED" in codes(whole, "Como variou o QNH anual de SBGR entre 2018 e 2020?")
