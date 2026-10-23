# Resultados com LLM real

Modelo: `gpt-6-luna (prompts v4)` · custo estimado: US$ 0.2098 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **sintético** (rdflib). Comparação com o oráculo independente.

### Todas (n=10)

- status final igual ao esperado: **10/10**
- respondíveis com resultado conferido: 6/6 corretas (das quais 0 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 0
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 1 · respostas de reserva (texto determinístico): 0 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 6 | 0 | 0 | 0 | 6 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| G01 | fresh | answered | answered | ok | 0 |  | ok |
| G02 | fresh | answered | answered | ok | 0 |  | ok |
| G03 | fresh | answered | answered | ok | 0 |  | ok |
| G04 | fresh | no_results | no_results | — | 0 |  | — |
| G05 | fresh | answered | answered | ok | 0 |  | ok |
| G06 | fresh | answered | answered | ok | 0 |  | ok |
| G07 | fresh | unsupported | unsupported | — | 0 |  | — |
| G08 | fresh | needs_clarification | needs_clarification | — | 0 |  | — |
| G09 | fresh | unsupported | unsupported | — | 0 |  | — |
| G10 | fresh | answered | answered | ok | 1 |  | ok |
