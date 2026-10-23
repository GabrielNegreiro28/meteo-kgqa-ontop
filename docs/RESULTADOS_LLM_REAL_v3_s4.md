# Resultados com LLM real

Modelo: `gpt-6-luna (prompts v3)` · custo estimado: US$ 0.6272 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **sintético** (rdflib). Comparação com o oráculo independente.

### Todas (n=24)

- status final igual ao esperado: **4/24**
- respondíveis com resultado conferido: 2/12 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **1**: T10
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **9**: D01, D02, D04, D05, T01, T03, T04, T06, T07
- abstenções indevidas (pergunta respondível recusada): 7: D03→needs_clarification, T02→needs_clarification, T05→needs_clarification, T08→needs_clarification, T11→needs_clarification, T12→needs_clarification, T16→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 1: D06
- reparos usados: 2 · respostas de reserva (texto determinístico): 0
- erros de LLM: nenhum

### dev (n=8)

- status final igual ao esperado: **1/8**
- respondíveis com resultado conferido: 1/5 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **4**: D01, D02, D04, D05
- abstenções indevidas (pergunta respondível recusada): 1: D03→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 1: D06
- reparos usados: 0 · respostas de reserva (texto determinístico): 0
- erros de LLM: nenhum

### test (n=16)

- status final igual ao esperado: **3/16**
- respondíveis com resultado conferido: 1/7 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **1**: T10
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **5**: T01, T03, T04, T06, T07
- abstenções indevidas (pergunta respondível recusada): 6: T02→needs_clarification, T05→needs_clarification, T08→needs_clarification, T11→needs_clarification, T12→needs_clarification, T16→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 2 · respostas de reserva (texto determinístico): 0
- erros de LLM: nenhum

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 2 | 0 | 0 | 1 | 1 |
| silent_wrong | 1 | 0 | 0 | 1 | 0 |
| surfaced_empty | 9 | 0 | 0 | 0 | 9 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| D01 | dev | answered | no_results | ERRADO | 0 |  | ok |
| D02 | dev | answered | no_results | ERRADO | 0 |  | ok |
| D03 | dev | answered | needs_clarification | — | 0 |  | — |
| D04 | dev | answered | no_results | ERRADO | 0 |  | ok |
| D05 | dev | answered | no_results | ERRADO | 0 |  | ok |
| D06 | dev | needs_clarification | no_results | — | 0 |  | ok |
| D07 | dev | unsupported | needs_clarification | — | 0 |  | — |
| D08 | dev | no_results | no_results | ok | 0 |  | ok |
| T01 | test | answered | no_results | ERRADO | 0 |  | ok |
| T02 | test | answered | needs_clarification | — | 0 |  | — |
| T03 | test | answered | no_results | ERRADO | 0 |  | ok |
| T04 | test | answered | no_results | ERRADO | 0 |  | ok |
| T05 | test | answered | needs_clarification | — | 0 |  | — |
| T06 | test | answered | no_results | ERRADO | 0 |  | ok |
| T07 | test | answered | no_results | ERRADO | 0 |  | ok |
| T08 | test | no_results | needs_clarification | — | 0 |  | — |
| T09 | test | no_results | no_results | ok | 1 |  | PERIOD_MISMATCH |
| T10 | test | answered | answered | ERRADO | 1 |  | PERIOD_MISMATCH,FORECAST_NOT_SELECTED |
| T11 | test | answered | needs_clarification | — | 0 |  | — |
| T12 | test | answered | needs_clarification | — | 0 |  | — |
| T13 | test | needs_clarification | needs_clarification | — | 0 |  | — |
| T14 | test | unsupported | needs_clarification | — | 0 |  | — |
| T15 | test | unsupported | needs_clarification | — | 0 |  | — |
| T16 | test | answered | needs_clarification | — | 0 |  | — |
