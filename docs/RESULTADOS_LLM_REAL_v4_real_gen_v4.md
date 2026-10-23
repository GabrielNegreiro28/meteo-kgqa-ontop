# Resultados com LLM real

Modelo: `gpt-6-luna` · custo estimado: US$ 0.9355 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **real** (Ontop sobre PostgreSQL). Comparação com o oráculo independente.

### Todas (n=24)

- status final igual ao esperado: **22/24**
- respondíveis com resultado conferido: 15/18 corretas (das quais 0 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **2**: RG13, RG14
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **1**: RG18
- abstenções indevidas (pergunta respondível recusada): 1: RG16→unsupported
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 14 · respostas de reserva (texto determinístico): 4 · consultas montadas pelo compilador (não são acerto do LLM): 1
- erros de LLM: nenhum

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 14 | 0 | 0 | 2 | 12 |
| silent_wrong | 2 | 0 | 0 | 1 | 1 |
| surfaced_empty | 1 | 0 | 1 | 0 | 0 |
| surfaced_error | 1 | 0 | 1 | 0 | 0 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| RG01 | gen | answered | answered | ok | 2 | sim | ok |
| RG02 | gen | answered | answered | ok | 2 |  | ENTITY_MISMATCH |
| RG03 | gen | answered | answered | ok | 1 | sim | ok |
| RG04 | gen | answered | answered | ok | 1 |  | ok |
| RG05 | gen | answered | answered | ok | 0 |  | ok |
| RG06 | gen | answered | answered | ok | 0 |  | ok |
| RG07 | gen | answered | answered | ok | 0 |  | ok |
| RG08 | gen | answered | answered | ok | 0 |  | ok |
| RG09 | gen | answered | answered | ok | 0 |  | ok |
| RG10 | gen | answered | answered | ok | 2 | sim | ENTITY_MISMATCH |
| RG11 | gen | answered | answered | ok | 1 |  | ok |
| RG12 | gen | answered | answered | ok | 0 |  | ok |
| RG13 | gen | answered | answered | ERRADO | 1 |  | GROUPED_PROJECTION_EXPR,RELATION_DIRECTION |
| RG14 | gen | answered | answered | ERRADO | 0 |  | ok |
| RG15 | gen | answered | answered | ok | 0 |  | ok |
| RG16 | gen | answered | unsupported | — | 0 |  | — |
| RG17 | gen | answered | answered | ok | 1 | sim | ok |
| RG18 | gen | answered | no_results | ERRADO | 1 |  | PERIOD_MISMATCH |
| RG19 | gen | unsupported | unsupported | — | 0 |  | — |
| RG20 | gen | needs_clarification | needs_clarification | — | 0 |  | — |
| RG21 | gen | unsupported | unsupported | — | 0 |  | — |
| RG22 | gen | no_results | no_results | — | 0 |  | — |
| RG23 | gen | needs_clarification | needs_clarification | — | 0 |  | — |
| RG24 | gen | answered | answered | ok | 2 |  | RELATION_DIRECTION |
