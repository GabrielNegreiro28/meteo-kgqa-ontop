# Julgamento humano: conjunto `novo_a`

31 perguntas em que alguma condição não bateu automaticamente com a referência. Condições: v4, v5_v1, v5_v2, v7.
`diverge` não é erro: pode ser erro do sistema, erro do oráculo ou diferença de limpeza declarada. Dê um veredito por pergunta (o mesmo vale para todas as condições que deram o mesmo valor) no arquivo de vereditos.

## E05 · simples · esperado `answerable`

**Pergunta:** Quantos minutos de chuva, somando todas as horas, foram registrados em SBFZ em 2020?

**Referência (oráculo):** (13959.0)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Para grandezas acumuladas/contadas por hora usa só boletins na hora cheia (minuto 0). Descartei durpreci fora de [0, 60] min; vazios ignorados (vazio não é zero).

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (1566.2, 8686.0) |
| v5_v1 | answered | diverge | (1566.2, 8686.0) |
| v5_v2 | answered | diverge | (1566.2, 8686.0) |
| v7 | answered | diverge | (1566.2, 8686.0) |

Nota automática: 1 de 1 números da referência sem par na resposta: [13959.0]

## E07 · simples · esperado `answerable`

**Pergunta:** Qual foi a visibilidade mínima, em metros, em SBGL no dia 15 de fevereiro de 2024?

**Referência (oráculo):** (1000.0)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. visibpre está em dezenas de metros, multipliquei por 10; descartei valores fora de [0, 2000]; todos os boletins do dia entram.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (500.0, 707.0) |
| v5_v1 | answered | diverge | (500.0, 707.0) |
| v5_v2 | rejected | abstained | — |
| v7 | rejected | abstained | — |

Nota automática: 1 de 1 números da referência sem par na resposta: [1000.0]

## E10 · simples · esperado `answerable`

**Pergunta:** Qual a menor altura de base de nuvem, em metros, vista em SBBR em janeiro de 2020?

**Referência (oráculo):** (30.0)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. altnuvem em dezenas de metros, multipliquei por 10; considerei só altnuvem entre 1 e 2000 (descarta zero e valores impossíveis); uma linha por camada, o mínimo não depende disso.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | unsupported | abstained | — |
| v5_v1 | unsupported | abstained | — |
| v5_v2 | unsupported | abstained | — |
| v7 | unsupported | abstained | — |

## E11 · simples · esperado `answerable`

**Pergunta:** Qual foi a temperatura máxima do ar em SBGO em 14 de outubro de 2019?

**Referência (oráculo):** (35.4)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Descartei bseco fora de [-10, 50] °C; todos os boletins do dia.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (36.5, 769.0) |
| v5_v1 | answered | diverge | (36.5, 769.0) |
| v5_v2 | answered | diverge | (36.5, 769.0) |
| v7 | answered | diverge | (36.5, 769.0) |

Nota automática: 1 de 1 números da referência sem par na resposta: [35.4]

## E13 · condicao · esperado `answerable`

**Pergunta:** Em quantas horas a visibilidade em SBSP ficou abaixo de 1000 metros em 2018?

**Referência (oráculo):** (7)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Para grandezas acumuladas/contadas por hora usa só boletins na hora cheia (minuto 0). visibpre em dezenas de metros: < 1000 m equivale a visibpre < 100; descartei valores fora de [0, 2000].

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (14.0) |
| v5_v1 | answered | diverge | (14.0) |
| v5_v2 | answered | diverge | (14.0) |
| v7 | answered | diverge | (14.0) |

Nota automática: 1 de 1 números da referência sem par na resposta: [7.0]

## E14 · condicao · esperado `answerable`

**Pergunta:** Em quantos dias de 2020 a temperatura máxima em SBBR chegou a 33 °C ou mais?

**Referência (oráculo):** (18)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Máxima diária = maior bseco do dia civil local entre todos os boletins; descartei bseco fora de [-10, 50] °C.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | rejected | abstained | — |
| v5_v1 | rejected | abstained | — |
| v5_v2 | rejected | abstained | — |
| v7 | answered | match | (18.0, 362.0) |

## E15 · condicao · esperado `answerable`

**Pergunta:** Quantas horas com chuva houve em SBCY em 2022?

