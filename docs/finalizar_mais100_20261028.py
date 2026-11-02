"""Forma nova versão com substituição registrada e resultados já calculados."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import re
import sys
import yaml

DOCS = Path(__file__).resolve().parent
sys.path.insert(0, str(DOCS.parent))
from eval.freeze_set import freeze, verify, seen_questions, check, _norm


def read_yaml(path):
    return yaml.safe_load(path.read_text(encoding='utf-8'))['questions']


if __name__ == '__main__':
    original_dir = DOCS.parent / 'eval' / 'frozen' / 'novo_b_100_20261028'
    original = read_yaml(original_dir / 'questions.yaml')
    report = json.loads((DOCS / 'validacao_novo_b_100_20261028' / 'oracle_results.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((original_dir / 'questions.yaml').read_bytes()).hexdigest() == report['sha256']
    raw = DOCS / 'perguntas_mais100_20261028.yaml'
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == report['raw_sha256']
    assert read_yaml(raw) == original
    failures = [row for row in report['results'] if row['status'] not in ('ok', 'not_applicable')]
    assert [row['id'] for row in failures] == ['E59'], failures
    replacement_src = DOCS / 'substituicoes_mais100_20261028.yaml'
    replacement_hash = json.loads((DOCS / 'substituicoes_mais100_20261028.sha256.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(replacement_src.read_bytes()).hexdigest() == replacement_hash['sha256']
    replacement = read_yaml(replacement_src)[0]
    replacement_result = json.loads((DOCS / 'substituicao_E59R1_resultado.json').read_text(encoding='utf-8'))
    assert replacement['id'] == replacement_result['id'] == 'E59R1'
    assert replacement_result['status'] == 'ok'
    final = [replacement if item['id'] == 'E59' else item for item in original]
    # A checagem histórica exclui apenas esta própria versão bruta supersedida.
    historical = seen_questions() - {_norm(item['question']) for item in original}
    assert not check(final, historical)
    assert _norm(replacement['question']) not in seen_questions()
    assert len(final) == len({_norm(item['question']) for item in final}) == 100
    assert Counter(item['category'] for item in final) == Counter(item['category'] for item in original)
    target = DOCS / 'perguntas_mais100_20261028_validadas.yaml'
    class Dumper(yaml.SafeDumper):
        pass
    Dumper.add_representer(str, lambda dumper, value: dumper.represent_scalar(
        'tag:yaml.org,2002:str', value, style='|' if '\n' in value else None))
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        yaml.dump({'questions': final}, stream, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=120)
    # Usa o congelador original com root em docs, área autorizada para escrita.
    name = 'novo_b_100_20261028_validado'
    frozen = freeze(target, name, 'OpenAI GPT-6 (Codex); revisão com substituição documentada de E59 por E59R1', root=DOCS)
    sha = verify(name, root=DOCS)
    rows = [replacement_result if row['id'] == 'E59' else row for row in report['results']]
    assert Counter(row['status'] for row in rows) == {'ok': 80, 'not_applicable': 20}
    removals = [dict(id='E59', reason=failures[0]['error'], replacement_id='E59R1',
                     detail='Sem visibilidade válida em SBDO em julho de 2024; substituída por pergunta de mesma categoria em SBNF.')]
    final_report = dict(frozen_name=name, sha256=sha, pipeline_executed=False,
                        original_sha256=report['sha256'], replacement_source_sha256=replacement_hash['sha256'],
                        summary=dict(Counter(row['status'] for row in rows)), removals=removals, results=rows)
    (frozen / 'oracle_results.json').write_text(json.dumps(final_report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    stations = sorted(set(re.findall(r'\b(?:SB|SD|SS)[A-Z]{2}\b', ' '.join(item['question'].upper() for item in final))))
    review = f'''# Revisão das 100 perguntas adicionais — 28/10/2026

Entrega: `perguntas_mais100_20261028_validadas.yaml`.
Congelamento validado: `frozen/{name}/questions.yaml`.
Resultados: `frozen/{name}/oracle_results.json`.

São 100 perguntas adicionais às 50 da rodada anterior: 24 simples, 16 com
condição, 16 séries/rankings, 8 comparações, 12 não suportadas, 8 ambíguas,
8 informais e 8 com recortes temporais. Os IDs vão de E51 a E150, com E59
substituído pelo novo ID E59R1. Há {len(stations)} estações válidas citadas e
todos os anos de 2016 a 2025; as duas siglas fictícias das perguntas sem
suporte não entram nessa contagem. Foram incluídos bulbo úmido, ponto de
orvalho, rajada, nuvem e duração da chuva.

## Geração e validação

O arquivo bruto `perguntas_mais100_20261028.yaml` foi congelado em
`../eval/frozen/novo_b_100_20261028` antes da execução dos oráculos.
A conferência estrutural está em `conferencia_mais100_20261028.json`.
Não foram usadas regras do pipeline para gerar as perguntas.

Os 80 oráculos originais foram executados em processos separados, com
limite de 180 segundos e três execuções simultâneas, usando o worker do
repositório e os CSVs originais. O worker limita os arquivos e as colunas
lidos; não constitui sandbox de segurança. Resultado bruto: 79 códigos
com sucesso, uma falha por ausência de dados válidos e 20 perguntas sem
oráculo conforme o comportamento esperado.

## Registro de remoção e substituição

- Removida E59: não havia visibilidade válida em SBDO em julho de 2024.
- Incluída E59R1: menor visibilidade predominante de SBNF em julho de 2024.
- O código de E59R1 foi executado separadamente pelo mesmo worker e
  retornou 100 metros. A fonte da substituição tem hash próprio, registrado
  antes da execução, em `substituicoes_mais100_20261028.sha256.json`.

O bruto e o primeiro congelamento foram preservados sem edição. A versão
validada reaproveita integralmente as outras 99 perguntas e seus códigos;
os resultados correspondem às mesmas execuções já concluídas, sem refazer
os cálculos inalterados. A checagem automática contra conjuntos anteriores
excluiu somente a própria versão bruta desta rodada, e a substituta também
foi conferida contra todo o histórico.

Resultado final: **80 oráculos com status `ok`, 20 perguntas sem oráculo,
100 perguntas mantidas**. O sucesso de execução não substitui o julgamento
humano das eventuais divergências futuras com o pipeline.

## Integridade

SHA-256 da versão validada congelada:

```text
{sha}
```

O congelador original foi usado com `root=docs`, produzindo `docs/frozen/`,
dentro da área autorizada de escrita. O primeiro congelamento, em `eval/`,
continua disponível como registro bruto. A versão validada tem manifesto,
hash e resultados próprios. Nenhuma execução do pipeline foi realizada.
'''
    (DOCS / 'REVISAO_MAIS100_20261028.md').open('x', encoding='utf-8').write(review)
    assert verify(name, root=DOCS) == sha
    print(json.dumps(dict(file=target.name, sha256=sha, summary=final_report['summary'], explicit_stations=len(stations)), ensure_ascii=True))
