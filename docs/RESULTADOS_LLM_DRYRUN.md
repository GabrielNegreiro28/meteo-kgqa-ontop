# Resultados com LLM roteirizado (dry-run)

Modelo: `dry-run (LLM roteirizado)` · custo estimado: US$ 0.0000 · gerado por `python -m eval.run_llm_pipeline`.

Resultados sobre o grafo **sintético** (rdflib). Comparação com o oráculo independente.

### Todas (n=9)

- status final igual ao esperado: **9/9**
- respondíveis com resultado conferido: 9/9 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 0
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 8 · respostas de reserva (texto determinístico): 8 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

### dev (n=3)

- status final igual ao esperado: **3/3**
- respondíveis com resultado conferido: 3/3 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 0
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 3 · respostas de reserva (texto determinístico): 3 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

### test (n=6)

- status final igual ao esperado: **6/6**
- respondíveis com resultado conferido: 6/6 corretas
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **0**
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **0**
- abstenções indevidas (pergunta respondível recusada): 0
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 0
- reparos usados: 5 · respostas de reserva (texto determinístico): 5 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 9 | 0 | 0 | 0 | 9 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| D03 | dev | answered | answered | ok | 1 | sim | ok |
| D04 | dev | answered | answered | ok | 1 | sim | ok |
| D05 | dev | answered | answered | ok | 1 | sim | ok |
| T03 | test | answered | answered | ok | 1 | sim | ok |
| T04 | test | answered | answered | ok | 1 | sim | ok |
| T06 | test | answered | answered | ok | 1 | sim | ok |
| T07 | test | answered | answered | ok | 1 | sim | ok |
| T08 | test | no_results | no_results | ok | 0 |  | ok |
| T11 | test | answered | answered | ok | 1 | sim | ok |
