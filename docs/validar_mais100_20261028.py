"""Valida o artefato imutável com o worker existente, gravando apenas em docs."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time
import yaml

DOCS = Path(__file__).resolve().parent
FROZEN = DOCS.parent / 'eval' / 'frozen' / 'novo_b_100_20261028'
SRC = FROZEN / 'questions.yaml'
WORKER = DOCS.parent / 'eval' / 'independent_evaluation' / 'oracle_worker.py'
CSV = Path(r'C:\Users\Gabriel\OneDrive\Área de Trabalho\Parente\METEOROLOGIA')
OUT = DOCS / 'validacao_novo_b_100_20261028'


def run(q):
    if q['expected_behavior'] != 'answerable':
        return dict(id=q['id'], status='not_applicable', expected_behavior=q['expected_behavior'])
    dest = OUT / (q['id'] + '.json')
    started = time.monotonic()
    try:
        p = subprocess.run([sys.executable, '-I', '-B', str(WORKER), str(SRC), q['id'], str(dest)],
                           cwd=CSV, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
        row = json.loads(dest.read_text(encoding='utf-8')) if dest.exists() else dict(id=q['id'], status='error', error=p.stderr[-1000:])
    except subprocess.TimeoutExpired:
        row = dict(id=q['id'], status='timeout', error='Limite de 180 segundos excedido.')
    row['elapsed_seconds'] = round(time.monotonic() - started, 2)
    return row


if __name__ == '__main__':
    sha = hashlib.sha256(SRC.read_bytes()).hexdigest()
    manifest = json.loads((FROZEN / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['files']['questions.yaml'] == sha
    raw = DOCS / 'perguntas_mais100_20261028.yaml'
    questions = yaml.safe_load(SRC.read_text(encoding='utf-8'))['questions']
    assert yaml.safe_load(raw.read_text(encoding='utf-8'))['questions'] == questions
    OUT.mkdir(exist_ok=False)
    rows = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(run, q) for q in questions]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(row['id'], row['status'], row.get('error', ''), flush=True)
    rows.sort(key=lambda row: row['id'])
    failed = [row for row in rows if row['status'] not in ('ok', 'not_applicable')]
    report = dict(frozen_name='novo_b_100_20261028', sha256=sha,
                  raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                  pipeline_executed=False, timeout_seconds=180, workers=3,
                  summary=dict(Counter(row['status'] for row in rows)), results=rows,
                  removals=[dict(id=row['id'], reason=row.get('error', row['status'])) for row in failed])
    (OUT / 'oracle_results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    assert hashlib.sha256(SRC.read_bytes()).hexdigest() == sha
    print(report['summary'], flush=True)
