# Resultados com LLM real

Modelo: `gpt-6-luna (prompts v1)` · custo estimado: US$ 0.4272 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **sintético** (rdflib). Comparação com o oráculo independente.

### Todas (n=24)

- status final igual ao esperado: **13/24**
- respondíveis com resultado conferido: 10/10 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 9: D05→rejected, T05→needs_clarification, T07→needs_clarification, T08→needs_clarification, T09→needs_clarification, T10→rejected, T11→needs_clarification, T12→needs_clarification, T16→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 9 · respostas de reserva (texto determinístico): 0
- erros de LLM: {'invalid_output': 6}

### dev (n=8)

- status final igual ao esperado: **6/8**
- respondíveis com resultado conferido: 5/5 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 1: D05→rejected
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 3 · respostas de reserva (texto determinístico): 0
- erros de LLM: {'invalid_output': 2}

### test (n=16)

- status final igual ao esperado: **7/16**
- respondíveis com resultado conferido: 5/5 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 8: T05→needs_clarification, T07→needs_clarification, T08→needs_clarification, T09→needs_clarification, T10→rejected, T11→needs_clarification, T12→needs_clarification, T16→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 6 · respostas de reserva (texto determinístico): 0
- erros de LLM: {'invalid_output': 4}

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 9 | 0 | 0 | 0 | 9 |
| surfaced_empty | 3 | 0 | 3 | 0 | 0 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| D01 | dev | answered | answered | ok | 0 |  | ok |
| D02 | dev | answered | answered | ok | 0 |  | ok |
| D03 | dev | answered | answered | ok | 1 |  | ok |
| D04 | dev | answered | answered | ok | 1 |  | ok |
| D05 | dev | answered | rejected | — | 1 |  | TYPE_CLASH,PERIOD_MISMATCH |
| D06 | dev | needs_clarification | needs_clarification | — | 0 |  | — |
| D07 | dev | unsupported | needs_clarification | — | 0 |  | — |
| D08 | dev | no_results | no_results | ok | 0 |  | ok |
| T01 | test | answered | answered | ok | 1 |  | ok |
| T02 | test | answered | answered | ok | 1 |  | ok |
| T03 | test | answered | answered | ok | 1 |  | ok |
| T04 | test | answered | answered | ok | 0 |  | ok |
| T05 | test | answered | needs_clarification | — | 0 |  | — |
| T06 | test | answered | answered | ok | 2 |  | TYPE_CLASH,PERIOD_MISMATCH |
| T07 | test | answered | needs_clarification | — | 0 |  | — |
| T08 | test | no_results | needs_clarification | — | 0 |  | — |
| T09 | test | no_results | needs_clarification | — | 0 |  | — |
| T10 | test | answered | rejected | — | 1 |  | UNKNOWN_IRI,CLASS_WITHOUT_DIRECT_INSTANCES,FORECAST_NOT_SELECTED |
| T11 | test | answered | needs_clarification | — | 0 |  | — |
| T12 | test | answered | needs_clarification | — | 0 |  | — |
| T13 | test | needs_clarification | needs_clarification | — | 0 |  | — |
| T14 | test | unsupported | needs_clarification | — | 0 |  | — |
| T15 | test | unsupported | unsupported | — | 0 |  | — |
| T16 | test | answered | needs_clarification | — | 0 |  | — |