**Referência (oráculo):** (360)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Para grandezas acumuladas/contadas por hora usa só boletins na hora cheia (minuto 0). Hora com chuva = precip > 0; descartei precip fora de [0, 200] mm.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (8691.0) |
| v5_v1 | answered | diverge | (8691.0) |
| v5_v2 | answered | diverge | (8691.0) |
| v7 | needs_clarification | abstained | — |

Nota automática: 1 de 1 números da referência sem par na resposta: [360.0]

## E16 · condicao · esperado `answerable`

**Pergunta:** Quantas vezes o vento passou de 15 nós em SBNF em 2017?

**Referência (oráculo):** (147)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Contei boletins (instantes distintos), não linhas por cabeceira: um instante conta se alguma cabeceira passou de 15 nós; descartei velvento fora de [0, 100].

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (209.0) |
| v5_v1 | answered | diverge | (209.0) |
| v5_v2 | answered | diverge | (209.0) |
| v7 | answered | diverge | (209.0) |

Nota automática: 1 de 1 números da referência sem par na resposta: [147.0]

## E17 · condicao · esperado `answerable`

**Pergunta:** Quantas horas o QNH em SBVT ficou abaixo de 1010 hPa em 2019?

**Referência (oráculo):** (294)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Para grandezas acumuladas/contadas por hora usa só boletins na hora cheia (minuto 0). Descartei qnh fora de [850, 1100] hPa.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (302.0) |
| v5_v1 | answered | diverge | (302.0) |
| v5_v2 | answered | diverge | (302.0) |
| v7 | answered | diverge | (302.0) |

Nota automática: 1 de 1 números da referência sem par na resposta: [294.0]

## E18 · condicao · esperado `answerable`

**Pergunta:** Em quantos dias de 2021 a temperatura mínima em SBCT ficou abaixo de 8 °C?

**Referência (oráculo):** (35)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Mínima diária = menor bseco do dia civil local; descartei bseco fora de [-10, 50] °C.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | rejected | abstained | — |
| v5_v1 | rejected | abstained | — |
| v5_v2 | execution_error | abstained | — |
| v7 | answered | match | (35.0, 351.0) |

## E19 · condicao · esperado `answerable`

**Pergunta:** Quantas horas de agosto de 2024 em SBBR tiveram umidade relativa abaixo de 20%?

**Referência (oráculo):** (131)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Para grandezas acumuladas/contadas por hora usa só boletins na hora cheia (minuto 0). Descartei ur fora de [0, 100] %.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (74.0) |
| v5_v1 | answered | diverge | (74.0) |
| v5_v2 | answered | diverge | (74.0) |
| v7 | answered | diverge | (74.0) |

Nota automática: 1 de 1 números da referência sem par na resposta: [131.0]

## E20 · condicao · esperado `answerable`

**Pergunta:** Em quantas horas de 2016 SBPA teve nuvens cobrindo 5 oitavos ou mais com base abaixo de 300 metros?

**Referência (oráculo):** (970)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Para grandezas acumuladas/contadas por hora usa só boletins na hora cheia (minuto 0). altnuvem em dezenas de metros: < 300 m equivale a altnuvem < 30 (com altnuvem >= 1); qtdnuvem convertida para número, vazio/não numérico descartado; contei horas distintas (não camadas).

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | unsupported | abstained | — |
| v5_v1 | unsupported | abstained | — |
| v5_v2 | unsupported | abstained | — |
| v7 | unsupported | abstained | — |

## E21 · serie_ranking · esperado `answerable`

**Pergunta:** Qual foi a temperatura média de cada mês de 2019 em SBFL?

**Referência (oráculo):** (1, 27.22); (2, 24.75); (3, 24.34); (4, 23.32) … +8 linhas

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Descartei bseco fora de [-10, 50] °C; média de todos os boletins de cada mês.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (2019-09, 18.507, 757.0); (2019-08, 17.529, 753.0); (2019-11, 22.541, 749.0); (2019-05, 21.36, 790.0) … +8 linhas |
| v5_v1 | answered | match | (2.0, 24.749, 737.0); (9.0, 18.507, 757.0); (3.0, 24.345, 767.0); (11.0, 22.541, 749.0) … +8 linhas |
| v5_v2 | answered | diverge | (2019-09, 18.507, 757.0); (2019-08, 17.529, 753.0); (2019-11, 22.541, 749.0); (2019-05, 21.36, 790.0) … +8 linhas |
| v7 | answered | match | (2019.0, 1.0, 27.217, 789.0); (2019.0, 2.0, 24.749, 737.0); (2019.0, 3.0, 24.345, 767.0); (2019.0, 4.0, 23.317, 746.0) … +8 linhas |

