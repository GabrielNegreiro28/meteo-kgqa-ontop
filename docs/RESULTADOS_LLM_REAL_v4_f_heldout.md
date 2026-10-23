# Resultados com LLM real

Modelo: `gpt-6-luna (prompts v4)` · custo estimado: US$ 0.2701 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **sintético** (rdflib). Comparação com o oráculo independente.

### Todas (n=10)

- status final igual ao esperado: **9/10**
- respondíveis com resultado conferido: 6/7 corretas (das quais 0 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **1**: H02
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 1: H07→unsupported
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 1 · respostas de reserva (texto determinístico): 0 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 6 | 0 | 1 | 0 | 5 |
| silent_wrong | 1 | 0 | 0 | 0 | 1 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| H01 | heldout | answered | answered | ok | 0 |  | ok |
| H02 | heldout | answered | answered | ERRADO | 0 |  | ok |
| H03 | heldout | answered | answered | ok | 0 |  | ok |
| H04 | heldout | answered | answered | ok | 0 |  | ok |
| H05 | heldout | answered | answered | ok | 1 |  | TYPE_CLASH,TYPE_CLASH |
| H06 | heldout | answered | answered | ok | 0 |  | ok |
| H07 | heldout | answered | unsupported | — | 0 |  | — |
| H08 | heldout | answered | answered | ok | 0 |  | ok |
| H09 | heldout | needs_clarification | needs_clarification | — | 0 |  | — |
| H10 | heldout | unsupported | unsupported | — | 0 |  | — |
