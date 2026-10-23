# Resultados com LLM real

Modelo: `gpt-6-luna` · custo estimado: US$ 0.6212 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **sintético** (rdflib). Comparação com o oráculo independente.

### Todas (n=24)

- status final igual ao esperado: **12/24**
- respondíveis com resultado conferido: 9/10 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **1**: T10
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 9: D02→needs_clarification, D03→needs_clarification, T05→needs_clarification, T07→needs_clarification, T08→needs_clarification, T09→rejected, T11→needs_clarification, T12→needs_clarification, T16→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 14 · respostas de reserva (texto determinístico): 0 · consultas montadas pelo compilador (não são acerto do LLM): 1
- erros de LLM: {'invalid_output': 5}

### dev (n=8)

- status final igual ao esperado: **5/8**
- respondíveis com resultado conferido: 4/4 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 2: D02→needs_clarification, D03→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 4 · respostas de reserva (texto determinístico): 0 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: {'invalid_output': 1}

### test (n=16)

- status final igual ao esperado: **7/16**
- respondíveis com resultado conferido: 5/6 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **1**: T10
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 7: T05→needs_clarification, T07→needs_clarification, T08→needs_clarification, T09→rejected, T11→needs_clarification, T12→needs_clarification, T16→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 10 · respostas de reserva (texto determinístico): 0 · consultas montadas pelo compilador (não são acerto do LLM): 1
- erros de LLM: {'invalid_output': 4}

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 7 | 0 | 0 | 4 | 3 |
| silent_wrong | 1 | 0 | 0 | 0 | 1 |
| surfaced_empty | 3 | 0 | 3 | 0 | 0 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| D01 | dev | answered | answered | ok | 1 |  | ENTITY_MISMATCH |
| D02 | dev | answered | needs_clarification | — | 0 |  | — |
| D03 | dev | answered | needs_clarification | — | 0 |  | — |
| D04 | dev | answered | answered | ok | 2 |  | ENTITY_MISMATCH |
| D05 | dev | answered | answered | ok | 1 |  | TYPE_CLASH |
| D06 | dev | needs_clarification | needs_clarification | — | 0 |  | — |
| D07 | dev | unsupported | needs_clarification | — | 0 |  | — |
| D08 | dev | no_results | no_results | ok | 0 |  | ok |
| T01 | test | answered | answered | ok | 3 |  | TYPE_CLASH |
| T02 | test | answered | answered | ok | 1 |  | ok |
| T03 | test | answered | answered | ok | 2 |  | ENTITY_MISMATCH |
| T04 | test | answered | answered | ok | 0 |  | ok |
| T05 | test | answered | needs_clarification | — | 0 |  | — |
| T06 | test | answered | answered | ok | 3 |  | TYPE_CLASH,ENTITY_MISMATCH,PERIOD_MISMATCH |
| T07 | test | answered | needs_clarification | — | 0 |  | — |
| T08 | test | no_results | needs_clarification | — | 0 |  | — |
| T09 | test | no_results | rejected | — | 1 |  | PERIOD_MISMATCH |
| T10 | test | answered | answered | ERRADO | 0 |  | ok |
| T11 | test | answered | needs_clarification | — | 0 |  | — |
| T12 | test | answered | needs_clarification | — | 0 |  | — |
| T13 | test | needs_clarification | needs_clarification | — | 0 |  | — |
| T14 | test | unsupported | needs_clarification | — | 0 |  | — |
| T15 | test | unsupported | needs_clarification | — | 0 |  | — |
| T16 | test | answered | needs_clarification | — | 0 |  | — |