Nota automática: 12 de 24 números da referência sem par na resposta: [1.0, 2.0, 3.0, 4.0, 5.0]

## E22 · serie_ranking · esperado `answerable`

**Pergunta:** Quanto choveu por ano em SBRJ de 2016 a 2025?

**Referência (oráculo):** (2016, 920.8); (2017, 745.6); (2018, 945.4); (2019, 1114.2) … +6 linhas

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Para grandezas acumuladas/contadas por hora usa só boletins na hora cheia (minuto 0). Descartei precip fora de [0, 200] mm; vazios ignorados.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | match | (2016.0, 920.7, 8766.0); (2017.0, 745.6, 8738.0); (2018.0, 945.2, 8751.0); (2019.0, 1114.2, 8725.0) … +6 linhas |
| v5_v1 | answered | diverge | (2024.0, 708.6, 8011.0); (2016.0, 920.7, 8766.0); (2021.0, 722.2, 7448.0); (2018.0, 945.2, 8751.0) … +6 linhas |
| v5_v2 | answered | diverge | (2024.0, 708.6, 8011.0); (2016.0, 920.7, 8766.0); (2021.0, 722.2, 7448.0); (2018.0, 945.2, 8751.0) … +6 linhas |
| v7 | answered | match | (2016.0, 920.7, 8766.0); (2017.0, 745.6, 8738.0); (2018.0, 945.2, 8751.0); (2019.0, 1114.2, 8725.0) … +6 linhas |

Nota automática: 2 de 20 números da referência sem par na resposta: [2024.0, 2025.0]

## E24 · serie_ranking · esperado `answerable`

**Pergunta:** Em que mês de 2021 mais choveu em SBGR, e quanto?

**Referência (oráculo):** (2, 217.6)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Para grandezas acumuladas/contadas por hora usa só boletins na hora cheia (minuto 0). Descartei precip fora de [0, 200] mm.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (1159.8, 8127.0) |
| v5_v1 | answered | diverge | (2021-02, 217.5, 669.0) |
| v5_v2 | answered | diverge | (2021-02, 217.5, 669.0); (2021-12, 215.3, 692.0); (2021-01, 171.0, 744.0); (2021-10, 153.4, 668.0) … +8 linhas |
| v7 | rejected | abstained | — |

Nota automática: 1 de 2 números da referência sem par na resposta: [2.0] / 2 de 2 números da referência sem par na resposta: [2.0, 217.6]

## E25 · serie_ranking · esperado `answerable`

**Pergunta:** Qual estação registrou a maior rajada de vento em 2022?

**Referência (oráculo):** (SBUL, 68.0)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Rajada em nós; descartei rajada fora de [0, 120]; vazios ignorados; empate improvável, retorno a primeira.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (SBCG, 66.0, 1.0) |
| v5_v1 | answered | diverge | (SBCG, 66.0, 703.0) |
| v5_v2 | answered | diverge | (SBCG, SBCG, 66.0, 703.0) |
| v7 | answered | diverge | (66.0, 13492.0) |

Nota automática: 1 de 1 números da referência sem par na resposta: [68.0]

## E27 · serie_ranking · esperado `answerable`

**Pergunta:** Qual foi o ponto de orvalho médio de cada ano, de 2016 a 2025, em SBCO?

