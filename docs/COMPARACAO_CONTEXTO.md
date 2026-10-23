# Comparação de contexto: rótulos (A) × ontologia (B)

Gerado por `python -m eval.compare_runs`. Mesmo código de regras nas duas condições; muda só o contexto (e, em B, o prompt de geração sem o parágrafo escrito à mão). **Duas execuções por condição, 24 perguntas, um modelo**: leia as diferenças pequenas como ruído.

| métrica | A #1 | B #1 |
|---|---:|---:|
| status igual ao esperado | 12 | 12 |
| respondíveis corretas | 9 | 9 |
| respondíveis (n) | 9 | 12 |
| RESPOSTAS ERRADAS entregues | 0 | 0 |
| falsa ausência de registros | 0 | 3 |
| abstenções indevidas | 10 | 7 |
| respondeu o que devia esclarecer/recusar | 0 | 1 |
| 1ª tentativa de consulta correta | 9 | 10 |
| 1ª tentativa errada (n) | 3 | 3 |
|   das quais barradas pelas regras | 3 | 1 |
| reparos | 6 | 6 |
| respostas de reserva | 0 | 0 |
| custo (US$) | 0.403 | 0.714 |

## Por pergunta (status final em cada execução; ✔ resultado conferido, ✘ resultado errado)

| id | esperado | A#1 | B#1 |
|---|---|---|---|
| D01 | answered | answered ✔ | answered ✔ |
| D02 | answered | answered ✔ | no_results ✘ |
| D03 | answered | answered ✔ | answered ✔ |
| D04 | answered | answered ✔ | no_results ✘ |
| D05 | answered | rejected | answered ✔ |
| D06 | needs_clarification | needs_clarification | no_results |
| D07 | unsupported | needs_clarification | unsupported |
| D08 | no_results | no_results ✔ | no_results ✔ |
| T01 | answered | answered ✔ | answered ✔ |
| T02 | answered | answered ✔ | answered ✔ |
| T03 | answered | answered ✔ | answered ✔ |
| T04 | answered | answered ✔ | answered ✔ |
| T05 | answered | needs_clarification | needs_clarification |
| T06 | answered | rejected | answered ✔ |
| T07 | answered | needs_clarification | no_results ✘ |
| T08 | no_results | needs_clarification | needs_clarification |
| T09 | no_results | needs_clarification | needs_clarification |
| T10 | answered | rejected | rejected |
| T11 | answered | needs_clarification | needs_clarification |
| T12 | answered | needs_clarification | needs_clarification |
| T13 | needs_clarification | needs_clarification | needs_clarification |
| T14 | unsupported | needs_clarification | unsupported |
| T15 | unsupported | unsupported | needs_clarification |
| T16 | answered | needs_clarification | needs_clarification |

## Achados das regras na 1ª tentativa do modelo (todas as execuções da condição)

| condição | códigos (contagem) |
|---|---|
| A | TYPE_CLASH×2, PERIOD_MISMATCH×2, UNKNOWN_IRI×1, CLASS_WITHOUT_DIRECT_INSTANCES×1, FORECAST_NOT_SELECTED×1 |
| B | ENTITY_MISMATCH×1, PERIOD_MISMATCH×1 |
