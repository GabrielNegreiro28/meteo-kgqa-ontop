# Resultados com LLM real

Modelo: `gpt-6-luna` · custo estimado: US$ 0.2310 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **real** (Ontop sobre PostgreSQL). Comparação com o oráculo independente.

### Todas (n=8)

- status final igual ao esperado: **6/8**
- respondíveis com resultado conferido: 2/3 corretas (das quais 0 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **1**: RD02
- abstenções indevidas (pergunta respondível recusada): 1: RD03→execution_error
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 1 · respostas de reserva (texto determinístico): 0 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

### dev (n=8)

- status final igual ao esperado: **6/8**
- respondíveis com resultado conferido: 2/3 corretas (das quais 0 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **1**: RD02
- abstenções indevidas (pergunta respondível recusada): 1: RD03→execution_error
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 1 · respostas de reserva (texto determinístico): 0 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 3 | 0 | 0 | 1 | 2 |
| surfaced_error | 1 | 0 | 0 | 0 | 1 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| RD01 | dev | answered | answered | ok | 0 |  | ok |
| RD02 | dev | answered | no_results | ERRADO | 1 |  | PERIOD_MIXED_FORMS |
| RD03 | dev | answered | execution_error | — | 0 |  | ok |
| RD04 | dev | answered | answered | ok | 0 |  | ok |
| RD05 | dev | needs_clarification | needs_clarification | — | 0 |  | — |
| RD06 | dev | unsupported | unsupported | — | 0 |  | — |
| RD07 | dev | unsupported | unsupported | — | 0 |  | — |
| RD08 | dev | no_results | no_results | — | 0 |  | — |