**Referência (oráculo):** (2016, 14.87); (2017, 15.99); (2018, 15.88); (2019, 16.36) … +6 linhas

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Descartei temppo fora de [-20, 40] °C.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (2016.0, 14.872, 7438.0); (2017.0, 15.987, 7478.0); (2018.0, 15.877, 7474.0); (2019.0, 16.357, 7447.0) … +6 linhas |
| v5_v1 | answered | diverge | (2019, 16.357, 7447.0); (2020, 15.061, 7344.0); (2025, 16.24, 7665.0); (2023, 16.791, 8084.0) … +6 linhas |
| v5_v2 | answered | diverge | (2024.0, 16.384, 9374.0); (2016.0, 14.872, 7438.0); (2021.0, 15.1, 7652.0); (2018.0, 15.877, 7474.0) … +6 linhas |
| v7 | answered | diverge | (2016.0, 14.872, 7438.0); (2017.0, 15.987, 7478.0); (2018.0, 15.877, 7474.0); (2019.0, 16.357, 7447.0) … +6 linhas |

Nota automática: 13 de 20 números da referência sem par na resposta: [2016.0, 2017.0, 2018.0, 2019.0, 2020.0] / 3 de 20 números da referência sem par na resposta: [14.62, 15.24, 16.26] / 5 de 20 números da referência sem par na resposta: [14.62, 15.24, 2024.0, 2025.0, 16.26]

## E28 · serie_ranking · esperado `answerable`

**Pergunta:** Considerando 2016 a 2025, em qual mês do ano SBJV tem em média a pior visibilidade?

**Referência (oráculo):** (7, 12080.6)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Média por mês do ano sobre todos os anos; visibpre em dezenas de metros, multipliquei por 10; descartei valores fora de [0, 2000].

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | match | (7.0, 12080.556, 6259.0) |
| v5_v1 | answered | match | (7.0, 12080.556, 6259.0) |
| v5_v2 | answered | diverge | (07, 12080.556, 6259.0) |
| v7 | rejected | abstained | — |

Nota automática: 1 de 2 números da referência sem par na resposta: [7.0]

## E30 · comparacao · esperado `answerable`

**Pergunta:** SBPA esteve mais quente em janeiro de 2016 ou em janeiro de 2025?

**Referência (oráculo):** (2016, 25.63); (2025, 25.44)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Comparei a temperatura média do ar; descartei bseco fora de [-10, 50] °C.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | needs_clarification | abstained | — |
| v5_v1 | needs_clarification | abstained | — |
| v5_v2 | needs_clarification | abstained | — |
| v7 | needs_clarification | abstained | — |

## E32 · comparacao · esperado `answerable`

**Pergunta:** A pressão QNH média em SBBR em 2025 foi maior ou menor que em 2016?

**Referência (oráculo):** (2016, 1019.72); (2025, 1019.56)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Descartei qnh fora de [850, 1100] hPa.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | needs_clarification | abstained | — |
| v5_v1 | needs_clarification | abstained | — |
| v5_v2 | unsupported | abstained | — |
| v7 | unsupported | abstained | — |

## E37 · impossivel · esperado `unsupported`

**Pergunta:** Qual foi a temperatura média em SBGL em março de 2012?

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | no_results | answered_unanswerable | — |
| v5_v1 | no_results | answered_unanswerable | — |
| v5_v2 | no_results | answered_unanswerable | — |
| v7 | no_results | answered_unanswerable | — |

## E41 · ambigua · esperado `needs_clarification`

**Pergunta:** Qual foi a média de vento?

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | answered_unanswerable | (6.091, 12522133.0) |
| v5_v1 | execution_error | — | — |
| v5_v2 | answered | answered_unanswerable | (6.091, 12522133.0) |
| v7 | answered | answered_unanswerable | (6.091, 12522133.0) |

## E42 · ambigua · esperado `needs_clarification`

**Pergunta:** Qual foi a temperatura em SBSV em 2020?

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | answered_unanswerable | (2020-01-02, 23.9); (2020-01-02, 27.7); (2020-01-03, 25.7); (2020-01-05, 26.7) … +46 linhas |
| v5_v1 | execution_error | — | — |
| v5_v2 | answered | answered_unanswerable | (2020-01-02, 23.9); (2020-01-02, 27.7); (2020-01-03, 25.7); (2020-01-05, 26.7) … +46 linhas |
| v7 | answered | answered_unanswerable | (2020-01-02, 23.9); (2020-01-02, 27.7); (2020-01-03, 25.7); (2020-01-05, 26.7) … +46 linhas |

## E43 · informal · esperado `answerable`

**Pergunta:** qual a temperatua maxima em sbpv no dia 13 de março de 2021?

