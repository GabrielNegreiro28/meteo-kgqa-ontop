"""Conferências estruturais; não usa regras do pipeline."""
import ast
from collections import Counter
from pathlib import Path
import json
import re
import pandas as pd
import yaml

DOCS = Path(__file__).resolve().parent
q = yaml.safe_load((DOCS / 'perguntas_mais100_20261028.yaml').read_text(encoding='utf-8'))['questions']
coverage = pd.read_csv(DOCS / 'estacoes_novas.csv').set_index('sigla')
issues = []
stations = set()
for item in q:
    text_stations = set(re.findall(r'\b(?:SB|SD|SS)[A-Z]{2}\b', item['question'].upper()))
    stations |= text_stations
    if item['expected_behavior'] != 'unsupported':
        assert text_stations <= set(coverage.index), (item['id'], text_stations - set(coverage.index))
    if 'oracle_pandas' not in item:
        continue
    code = item['oracle_pandas']
    names = ast.literal_eval(re.search(r'^stations = (.+)$', code, re.M)[1])
    dates = re.findall(r"chunk\['hora_observacao'\] [<>]=? '(\d{4}-\d{2}-\d{2})'", code)
    assert len(dates) == 2, item['id']
    for name in names or []:
        if (pd.Timestamp(dates[0]) < pd.Timestamp(coverage.loc[name, 'min']).normalize()
                or pd.Timestamp(dates[1]) - pd.Timedelta(days=1) > pd.Timestamp(coverage.loc[name, 'max']).normalize()):
            issues.append(dict(id=item['id'], station=name, interval=dates))
assert not issues, issues
years = sorted(set(re.findall(r'\b20(?:1[6-9]|2[0-5])\b', ' '.join(item['question'] for item in q))))
assert len(years) == 10
result = dict(count=len(q), categories=dict(Counter(item['category'] for item in q)),
              behaviors=dict(Counter(item['expected_behavior'] for item in q)),
              explicit_station_count=len(stations), explicit_stations=sorted(stations),
              years=years, coverage_issues=issues)
(DOCS / 'conferencia_mais100_20261028.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=True))
