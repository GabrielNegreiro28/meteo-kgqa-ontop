# Resultados com LLM real

Modelo: `gpt-6-luna` · custo estimado: US$ 0.2596 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **real** (Ontop sobre PostgreSQL). Comparação com o oráculo independente.

### Todas (n=8)

- status final igual ao esperado: **7/8**
- respondíveis com resultado conferido: 4/4 corretas (das quais 1 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 0
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 1: RD07
- reparos usados: 3 · respostas de reserva (texto determinístico): 0 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

### dev (n=8)

- status final igual ao esperado: **7/8**
- respondíveis com resultado conferido: 4/4 corretas (das quais 1 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 0
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 1: RD07
- reparos usados: 3 · respostas de reserva (texto determinístico): 0 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 3 | 0 | 0 | 0 | 3 |
| surfaced_empty | 1 | 0 | 0 | 1 | 0 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| RD01 | dev | answered | answered | ok | 0 |  | ok |
| RD02 | dev | answered | answered | ok | 1 |  | ok |
| RD03 | dev | answered | answered | ok | 0 |  | ok |
| RD04 | dev | answered | answered | ok | 1 |  | ENTITY_MISMATCH |
| RD05 | dev | needs_clarification | needs_clarification | — | 0 |  | — |
| RD06 | dev | unsupported | unsupported | — | 0 |  | — |
| RD07 | dev | unsupported | answered | — | 1 |  | ok |
| RD08 | dev | no_results | no_results | — | 0 |  | — |
