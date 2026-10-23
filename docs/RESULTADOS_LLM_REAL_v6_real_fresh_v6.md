# Resultados com LLM real

Modelo: `gpt-6-luna` · custo estimado: US$ 0.2927 · gerado por `python -m eval.run_llm_pipeline`.

Parâmetros recusados pelo modelo e removidos: ['response_format']

Resultados sobre o grafo **real** (Ontop sobre PostgreSQL). Comparação com o oráculo independente.

### Todas (n=16)

- status final igual ao esperado: **16/16**
- respondíveis com resultado conferido: 11/11 corretas (das quais 0 incompletas — faltam colunas que a referência pede — e 0 em outra ordem)
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
| correct | 11 | 0 | 0 | 0 | 11 |

`correct` barradas = falsos positivos das regras (consulta certa recusada na primeira tentativa).

## Por pergunta

| id | split | esperado | obtido | resultado | reparos | reserva | 1ª tentativa |
|---|---|---|---|---|---|---|---|
| RF01 | fresh | answered | answered | ok | 0 |  | ok |
| RF02 | fresh | answered | answered | ok | 0 |  | ok |
| RF03 | fresh | answered | answered | ok | 0 |  | ok |
| RF04 | fresh | answered | answered | ok | 0 |  | ok |
| RF05 | fresh | answered | answered | ok | 0 |  | ok |
| RF06 | fresh | answered | answered | ok | 0 |  | ok |
| RF07 | fresh | answered | answered | ok | 0 |  | ok |
| RF08 | fresh | answered | answered | ok | 0 |  | ok |
| RF09 | fresh | answered | answered | ok | 1 |  | ok |
| RF10 | fresh | answered | answered | ok | 0 |  | ok |
| RF11 | fresh | answered | answered | ok | 0 |  | ok |
| RF12 | fresh | unsupported | unsupported | — | 0 |  | — |
| RF13 | fresh | unsupported | unsupported | — | 0 |  | — |
| RF14 | fresh | no_results | no_results | — | 0 |  | — |
| RF15 | fresh | needs_clarification | needs_clarification | — | 0 |  | — |
| RF16 | fresh | unsupported | unsupported | — | 0 |  | — |
