# Resultados com LLM real

Modelo: `gpt-6-luna (prompts v1)` · custo estimado: US$ 0.1775 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **sintético** (rdflib). Comparação com o oráculo independente.

### Todas (n=10)

- status final igual ao esperado: **6/10**
- respondíveis com resultado conferido: 4/4 corretas (das quais 0 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 4: H02→rejected, H04→needs_clarification, H07→unsupported, H08→rejected
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 3 · respostas de reserva (texto determinístico): 0 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: {'invalid_output': 1}

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 4 | 0 | 0 | 0 | 4 |
| surfaced_empty | 2 | 0 | 2 | 0 | 0 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| H01 | heldout | answered | answered | ok | 1 |  | ok |
| H02 | heldout | answered | rejected | — | 1 |  | TYPE_CLASH,PERIOD_MISMATCH |
| H03 | heldout | answered | answered | ok | 0 |  | ok |
| H04 | heldout | answered | needs_clarification | — | 0 |  | — |
| H05 | heldout | answered | answered | ok | 0 |  | ok |
| H06 | heldout | answered | answered | ok | 0 |  | ok |
| H07 | heldout | answered | unsupported | — | 0 |  | — |
| H08 | heldout | answered | rejected | — | 1 |  | TYPE_CLASH,PERIOD_MISMATCH |
| H09 | heldout | needs_clarification | needs_clarification | — | 0 |  | — |
| H10 | heldout | unsupported | unsupported | — | 0 |  | — |
