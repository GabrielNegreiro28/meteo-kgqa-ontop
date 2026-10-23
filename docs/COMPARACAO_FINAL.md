# Comparação final: A (v1, só rótulos) × C (v4, revisão crítica) — 44 perguntas, 3 suítes

Gerado por `python -m eval.compare_runs`. Mesmo código de regras de consulta nas condições; muda o contexto/prompt/etapas. **Poucas execuções, poucas perguntas, um modelo**: leia as diferenças pequenas como ruído.

| métrica | A_v1 #1 | C_v4 #1 |
|---|---:|---:|
| status igual ao esperado | 23 | 41 |
| respondíveis corretas | 16 | 29 |
|   das quais incompletas (valor certo, falta coluna exigida) | 0 | 1 |
|   das quais em outra ordem | 0 | 1 |
| respondíveis (n) | 17 | 30 |
| RESPOSTAS ERRADAS entregues | 1 | 1 |
| falsa ausência de registros | 0 | 0 |
| abstenções indevidas | 17 | 3 |
| respondeu o que devia esclarecer/recusar | 2 | 0 |
| 1ª tentativa de consulta correta | 16 | 27 |
| 1ª tentativa errada (n) | 7 | 3 |
|   das quais barradas pelas regras | 6 | 2 |
| reparos | 14 | 8 |
| respostas de reserva | 3 | 1 |
| consultas montadas pelo compilador | 0 | 0 |
| custo (US$) | 0.779 | 1.171 |

## Por pergunta (status final em cada execução; ✔ resultado conferido, ✘ resultado errado)

| id | esperado | A_v1#1 | C_v4#1 |
|---|---|---|---|
| G01 | answered | answered ✔ | answered ✔ |
| G02 | answered | rejected | answered ✔ |
| G03 | answered | answered ✘ | answered ✔ |
| G04 | no_results | no_results ✔ | no_results |
| G05 | answered | answered ✔ | answered ✔ |
| G06 | answered | needs_clarification | answered ✔ |
| G07 | unsupported | needs_clarification | unsupported |
| G08 | needs_clarification | no_results | needs_clarification |
| G09 | unsupported | unsupported | unsupported |
| G10 | answered | answered ✔ | answered ✔ |
| D01 | answered | answered ✔ | answered ✔ |
| D02 | answered | needs_clarification | answered ✔ |
| D03 | answered | answered ✔ | answered ✔ |
| D04 | answered | answered ✔ | answered ✔ |
| D05 | answered | rejected | answered ✔ |
| D06 | needs_clarification | needs_clarification | needs_clarification |
| D07 | unsupported | needs_clarification | unsupported |
| D08 | no_results | needs_clarification | no_results ✔ |
| T01 | answered | answered ✔ | answered ✔ |
| T02 | answered | answered ✔ | answered ✔ |
| T03 | answered | answered ✔ | answered ✔ |
| T04 | answered | answered ✔ | answered ✔ |
| T05 | answered | needs_clarification | unsupported |
| T06 | answered | rejected | answered ✔ |
| T07 | answered | needs_clarification | answered ✔ |
| T08 | no_results | needs_clarification | no_results ✔ |
| T09 | no_results | no_results ✔ | no_results ✔ |
| T10 | answered | rejected | answered ✔ |
| T11 | answered | needs_clarification | needs_clarification |
| T12 | answered | needs_clarification | answered ✔ |
| T13 | needs_clarification | needs_clarification | needs_clarification |
| T14 | unsupported | no_results | unsupported |
| T15 | unsupported | unsupported | unsupported |
| T16 | answered | needs_clarification | answered ✔ |
| H01 | answered | answered ✔ | answered ✔ |
| H02 | answered | rejected | answered ✘ |
| H03 | answered | answered ✔ | answered ✔ |
| H04 | answered | needs_clarification | answered ✔ |
| H05 | answered | answered ✔ | answered ✔ |
| H06 | answered | answered ✔ | answered ✔ |
| H07 | answered | unsupported | unsupported |
| H08 | answered | rejected | answered ✔ |
| H09 | needs_clarification | needs_clarification | needs_clarification |
| H10 | unsupported | unsupported | unsupported |

## Achados das regras na 1ª tentativa do modelo (todas as execuções da condição)

| condição | códigos (contagem) |
|---|---|
| A_v1 | TYPE_CLASH×5, PERIOD_MISMATCH×5, UNKNOWN_IRI×1, CLASS_WITHOUT_DIRECT_INSTANCES×1, FORECAST_NOT_SELECTED×1 |
| C_v4 | TYPE_CLASH×8, ENTITY_MISMATCH×1, UNSUPPORTED_FUNCTION×1, FORECAST_NOT_SELECTED×1 |
