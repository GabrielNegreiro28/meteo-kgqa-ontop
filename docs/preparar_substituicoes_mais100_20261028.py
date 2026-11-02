"""Novas perguntas para falhas da validação, sem alterar o conjunto bruto."""
from pathlib import Path
import hashlib
import json
import gerar_mais100_20261028 as generator
import yaml

DOCS = Path(__file__).resolve().parent
generator.QUESTIONS.clear()
generator.scalar('simples', 'Qual foi a menor visibilidade predominante de SBNF em julho de 2024, em metros?',
                 'SBNF', '2024-07-01', '2024-08-01', 'visibpre', 'min')
generator.QUESTIONS[0]['id'] = 'E59R1'
target = DOCS / 'substituicoes_mais100_20261028.yaml'
with target.open('x', encoding='utf-8') as stream:
    yaml.safe_dump({'questions': generator.QUESTIONS}, stream, allow_unicode=True, sort_keys=False)
(DOCS / 'substituicoes_mais100_20261028.sha256.json').write_text(
    json.dumps({'file': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}, indent=2), encoding='utf-8')
print(target.name)
