# Resultados com LLM real

Modelo: `gpt-6-luna` · custo estimado: US$ 0.3860 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **sintético** (rdflib). Comparação com o oráculo independente.

### Todas (n=24)

- status final igual ao esperado: **13/24**
- respondíveis com resultado conferido: 11/11 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 8: T05→unsupported, T07→execution_error, T08→execution_error, T09→execution_error, T10→execution_error, T11→execution_error, T12→execution_error, T16→execution_error
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 3 · respostas de reserva (texto determinístico): 2 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: {'timeout': 1, 'circuit_open': 9}

### dev (n=8)

- status final igual ao esperado: **8/8**
- respondíveis com resultado conferido: 6/6 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 0
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 2 · respostas de reserva (texto determinístico): 2 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

### test (n=16)

- status final igual ao esperado: **5/16**
- respondíveis com resultado conferido: 5/5 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 8: T05→unsupported, T07→execution_error, T08→execution_error, T09→execution_error, T10→execution_error, T11→execution_error, T12→execution_error, T16→execution_error
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 1 · respostas de reserva (texto determinístico): 0 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: {'timeout': 1, 'circuit_open': 9}

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 11 | 0 | 0 | 0 | 11 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| D01 | dev | answered | answered | ok | 0 |  | ok |
| D02 | dev | answered | answered | ok | 0 |  | ok |
| D03 | dev | answered | answered | ok | 1 | sim | ok |
| D04 | dev | answered | answered | ok | 1 | sim | ok |
| D05 | dev | answered | answered | ok | 0 |  | ok |
| D06 | dev | needs_clarification | needs_clarification | — | 0 |  | — |
| D07 | dev | unsupported | unsupported | — | 0 |  | — |
| D08 | dev | no_results | no_results | ok | 0 |  | ok |
| T01 | test | answered | answered | ok | 0 |  | ok |
| T02 | test | answered | answered | ok | 0 |  | ok |
| T03 | test | answered | answered | ok | 1 |  | ok |
| T04 | test | answered | answered | ok | 0 |  | ok |
| T05 | test | answered | unsupported | — | 0 |  | — |
| T06 | test | answered | answered | ok | 0 |  | ok |
| T07 | test | answered | execution_error | — | 0 |  | — |
| T08 | test | no_results | execution_error | — | 0 |  | — |
| T09 | test | no_results | execution_error | — | 0 |  | — |
| T10 | test | answered | execution_error | — | 0 |  | — |
| T11 | test | answered | execution_error | — | 0 |  | — |
| T12 | test | answered | execution_error | — | 0 |  | — |
| T13 | test | needs_clarification | execution_error | — | 0 |  | — |
| T14 | test | unsupported | execution_error | — | 0 |  | — |
| T15 | test | unsupported | execution_error | — | 0 |  | — |
| T16 | test | answered | execution_error | — | 0 |  | — |
