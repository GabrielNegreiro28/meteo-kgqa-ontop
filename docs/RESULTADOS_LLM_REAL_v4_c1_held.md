# Resultados com LLM real

Modelo: `gpt-6-luna` · custo estimado: US$ 0.3118 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **sintético** (rdflib). Comparação com o oráculo independente.

### Todas (n=10)

- status final igual ao esperado: **8/10**
- respondíveis com resultado conferido: 6/6 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 2: H05→needs_clarification, H07→unsupported
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 8 · respostas de reserva (texto determinístico): 0 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: {'invalid_output': 3}

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 2 | 0 | 0 | 1 | 1 |
| surfaced_empty | 4 | 0 | 4 | 0 | 0 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| H01 | heldout | answered | answered | ok | 2 |  | TYPE_CLASH |
| H02 | heldout | answered | answered | ok | 1 |  | ok |
| H03 | heldout | answered | answered | ok | 1 |  | TYPE_CLASH |
| H04 | heldout | answered | answered | ok | 1 |  | TYPE_CLASH |
| H05 | heldout | answered | needs_clarification | — | 0 |  | — |
| H06 | heldout | answered | answered | ok | 1 |  | ENTITY_MISMATCH |
| H07 | heldout | answered | unsupported | — | 0 |  | — |
| H08 | heldout | answered | answered | ok | 2 |  | TYPE_CLASH |
| H09 | heldout | needs_clarification | needs_clarification | — | 0 |  | — |
| H10 | heldout | unsupported | unsupported | — | 0 |  | — |