**Referência (oráculo):** (31.9)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Descartei bseco fora de [-10, 50] °C; todos os boletins do dia.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (33.0, 817.0) |
| v5_v1 | execution_error | abstained | — |
| v5_v2 | rejected | abstained | — |
| v7 | rejected | abstained | — |

Nota automática: 1 de 1 números da referência sem par na resposta: [31.9]

## E44 · informal · esperado `answerable`

**Pergunta:** sbcg, quantos mm choveu em janeiro de 2024?

**Referência (oráculo):** (64.1)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Para grandezas acumuladas/contadas por hora usa só boletins na hora cheia (minuto 0). Descartei precip fora de [0, 200] mm.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (731.0) |
| v5_v1 | execution_error | abstained | — |
| v5_v2 | answered | diverge | (731.0) |
| v7 | rejected | abstained | — |

Nota automática: 1 de 1 números da referência sem par na resposta: [64.1]

## E45 · informal · esperado `answerable`

**Pergunta:** bora ver: qnh maximo de sbsm em 2017, rapidão

**Referência (oráculo):** (1033.4)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Descartei qnh fora de [850, 1100] hPa.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | match | (1033.4, 7758.0) |
| v5_v1 | execution_error | abstained | — |
| v5_v2 | unsupported | abstained | — |
| v7 | answered | match | (1033.4, 7758.0) |

## E46 · informal · esperado `answerable`

**Pergunta:** No SBLO o bulbo úmido mais alto de 2018 foi quanto?

**Referência (oráculo):** (26.6)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Descartei bumido fora de [-10, 40] °C.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | match | (26.6, 9270.0) |
| v5_v1 | execution_error | abstained | — |
| v5_v2 | answered | match | (26.6, 9270.0) |
| v7 | answered | match | (26.6, 9270.0) |

## E47 · tempo · esperado `answerable`

**Pergunta:** Qual foi a temperatura média em SBSP no verão de 2022?

**Referência (oráculo):** (21.78)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Verão = dezembro de 2021 a fevereiro de 2022 (verão meteorológico austral que termina em 2022); descartei bseco fora de [-10, 50] °C.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | needs_clarification | abstained | — |
| v5_v1 | execution_error | abstained | — |
| v5_v2 | needs_clarification | abstained | — |
| v7 | needs_clarification | abstained | — |

## E48 · tempo · esperado `answerable`

**Pergunta:** Quanto choveu em SBBE de madrugada em 2019?

**Referência (oráculo):** (180.8)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Para grandezas acumuladas/contadas por hora usa só boletins na hora cheia (minuto 0). Madrugada = horas 0 a 5 (00:00 a 05:59 local); descartei precip fora de [0, 200] mm.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | needs_clarification | abstained | — |
| v5_v1 | execution_error | abstained | — |
| v5_v2 | unsupported | abstained | — |
| v7 | unsupported | abstained | — |

## E49 · tempo · esperado `answerable`

**Pergunta:** Qual foi a temperatura média de SBCF no primeiro trimestre de 2023?

**Referência (oráculo):** (23.34)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Primeiro trimestre = janeiro a março; descartei bseco fora de [-10, 50] °C.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | answered | diverge | (23.373, 2525.0) |
| v5_v1 | execution_error | abstained | — |
| v5_v2 | answered | diverge | (23.373, 2525.0) |
| v7 | answered | diverge | (23.373, 2525.0) |

Nota automática: 1 de 1 números da referência sem par na resposta: [23.34]

## E50 · tempo · esperado `answerable`

**Pergunta:** Qual a velocidade média do vento em SBNT nos fins de semana de 2024?

**Referência (oráculo):** (8.81)

**Premissas do oráculo:** Hora local fixa UTC-3 como nos arquivos. Fim de semana = sábado e domingo; média sobre todas as linhas de vento (uma por cabeceira), não por boletim; descartei velvento fora de [0, 100] nós.

| condição | status | automático | resposta do sistema (linhas) |
|---|---|---|---|
| v4 | unsupported | abstained | — |
| v5_v1 | execution_error | abstained | — |
| v5_v2 | answered | diverge | (8.563, 17579.0) |
| v7 | unsupported | abstained | — |

Nota automática: 1 de 1 números da referência sem par na resposta: [8.81]
