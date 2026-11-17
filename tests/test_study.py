import pytest

from eval.study import CONDITIONS, schedule, summarize


def questions():
    return [{'id': str(i), 'question': f'Pergunta {i}', 'expected_behavior':
             'answerable' if i < 80 else 'needs_clarification' if i < 100 else 'unsupported'} for i in range(120)]


def test_schedule_is_paired_repeated_and_interleaved():
    tasks = schedule(questions())
    assert tasks == schedule(questions())
    assert len(tasks) == 1800
    assert len({(t['id'], t['condition'], t['repetition']) for t in tasks}) == 1800
    for start in range(0, len(tasks), 5):
        block = tasks[start:start+5]
        assert len({t['id'] for t in block}) == 1
        assert {t['condition'] for t in block} == set(CONDITIONS)


def test_study_refuses_wrong_strata_and_duplicates():
    with pytest.raises(ValueError):
        schedule(questions()[:-1])
    qs = questions()
    qs[1]['id'] = qs[0]['id']
    with pytest.raises(ValueError):
        schedule(qs)


def test_repetitions_not_pooled_and_incomplete_never_passes():
    qs = {q['id']: q for q in questions()}
    events = [{**t, 'correct': True, 'harmful': False, 'expected_behavior': qs[t['id']]['expected_behavior'],
               'status': 'answered', 'cost_usd': .01, 'elapsed_s': 1} for t in schedule(list(qs.values()))]
    results = summarize(events)
    conditions = [r for r in results if 'condition' in r]
    assert len(conditions) == 15 and all(r['n'] == 120 and r['accepted'] for r in conditions)
    assert all(r['error_wilson95'][1] < .04 for r in conditions)
    partial = [r for r in summarize(events[:-1]) if 'condition' in r]
    assert sum(not r['accepted'] for r in partial) == 1


def test_bfo_ablation_preserves_domain_context():
    from metqa.knowledge import EvoLexicon
    from tests.test_metqa_shapes import CAT
    from pathlib import Path
    workspace = Path(__file__).resolve().parents[1] / '.evoontology'
    full = EvoLexicon(CAT, workspace)
    ablated = EvoLexicon(CAT, workspace, full.version, bfo_context=False)
    a, b = full.lookup('temperatura do ar'), ablated.lookup('temperatura do ar')
    assert a.measures == b.measures and a.info == b.info
    assert 'categoria BFO:' in a.context and 'categoria BFO:' not in b.context
    assert a.context.replace('categoria BFO: quality | ', '') == b.context
