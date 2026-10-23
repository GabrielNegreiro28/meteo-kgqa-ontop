# Resultados com LLM real

Modelo: `gpt-6-luna` · custo estimado: US$ 0.5253 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **real** (Ontop sobre PostgreSQL). Comparação com o oráculo independente.

### Todas (n=16)

- status final igual ao esperado: **13/16**
- respondíveis com resultado conferido: 7/8 corretas (das quais 0 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **1**: RF01
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 3: RF03→unsupported, RF04→unsupported, RF06→execution_error
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 6 · respostas de reserva (texto determinístico): 1 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 7 | 0 | 0 | 0 | 7 |
| surfaced_empty | 1 | 0 | 1 | 0 | 0 |
| surfaced_error | 1 | 0 | 0 | 0 | 1 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| RF01 | fresh | answered | answered | ERRADO | 1 |  | UNKNOWN_IRI,RELATION_WITHOUT_DATA,PERIOD_MISMATCH |
| RF02 | fresh | answered | answered | ok | 0 |  | ok |
| RF03 | fresh | answered | unsupported | — | 0 |  | — |
| RF04 | fresh | answered | unsupported | — | 0 |  | — |
| RF05 | fresh | answered | answered | ok | 1 |  | ok |
| RF06 | fresh | answered | execution_error | — | 0 |  | ok |
| RF07 | fresh | answered | answered | ok | 1 | sim | ok |
| RF08 | fresh | answered | answered | ok | 0 |  | ok |
| RF09 | fresh | answered | answered | ok | 2 |  | ok |
| RF10 | fresh | answered | answered | ok | 0 |  | ok |
| RF11 | fresh | answered | answered | ok | 0 |  | ok |
| RF12 | fresh | unsupported | unsupported | — | 0 |  | — |
| RF13 | fresh | unsupported | unsupported | — | 0 |  | — |
| RF14 | fresh | no_results | no_results | — | 1 |  | — |
| RF15 | fresh | needs_clarification | needs_clarification | — | 0 |  | — |
| RF16 | fresh | unsupported | unsupported | — | 0 |  | — |
