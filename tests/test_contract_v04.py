import json
from calendar import monthrange

import pytest

from eval.matching import match_rows
from metqa.app import Settings
from metqa.domain.contract import Status
from tests.test_metqa import app, llm, nir, MEAN, MAX, Q_AMB


def test_matching_preserves_identity_multiplicity_and_empty_reference():
    assert not match_rows([['SBGL', 20], ['SBGR', 30]], [['SBGL', 30], ['SBGR', 20]])
    assert not match_rows([[999]], [])
    assert match_rows([], [])
    assert not match_rows([[1], [1]], [[1]])
    assert not match_rows([[float('nan')]], [[float('nan')]])
    with pytest.raises(ValueError):
        match_rows([], None)


def test_default_environment_confirmation(monkeypatch):
    monkeypatch.delenv('METQA_SECRET', raising=False)
    qa = app(llm((MEAN, MAX)))
    qa.settings = Settings.from_env()
    r = qa.ask(Q_AMB).response
    assert r.status == Status.NEEDS_CLARIFICATION
    assert isinstance(qa.settings.secret, bytes)


def test_no_evidence_cannot_execute():
    ir = nir('met:AirTemperature', ['st:EST-B'], 'avg')
    r = app(llm((ir, ir))).ask('temperatura em outra cidade').response
    assert r.status == Status.NEEDS_CLARIFICATION
    assert r.results is None


def test_raw_units_and_presentation_units_are_consistent():
    from tests.test_metqa_novo_c import _vis_km
    r = _vis_km('unit:KiloM')
    assert r.units['value'].endswith('/M')
    assert r.presentation[0]['units']['value'].endswith('/KiloM')
    assert float(r.presentation[0]['rows'][0]['value']) == pytest.approx(18.1668)
    assert float(r.results['results']['bindings'][0]['value']['value']) == 18166.8


def test_nonfinite_condition_rejected():
    from metqa.understanding import parse
    ir = nir('met:AirTemperature', agg='count', conditions=[{'op': '>', 'value': float('inf')}])
    assert parse(ir).errors


def test_full_iris_and_precision_survive_presentation():
    from decimal import Decimal
    from tests.test_metqa_shapes import ask, table, lit, XD
    from metqa.execution.source import typed_rows
    value = '20.1250000000000000000000001'
    iri = 'https://example.org/kgqa-met/station/SBGL'
    response, _ = ask(nir('met:AirTemperature', agg='avg', group_by=['station']),
                      table({'station': {'type': 'uri', 'value': iri}, 'value': lit(value, XD), 'n': lit(2)}))
    assert typed_rows(response.results)[0]['value'] == Decimal(value)
    assert response.presentation[0]['rows'][0]['station'] == iri
    assert response.presentation[0]['rows'][0]['value'] == value
    assert '20,13' in response.answer_text


def test_nonfinite_result_is_technical_error():
    from tests.test_metqa_shapes import ask, table, lit, XD
    response, _ = ask(nir('met:AirTemperature', agg='avg'), table({'value': lit('NaN', XD), 'n': lit(2)}))
    assert response.status == Status.EXECUTION_ERROR
    assert 'INVALID_RESULT' in {d.code for d in response.diagnostics}
    assert response.results is None


def test_temporal_reread_preserves_internal_filters_and_separate_ranges():
    from metqa.understanding import parse
    from metqa.understanding.evidence import reread_agrees
    ir = nir('met:AirTemperature', agg='avg', start='2020-01-01', end='2020-01-31', hours=[23, 0], weekdays=[6])
    parts = [q for _, q in parse(ir).parts]
    t = ir['time']
    assert reread_agrees(t, parts)
    assert reread_agrees({**t, 'local_hours': None, 'weekdays': None}, parts)      # o trecho não carrega o recorte
    assert not reread_agrees({**t, 'local_hours': [22]}, parts)
    assert not reread_agrees({**t, 'weekdays': [5]}, parts)
    assert not reread_agrees({**t, 'ranges': [{'start': '2020-01-01', 'end': '2020-01-10'}, {'start': '2020-01-20', 'end': '2020-01-31'}]}, parts)
    plain = [q for _, q in parse(nir('met:AirTemperature', agg='avg', start='2020-01-01', end='2020-12-31')).parts]
    assert not reread_agrees({**t, 'ranges': [{'start': '2020-01-01', 'end': '2020-12-31'}]}, plain)   # a leitura esqueceu o recorte
    months = [{'start': f'2020-{m:02d}-01', 'end': f'2020-{m:02d}-{monthrange(2020, m)[1]}'} for m in range(1, 13)]
    assert reread_agrees({'ranges': months, 'local_hours': None, 'weekdays': None, 'instant': None}, plain)


def test_confirmation_is_bound_to_snapshot_and_lexicon(monkeypatch):
    qa = app(llm((MEAN, MAX)))
    token = qa.confirmation_token(Q_AMB, MAX)
    monkeypatch.setattr(qa.catalog, 'snapshot', {'snapshot_id': 'new'})
    response = qa.ask(Q_AMB, confirmed=MAX, confirmation=token).response
    assert response.status == Status.REJECTED


def test_split_station_plan_exposes_every_executed_interpretation():
    from tests.test_metqa_shapes import ask, table, lit
    ir = nir('met:Precipitation', ['st:SBGL', 'st:SBGO'], 'count', count_of='hours', start='2020-01-01', end='2020-01-31')
    response, _ = ask(ir, table({'value': lit(10), 'n': lit(20)}), table({'value': lit(12), 'n': lit(20)}))
    assert response.status == Status.ANSWERED, response.diagnostics
    assert [p['label'] for p in response.interpretations] == ['SBGL', 'SBGO']
    assert all(len(p['query']['stations']) == 1 for p in response.interpretations)


def test_second_reading_without_evidence_cannot_validate_the_first():
    from tests.test_metqa_understanding import run, MARCH_IR, MARCH
    wrong = {**MARCH_IR, 'evidence': {}}
    response, _ = run({'interpret_A': [MARCH_IR], 'interpret_B': [wrong]}, MARCH, reread=False)
    assert response.status == Status.NEEDS_CLARIFICATION and response.results is None


def test_temporal_service_failure_is_not_semantic_ambiguity():
    from metqa.llm.client import LLMTimeout
    from tests.test_metqa_understanding import run, MARCH_IR, MARCH
    response, _ = run({'interpret_A': [MARCH_IR], 'interpret_B': [MARCH_IR], 'reread_time': [LLMTimeout('timeout')]}, MARCH)
    assert response.status == Status.EXECUTION_ERROR
    assert 'TEMPORAL_VERIFICATION_UNAVAILABLE' in {d.code for d in response.diagnostics}


def test_comparison_never_declares_winner_on_truncated_part():
    from metqa.domain import Executed, ResultShape, SubQuery
    from metqa.presentation.render import render
    from metqa.understanding import parse
    from tests.test_metqa_shapes import CAT, lit, table, XD
    cq = parse(nir('met:AirTemperature', ['st:SBGL'], 'avg')).parts[0][1]
    done = [Executed(SubQuery(label, cq), '', table({'value': lit(value, XD), 'n': lit(2)}),
                     truncated=label == 'A', shape=ResultShape('value', n='n')) for label, value in [('A', 30), ('B', 20)]]
    answer = render(done, 'compare', CAT, [])
    assert 'Não dá para declarar vencedor' in answer and 'Maior em' not in answer
