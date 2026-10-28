# Revisão do conjunto novo — 28/10/2026

Arquivo gerado: `perguntas_novas_20261028.yaml`.
Conjunto congelado: `../eval/frozen/novo_a_20261028/questions.yaml`.
Origem declarada: OpenAI GPT-6 (Codex), geração independente em 28/10/2026.

Os nomes receberam o sufixo `20261028` porque `perguntas_novas.yaml` e
`eval/frozen/novo_a` já existiam. Os artefatos anteriores foram preservados.
Não foram lidos `DECISOES.md`, regras do pipeline ou conjuntos antigos para
gerar as perguntas. O congelador existente fez a checagem automática de
repetições sem expor as perguntas anteriores ao gerador.

## Conferências

- 50 perguntas independentes, IDs E01–E50, sem perguntas textualmente repetidas.
- Categorias: 12 simples, 8 com condição numérica, 8 séries/rankings,
  4 comparações, 6 impossíveis, 4 ambíguas, 4 informais e 4 temporais.
- 47 estações explícitas nas perguntas, todas presentes em `estacoes_novas.csv`.
- Todos os anos de 2016 a 2025 representados; intervalos individuais conferidos
  contra a cobertura por estação extraída de `pressao.csv`.
- Incluídos bulbo úmido, ponto de orvalho, rajada, base de nuvem e duração da chuva.
- Unidades, vazios, limites de limpeza, cabeceiras, camadas e critérios temporais
  declarados em `assumptions` de cada pergunta respondível.

## Validação executada

Os 40 oráculos foram executados sobre os CSVs originais usando o worker
`eval/independent_evaluation/oracle_worker.py`, em processos independentes,
com limite de 180 segundos por execução e duas execuções simultâneas.
O worker restringe arquivos e colunas lidos; o isolamento de processos não
constitui um sandbox de segurança.

Resultado: **40 oráculos com status `ok`; 10 perguntas sem oráculo, conforme
seus comportamentos esperados. Nenhum erro, timeout ou resultado vazio/não
finito detectado.**

Resultados calculados, leituras utilizadas e tempos por execução:
`validacao_novo_a_20261028/oracle_results.json`.

Registro de remoções: **nenhuma** (`removals: []` no relatório).
As perguntas geradas não foram editadas após o congelamento.
O sucesso de execução verifica a obtenção de resultados; não substitui o
julgamento humano de eventuais divergências futuras com o pipeline.

## Integridade e reprodução

SHA-256 da cópia congelada, conferido antes e depois da validação:

```text
8478a9263099e47b88ecadc572c2ef3fb2535449bfd084c42274c019857234fb
```

O manifesto original permanece em `../eval/frozen/novo_a_20261028/manifest.json`.
O hash do arquivo bruto também está registrado no relatório de validação;
ele pode diferir do hash congelado devido à serialização YAML do congelador.

`gerar_perguntas_20261028.py` registra a geração e recusa sobrescrever o YAML.
`validar_perguntas_20261028.py` verifica o hash e recusa sobrescrever a pasta
de resultados de uma execução anterior.

Nenhuma execução do pipeline ou medição de desempenho foi realizada.
Em uma avaliação posterior, divergências entre pipeline e oráculos devem
seguir para julgamento humano, conforme o documento de instruções.
