# Resultados com LLM real

Modelo: `gpt-6-luna` · custo estimado: US$ 0.3216 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **sintético** (rdflib). Comparação com o oráculo independente.

### Todas (n=10)

- status final igual ao esperado: **7/10**
- respondíveis com resultado conferido: 5/7 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **2**: H03, H08
- abstenções indevidas (pergunta respondível recusada): 1: H05→unsupported
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 3 · respostas de reserva (texto determinístico): 0
- erros de LLM: {'invalid_output': 1}

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 4 | 0 | 0 | 1 | 3 |
| silent_wrong | 1 | 0 | 0 | 1 | 0 |
| surfaced_empty | 2 | 0 | 0 | 0 | 2 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| H01 | heldout | answered | answered | ok | 1 |  | ok |
| H02 | heldout | answered | answered | ok | 1 |  | PERIOD_MISMATCH |
| H03 | heldout | answered | no_results | ERRADO | 0 |  | ok |
| H04 | heldout | answered | answered | ok | 0 |  | ok |
| H05 | heldout | answered | unsupported | — | 0 |  | — |
| H06 | heldout | answered | answered | ok | 0 |  | ok |
| H07 | heldout | answered | answered | ok | 1 |  | FORECAST_NOT_SELECTED |
| H08 | heldout | answered | no_results | ERRADO | 0 |  | ok |
| H09 | heldout | needs_clarification | needs_clarification | — | 0 |  | — |
| H10 | heldout | unsupported | unsupported | — | 0 |  | — |
