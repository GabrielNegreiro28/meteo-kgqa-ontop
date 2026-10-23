# Resultados com LLM real

Modelo: `gpt-6-luna` · custo estimado: US$ 0.3365 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **real** (Ontop sobre PostgreSQL). Comparação com o oráculo independente.

### Todas (n=12)

- status final igual ao esperado: **7/12**
- respondíveis com resultado conferido: 5/6 corretas (das quais 0 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **1**: RT12
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 4: RT01→unsupported, RT02→unsupported, RT04→unsupported, RT05→unsupported
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 5 · respostas de reserva (texto determinístico): 3 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

### test (n=12)

- status final igual ao esperado: **7/12**
- respondíveis com resultado conferido: 5/6 corretas (das quais 0 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **1**: RT12
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 4: RT01→unsupported, RT02→unsupported, RT04→unsupported, RT05→unsupported
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 5 · respostas de reserva (texto determinístico): 3 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 5 | 0 | 0 | 0 | 5 |
| silent_wrong | 1 | 0 | 0 | 0 | 1 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| RT01 | test | answered | unsupported | — | 0 |  | — |
| RT02 | test | answered | unsupported | — | 0 |  | — |
| RT03 | test | answered | answered | ok | 1 | sim | ok |
| RT04 | test | answered | unsupported | — | 0 |  | — |
| RT05 | test | answered | unsupported | — | 0 |  | — |
| RT06 | test | answered | answered | ok | 0 |  | ok |
| RT07 | test | answered | answered | ok | 0 |  | ok |
| RT08 | test | answered | answered | ok | 1 | sim | ok |
| RT09 | test | answered | answered | ok | 2 | sim | ok |
| RT10 | test | unsupported | needs_clarification | — | 0 |  | — |
| RT11 | test | needs_clarification | needs_clarification | — | 0 |  | — |
| RT12 | test | answered | answered | ERRADO | 1 |  | ok |
