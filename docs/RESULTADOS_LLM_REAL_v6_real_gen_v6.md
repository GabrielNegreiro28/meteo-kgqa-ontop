# Resultados com LLM real

Modelo: `gpt-6-luna` · custo estimado: US$ 0.8001 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **real** (Ontop sobre PostgreSQL). Comparação com o oráculo independente.

### Todas (n=23)

- status final igual ao esperado: **20/23**
- respondíveis com resultado conferido: 14/17 corretas (das quais 0 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
- **respostas ERRADAS entregues** (answered com resultado ≠ oráculo): **2**: RG17, RG18
- **falsa ausência de registros** (disse 'não há registros' onde há dados): **1**: RG09
- abstenções indevidas (pergunta respondível recusada): 1: RG11→unsupported
- respostas a perguntas que deveriam ser recusadas/esclarecidas: 1: RG19
- reparos usados: 10 · respostas de reserva (texto determinístico): 3 · consultas montadas pelo compilador (não são acerto do LLM): 0
- erros de LLM: nenhum

## Ablação sobre a primeira tentativa do modelo

Cada primeira consulta gerada foi executada **sem** regras para saber o que chegaria ao usuário.

| Verdade sem validação | n | barradas por L1 | por L2 | por L3 | passaram |
|---|---:|---:|---:|---:|---:|
| correct | 13 | 0 | 0 | 0 | 13 |
| silent_wrong | 2 | 0 | 0 | 0 | 2 |
| surfaced_empty | 2 | 0 | 1 | 0 | 1 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| RG01 | gen | answered | answered | ok | 1 |  | RELATION_DIRECTION |
| RG02 | gen | answered | answered | ok | 0 |  | ok |
| RG03 | gen | answered | answered | ok | 1 | sim | ok |
| RG04 | gen | answered | answered | ok | 2 | sim | ok |
| RG05 | gen | answered | answered | ok | 0 |  | ok |
| RG06 | gen | answered | answered | ok | 0 |  | ok |
| RG07 | gen | answered | answered | ok | 0 |  | ok |
| RG08 | gen | answered | answered | ok | 0 |  | ok |
| RG09 | gen | answered | no_results | ERRADO | 1 |  | ok |
| RG10 | gen | answered | answered | ok | 1 | sim | ok |
| RG11 | gen | answered | unsupported | — | 1 |  | — |
| RG12 | gen | answered | answered | ok | 0 |  | ok |
| RG13 | gen | answered | answered | ok | 0 |  | ok |
| RG14 | gen | answered | answered | ok | 0 |  | ok |
| RG15 | gen | answered | answered | ok | 0 |  | ok |
| RG16 | gen | answered | answered | ok | 0 |  | ok |
| RG17 | gen | answered | answered | ERRADO | 1 |  | ok |
| RG18 | gen | answered | answered | ERRADO | 1 |  | ok |
| RG19 | gen | unsupported | answered | — | 1 |  | ok |
| RG20 | gen | needs_clarification | needs_clarification | — | 0 |  | — |
| RG21 | gen | unsupported | unsupported | — | 0 |  | — |
| RG22 | gen | no_results | no_results | — | 0 |  | — |
| RG23 | gen | needs_clarification | needs_clarification | — | 0 |  | — |
