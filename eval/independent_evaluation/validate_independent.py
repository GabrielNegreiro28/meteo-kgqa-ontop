"""Validate a preserved raw generation without executing the QA pipeline."""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import sys, subprocess, json, hashlib, time, ast
from concurrent.futures import ThreadPoolExecutor, as_completed
import yaml
BASE=Path(__file__).resolve().parent
RAW=BASE/'questions_independent_raw.yaml'
OUT=BASE/'oracle_results'
OUT.mkdir(exist_ok=True)
raw_bytes=RAW.read_bytes()
sha=hashlib.sha256(raw_bytes).hexdigest()
questions=yaml.safe_load(raw_bytes)['questions']
assert len(questions)==50
assert [q['id'] for q in questions]==[f'E{i:02}' for i in range(1,51)]
assert Counter(q['category'] for q in questions)==Counter(simples=12,condicao=8,serie_ranking=8,comparacao=4,impossivel=6,ambigua=4,informal=4,tempo=4)
assert len({q['question'].strip().casefold() for q in questions})==50
for q in questions:
    assert set(q)>={'id','category','question','expected_behavior','rationale','assumptions'}
    assert q['expected_behavior'] in {'answerable','unsupported','needs_clarification'}
    if q['expected_behavior']=='answerable':ast.parse(q['oracle_pandas'])
    else:assert 'oracle_pandas' not in q
records=[]
previous=BASE/'validation_progress.json'
prior={r['id']:r for r in json.loads(previous.read_text(encoding='utf-8'))} if previous.exists() else {}
def run_one(q):
    if q['expected_behavior']!='answerable':
        return {'id':q['id'],'status':'not_applicable','expected_behavior':q['expected_behavior']}
    if q['id'] in prior:
        return prior[q['id']]
    start=time.monotonic()
    destination=OUT/(q['id']+'.json')
    try:
        p=subprocess.run([sys.executable,'-I','-B',str(BASE/'oracle_worker.py'),str(RAW),q['id'],str(destination)],cwd=OUT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        if destination.exists():r=json.loads(destination.read_text(encoding='utf-8'))
        else:r={'id':q['id'],'status':'error','error':f'Worker exit {p.returncode}: {p.stderr[-3000:]}'}
        if p.stderr:r['stderr']=p.stderr[-3000:]
    except subprocess.TimeoutExpired:
        r={'id':q['id'],'status':'timeout','error':'120 second limit exceeded'}
    r['elapsed_seconds']=round(time.monotonic()-start,3)
    return r
with ThreadPoolExecutor(max_workers=3) as pool:
    futures=[pool.submit(run_one,q) for q in questions]
    for future in as_completed(futures):
        r=future.result()
        records.append(r)
        records.sort(key=lambda x:x['id'])
        print(r['id'],r['status'],r.get('elapsed_seconds',''),r.get('error',''),flush=True)
        (BASE/'validation_progress.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
assert hashlib.sha256(RAW.read_bytes()).hexdigest()==sha
(BASE/'validation_results.json').write_text(json.dumps({'raw_sha256':sha,'finished_utc':datetime.now(timezone.utc).isoformat(),'timeout_seconds_per_oracle':120,'isolation':'fresh Python -I process; at most 3 concurrent workers; reviewed code; not a security sandbox','resumed_completed_ids':sorted(prior),'records':records},ensure_ascii=False,indent=2),encoding='utf-8')
print(Counter(r['status'] for r in records))
