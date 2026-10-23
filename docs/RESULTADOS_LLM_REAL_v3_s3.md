# Resultados com LLM real

Modelo: `gpt-6-luna (prompts v3)` · custo estimado: US$ 0.5792 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **sintético** (rdflib). Comparação com o oráculo independente.

### Todas (n=24)

- status final igual ao esperado: **4/24**
- respondíveis com resultado conferido: 2/9 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **7**: D02, D04, D05, T01, T03, T04, T06
- abstenções indevidas (pergunta respondível recusada): 10: D01→needs_clarification, D03→needs_clarification, T05→needs_clarification, T07→needs_clarification, T08→needs_clarification, T09→needs_clarification, T10→rejected, T11→needs_clarification, T12→needs_clarification, T16→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 2 · respostas de reserva (texto determinístico): 0
- erros de LLM: {'invalid_output': 1}

### dev (n=8)

- status final igual ao esperado: **2/8**
- respondíveis com resultado conferido: 1/4 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **3**: D02, D04, D05
- abstenções indevidas (pergunta respondível recusada): 2: D01→needs_clarification, D03→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 0 · respostas de reserva (texto determinístico): 0
- erros de LLM: nenhum

### test (n=16)

- status final igual ao esperado: **2/16**
- respondíveis com resultado conferido: 1/5 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **4**: T01, T03, T04, T06
- abstenções indevidas (pergunta respondível recusada): 8: T05→needs_clarification, T07→needs_clarification, T08→needs_clarification, T09→needs_clarification, T10→rejected, T11→needs_clarification, T12→needs_clarification, T16→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 2 · respostas de reserva (texto determinístico): 0
- erros de LLM: {'invalid_output': 1}

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 2 | 0 | 0 | 0 | 2 |
| silent_wrong | 1 | 0 | 0 | 1 | 0 |
| surfaced_empty | 7 | 0 | 0 | 0 | 7 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| D01 | dev | answered | needs_clarification | — | 0 |  | — |
| D02 | dev | answered | no_results | ERRADO | 0 |  | ok |
| D03 | dev | answered | needs_clarification | — | 0 |  | — |
| D04 | dev | answered | no_results | ERRADO | 0 |  | ok |
| D05 | dev | answered | no_results | ERRADO | 0 |  | ok |
| D06 | dev | needs_clarification | needs_clarification | — | 0 |  | — |
| D07 | dev | unsupported | needs_clarification | — | 0 |  | — |
| D08 | dev | no_results | no_results | ok | 0 |  | ok |
| T01 | test | answered | no_results | ERRADO | 0 |  | ok |
| T02 | test | answered | answered | ok | 1 |  | ok |
| T03 | test | answered | no_results | ERRADO | 0 |  | ok |
| T04 | test | answered | no_results | ERRADO | 0 |  | ok |
| T05 | test | answered | needs_clarification | — | 0 |  | — |
| T06 | test | answered | no_results | ERRADO | 0 |  | ok |
| T07 | test | answered | needs_clarification | — | 0 |  | — |
| T08 | test | no_results | needs_clarification | — | 0 |  | — |
| T09 | test | no_results | needs_clarification | — | 0 |  | — |
| T10 | test | answered | rejected | — | 1 |  | FORECAST_NOT_SELECTED |
| T11 | test | answered | needs_clarification | — | 0 |  | — |
| T12 | test | answered | needs_clarification | — | 0 |  | — |
| T13 | test | needs_clarification | needs_clarification | — | 0 |  | — |
| T14 | test | unsupported | needs_clarification | — | 0 |  | — |
| T15 | test | unsupported | needs_clarification | — | 0 |  | — |
| T16 | test | answered | needs_clarification | — | 0 |  | — |
