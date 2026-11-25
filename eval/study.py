"""Estudo pareado 80/20/20, três repetições; prepara agenda sem chamar LLM.

--run --budget USD executa a agenda revisada. Exige snapshot e referências limpas.
O JSON de perguntas deve incluir reviewed_by e questions; use perguntas inéditas.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import random
from statistics import median
import time

from eval.clean_reference import compare
from eval.stats import wilson, mcnemar_exact
from ingest.manifest import load

CONDITIONS = ('full', 'one_reading', 'no_conservation', 'formal', 'no_bfo_context')


def schedule(questions, seed=20261103):
    counts = Counter(q['expected_behavior'] for q in questions)
    if counts != {'answerable': 80, 'needs_clarification': 20, 'unsupported': 20}:
        raise ValueError('study requires 80 answerable, 20 ambiguous and 20 unsupported questions')
    if len({q['id'] for q in questions}) != 120 or len({q['question'] for q in questions}) != 120:
        raise ValueError('duplicate study questions or ids')
    rng, tasks = random.Random(seed), []
    for repetition in range(1, 4):
        ids = [q['id'] for q in questions]
        rng.shuffle(ids)
        for cid in ids:
            conditions = list(CONDITIONS)
            rng.shuffle(conditions)
            tasks.extend({'repetition': repetition, 'id': cid, 'condition': c} for c in conditions)
    return tasks


def summarize(events):
    """Repetições são relatadas separadamente, nunca como perguntas independentes."""
    report = []
    for repetition in range(1, 4):
        groups = {}
        for condition in CONDITIONS:
            rows = [e for e in events if e['repetition'] == repetition and e['condition'] == condition]
            if len({r['id'] for r in rows}) != len(rows):
                raise ValueError('duplicate study event')
            groups[condition] = {r['id']: r for r in rows}
            errors = sum(r['harmful'] for r in rows)
            answered = [r for r in rows if r['expected_behavior'] == 'answerable']
            behavior = [r for r in rows if r['expected_behavior'] != 'answerable']
            report.append({'repetition': repetition, 'condition': condition, 'n': len(rows),
                           'correct': sum(r['correct'] for r in rows), 'errors': errors,
                           'error_wilson95': wilson(errors, len(rows)),
                           'statuses': dict(Counter(r['status'] for r in rows)),
                           'cost_usd': sum(r['cost_usd'] for r in rows),
                           'mean_latency_s': sum(r['elapsed_s'] for r in rows) / len(rows) if rows else None,
                           'median_latency_s': median(r['elapsed_s'] for r in rows) if rows else None,
                           'by_behavior': {b: {'n': sum(r['expected_behavior'] == b for r in rows),
                                               'correct': sum(r['correct'] and r['expected_behavior'] == b for r in rows)}
                                           for b in ('answerable', 'needs_clarification', 'unsupported')},
                           'accepted': len(rows) == 120 and errors == 0 and
                               all(r['correct'] for r in behavior) and len(answered) == 80 and
                               sum(r['correct'] for r in answered) >= 72 and wilson(errors, 120)[1] < .04})
        for condition in CONDITIONS[1:]:
            a, b = groups['full'], groups[condition]
            if len(a) == 120 and set(a) == set(b):
                only_a = sum(a[i]['correct'] and not b[i]['correct'] for i in a)
                only_b = sum(b[i]['correct'] and not a[i]['correct'] for i in a)
                report.append({'repetition': repetition, 'pair': ['full', condition],
                               'mcnemar_p': mcnemar_exact(only_a, only_b)})
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('questions', 'references', 'snapshot', 'out'):
        ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--run', action='store_true')
    ap.add_argument('--budget', type=float)
    ap.add_argument('--conditions', help='subconjunto das condições, separadas por vírgula (padrão: todas)')
    ap.add_argument('--repetitions', type=int, default=3, help='quantas repetições da agenda rodar (1 a 3)')
    ap.add_argument('--slice', help='fatia A:B da agenda filtrada, para rodar em blocos (cada bloco em outro --out)')
    ap.add_argument('--authorize-usd', type=float, help='autorização extra no ledger (exige --authorized-by e --reason)')
    ap.add_argument('--authorized-by')
    ap.add_argument('--reason')
    args = ap.parse_args()
    document = json.loads(args.questions.read_text(encoding='utf-8'))
    if not document.get('reviewed_by'):
        raise ValueError('question/reference review required before study freeze')
    questions = document['questions']
    tasks = schedule(questions)
    wanted = set(args.conditions.split(',')) if args.conditions else set(CONDITIONS)
    if not wanted <= set(CONDITIONS) or not 1 <= args.repetitions <= 3:
        raise ValueError('condição desconhecida ou repetições fora de 1..3')
    # filtrar a agenda congelada preserva a ordem pseudoaleatória dela; nada é sorteado de novo
    tasks = [t for t in tasks if t['condition'] in wanted and t['repetition'] <= args.repetitions]
    if args.slice:
        a, b = (int(x) for x in args.slice.split(':'))
        tasks = tasks[a:b]
    from eval.freeze_set import check, seen_questions
    errors = check(questions, seen_questions())
    if errors:
        raise ValueError('; '.join(errors))
    snapshot = load(args.snapshot)
    references = json.loads(args.references.read_text(encoding='utf-8'))
    if references['snapshot_id'] != snapshot['snapshot_id']:
        raise ValueError('reference snapshot mismatch')
    if any(q['id'] not in references['cases'] for q in questions if q['expected_behavior'] == 'answerable'):
        raise ValueError('missing clean references')
    if args.run and (args.budget is None or args.budget <= 0):
        raise ValueError('--run requires an explicit positive --budget')
    manifest = {'tasks': tasks, 'reviewed_by': document['reviewed_by'], 'budget_usd': args.budget,
                'conditions': sorted(wanted), 'repetitions': args.repetitions, 'slice': args.slice,
                'inputs': {name: hashlib.sha256(getattr(args, name).read_bytes()).hexdigest()
                           for name in ('questions', 'references', 'snapshot')}}
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    if not args.run:
        print('Agenda congelada; nenhuma chamada de LLM.')
        return
    from metqa.app import MetQA, Settings
    from metqa.app.cli import build
    from metqa.knowledge import EvoLexicon, OntologyLexicon
    settings = Settings.from_env(snapshot=args.snapshot, budget_usd=args.budget, exemplars=False, record_trajectories=False)
    if args.authorize_usd:
        if not (args.authorized_by and args.reason):
            raise ValueError('--authorize-usd exige --authorized-by e --reason')
        from metqa.llm.ledger import Ledger
        Ledger(str(settings.ledger)).authorize(args.authorize_usd, by=args.authorized_by, reason=args.reason)
    full = build(settings, run='study:' + args.out.name)
    if settings.lexicon != 'evo':
        raise ValueError('full study requires EvoOntology')
    apps = {'full': full}
    for condition in CONDITIONS[1:]:
        config = replace(settings, readings=1 if condition == 'one_reading' else 2,
                         conservation=condition != 'no_conservation', reread=condition != 'no_conservation')
        lexicon = (OntologyLexicon(full.catalog) if condition == 'formal' else
                   EvoLexicon(full.catalog, settings.workspace, full.lexicon.version, bfo_context=condition != 'no_bfo_context'))
        apps[condition] = MetQA(full.catalog, lexicon, full.llm, full.source, config)
    lookup, events = {q['id']: q for q in questions}, []
    with (args.out / 'events.jsonl').open('x', encoding='utf-8') as stream:
        for task in tasks:
            if full.llm.spent_usd >= args.budget:
                break
            q = lookup[task['id']]
            spent, started = full.llm.spent_usd, time.perf_counter()
            result = apps[task['condition']].ask(q['question'])
            response = result.response
            correct = (compare(response, references['cases'][q['id']]) if q['expected_behavior'] == 'answerable'
                       else response.status.value == q['expected_behavior'])
            event = {**task, 'expected_behavior': q['expected_behavior'], 'correct': correct,
                     'harmful': not correct and response.status.value in ('answered', 'no_results'),
                     'status': response.status.value, 'elapsed_s': time.perf_counter() - started,
                     'cost_usd': full.llm.spent_usd - spent, 'response': response.to_dict(), 'trace': result.trace}
            stream.write(json.dumps(event, ensure_ascii=False, default=str) + '\n')
            stream.flush()
            events.append(event)
            if any(d.code == 'BUDGET_EXCEEDED' for d in response.diagnostics):
                break
    (args.out / 'summary.json').write_text(json.dumps(summarize(events), indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
