# Resultados com LLM real

Modelo: `gpt-6-luna (prompts v1)` · custo estimado: US$ 0.1941 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **sintético** (rdflib). Comparação com o oráculo independente.

### Todas (n=10)

- status final igual ao esperado: **6/10**
- respondíveis com resultado conferido: 4/5 corretas (das quais 0 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **1**: G03
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 2: G02→rejected, G06→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 1: G08
- reparos usados: 4 · respostas de reserva (texto determinístico): 1 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: {'invalid_output': 3}

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 4 | 0 | 0 | 0 | 4 |
| silent_wrong | 1 | 0 | 0 | 0 | 1 |
| surfaced_empty | 1 | 0 | 1 | 0 | 0 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| G01 | fresh | answered | answered | ok | 1 |  | ok |
| G02 | fresh | answered | rejected | — | 1 |  | TYPE_CLASH,PERIOD_MISMATCH |
| G03 | fresh | answered | answered | ERRADO | 1 | sim | ok |
| G04 | fresh | no_results | no_results | ok | 0 |  | ok |
| G05 | fresh | answered | answered | ok | 0 |  | ok |
| G06 | fresh | answered | needs_clarification | — | 0 |  | — |
| G07 | fresh | unsupported | needs_clarification | — | 0 |  | — |
| G08 | fresh | needs_clarification | no_results | — | 0 |  | ok |
| G09 | fresh | unsupported | unsupported | — | 0 |  | — |
| G10 | fresh | answered | answered | ok | 1 |  | ok |
