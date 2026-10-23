# Resultados com LLM real

Modelo: `gpt-6-luna` · custo estimado: US$ 0.2648 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **sintético** (rdflib). Comparação com o oráculo independente.

### Todas (n=10)

- status final igual ao esperado: **3/10**
- respondíveis com resultado conferido: 1/6 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **5**: H01, H02, H03, H04, H08
- abstenções indevidas (pergunta respondível recusada): 2: H05→needs_clarification, H06→needs_clarification
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 1 · respostas de reserva (texto determinístico): 0
- erros de LLM: nenhum

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 1 | 0 | 0 | 1 | 0 |
| surfaced_empty | 5 | 0 | 0 | 0 | 5 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| H01 | heldout | answered | no_results | ERRADO | 0 |  | ok |
| H02 | heldout | answered | no_results | ERRADO | 0 |  | ok |
| H03 | heldout | answered | no_results | ERRADO | 0 |  | ok |
| H04 | heldout | answered | no_results | ERRADO | 0 |  | ok |
| H05 | heldout | answered | needs_clarification | — | 0 |  | — |
| H06 | heldout | answered | needs_clarification | — | 0 |  | — |
| H07 | heldout | answered | answered | ok | 1 |  | FORECAST_NOT_SELECTED |
| H08 | heldout | answered | no_results | ERRADO | 0 |  | ok |
| H09 | heldout | needs_clarification | needs_clarification | — | 0 |  | — |
| H10 | heldout | unsupported | unsupported | — | 0 |  | — |
