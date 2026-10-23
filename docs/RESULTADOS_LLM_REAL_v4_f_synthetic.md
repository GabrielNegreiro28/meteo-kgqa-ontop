# Resultados com LLM real

Modelo: `gpt-6-luna (prompts v4)` · custo estimado: US$ 0.6913 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **sintético** (rdflib). Comparação com o oráculo independente.

### Todas (n=24)

- status final igual ao esperado: **22/24**
- respondíveis com resultado conferido: 17/17 corretas (das quais 1 incompletas — faltam colunas que a referência pede — e 1 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 2: T05→unsupported, T11→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 6 · respostas de reserva (texto determinístico): 1 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

### dev (n=8)

- status final igual ao esperado: **8/8**
- respondíveis com resultado conferido: 6/6 corretas (das quais 0 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 0
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 2 · respostas de reserva (texto determinístico): 0 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

### test (n=16)

- status final igual ao esperado: **14/16**
- respondíveis com resultado conferido: 11/11 corretas (das quais 1 incompletas — faltam colunas que a referência pede — e 1 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 2: T05→unsupported, T11→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 4 · respostas de reserva (texto determinístico): 1 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 15 | 0 | 3 | 0 | 12 |
| surfaced_empty | 2 | 0 | 1 | 1 | 0 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| D01 | dev | answered | answered | ok | 0 |  | ok |
| D02 | dev | answered | answered | ok | 1 |  | TYPE_CLASH,TYPE_CLASH |
| D03 | dev | answered | answered | ok | 0 |  | ok |
| D04 | dev | answered | answered | ok | 1 |  | TYPE_CLASH,TYPE_CLASH,ENTITY_MISMATCH |
| D05 | dev | answered | answered | ok | 0 |  | ok |
| D06 | dev | needs_clarification | needs_clarification | — | 0 |  | — |
| D07 | dev | unsupported | unsupported | — | 0 |  | — |
| D08 | dev | no_results | no_results | ok | 0 |  | ok |
| T01 | test | answered | answered | ok | 1 |  | TYPE_CLASH,TYPE_CLASH |
| T02 | test | answered | answered | ok | 0 |  | ok |
| T03 | test | answered | answered | ok | 0 |  | ok |
| T04 | test | answered | answered | ok | 0 |  | ok |
| T05 | test | answered | unsupported | — | 0 |  | — |
| T06 | test | answered | answered | ok | 0 |  | ok |
| T07 | test | answered | answered | ok | 1 |  | UNSUPPORTED_FUNCTION |
| T08 | test | no_results | no_results | ok | 0 |  | ok |
| T09 | test | no_results | no_results | ok | 0 |  | ok |
| T10 | test | answered | answered | ok | 1 |  | FORECAST_NOT_SELECTED |
| T11 | test | answered | needs_clarification | — | 0 |  | — |
| T12 | test | answered | answered | ok | 1 | sim | ok |
| T13 | test | needs_clarification | needs_clarification | — | 0 |  | — |
| T14 | test | unsupported | unsupported | — | 0 |  | — |
| T15 | test | unsupported | unsupported | — | 0 |  | — |
| T16 | test | answered | answered | ok | 0 |  | ok |
