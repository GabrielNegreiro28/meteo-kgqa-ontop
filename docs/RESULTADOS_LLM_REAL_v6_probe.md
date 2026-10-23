# Resultados com LLM real

Modelo: `gpt-6-luna` · custo estimado: US$ 0.3370 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **real** (Ontop sobre PostgreSQL). Comparação com o oráculo independente.

### Todas (n=8)

- status final igual ao esperado: **8/8**
- respondíveis com resultado conferido: 6/6 corretas (das quais 0 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 0
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 5 · respostas de reserva (texto determinístico): 0 · consultas montadas pelo compilador (não são acerto do LLM): 2
- erros de LLM: nenhum

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
| RP01 | probe | answered | answered | ok | 0 |  | ok |
| RP02 | probe | answered | answered | ok | 1 |  | RELATION_DIRECTION,TYPE_CLASH,TYPE_CLASH |
| RP03 | probe | answered | answered | ok | 0 |  | ok |
| RP04 | probe | unsupported | unsupported | — | 1 |  | — |
| RP05 | probe | answered | answered | ok | 0 |  | ok |
| RP06 | probe | unsupported | unsupported | — | 0 |  | — |
| RP07 | probe | answered | answered | ok | 3 |  | TYPE_CLASH,TYPE_CLASH |
| RP08 | probe | answered | answered | ok | 0 |  | ok |
