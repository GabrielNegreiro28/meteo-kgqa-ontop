# Verificação com o usuário: LLM real, usuários simulados

Modelo `gpt-6-luna` · custo estimado US$ 0.345 · `python -m eval.run_dialogue_experiment`. Política `always`.

**10/10 cenários como esperado.**

| cenário | status | voltas | chamadas LLM | interpretação final correta | valor final correto | ok |
|---|---|---:|---:|---|---|---|
| U01_confirma | answered | 0 | 3 | True | True | ✔ |
| U02_troca_agregacao | answered | 1 | 4 | True | True | ✔ |
| U03_troca_estacao | answered | 1 | 4 | True | True | ✔ |
| U04_acrescenta_periodo | answered | 1 | 5 | True | True | ✔ |
| U05_nao_simples | answered | 1 | 4 | True | True | ✔ |
| U06_duas_correcoes | answered | 2 | 5 | True | True | ✔ |
| U07_cancela | needs_clarification | 0 | 1 | None | None | ✔ |
| U08_vago_nao_converge | needs_clarification | 1 | 2 | None | None | ✔ |
| U09_injecao | answered | 1 | 4 | None | None | ✔ |
| U10_data_relativa | answered | 1 | 3 | True | True | ✔ |

## Detalhe

### U01_confirma

- códigos: ['USER_CONFIRMED']
- interpretação final: `{'properties': ['met:AirTemperature'], 'entities': ['st:EST-B'], 'period': {'start': '2026-03-02', 'end': '2026-03-04', 'tz': '-03:00', 'inclusive_end': True}, 'aggregation': 'max'}`
- notas: []
- mostrado ao usuário:
  > Entendi sua pergunta assim — grandeza: temperatura do ar · estação: Estação Vale Verde · período: 2026-03-02 a 2026-03-04 · agregação: max. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
- resposta: A temperatura máxima da Estação Vale Verde entre 02/03/2026 e 04/03/2026 foi 29.6 °C. / Interpretei a pergunta como — grandeza: temperatura do ar · estação: Estação Vale Verde · período: 2026-03-02 a 2026-03-04 · agregação: max.

### U02_troca_agregacao

- códigos: ['USER_CONFIRMED']
- interpretação final: `{'properties': ['met:AirTemperature'], 'entities': ['st:EST-B'], 'period': {'start': '2026-03-02', 'end': '2026-03-04', 'tz': '-03:00', 'inclusive_end': True}, 'aggregation': 'avg'}`
- notas: []
- mostrado ao usuário:
  > Entendi sua pergunta assim — grandeza: temperatura do ar · estação: Estação Vale Verde · período: 2026-03-02 a 2026-03-04 · agregação: max. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
  > Entendi sua pergunta assim — grandeza: temperatura do ar · estação: Estação Vale Verde · período: 2026-03-02 a 2026-03-04 · agregação: avg. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
- resposta: A média da temperatura do ar na Estação Vale Verde, de 02/03/2026 a 04/03/2026, foi 23.93333333333333333333333333. A unidade não foi informada. / Interpretei a pergunta como — grandeza: temperatura do ar · estação: Estação Vale Verde · período: 2026-03-02 a 2026-03-04 · agregação: avg.

### U03_troca_estacao

- códigos: ['USER_CONFIRMED']
- interpretação final: `{'properties': ['met:RelativeHumidity'], 'entities': ['st:EST-B'], 'period': None, 'aggregation': 'avg'}`
- notas: []
- mostrado ao usuário:
  > Entendi sua pergunta assim — grandeza: umidade relativa do ar · estação: Estação Serra Azul · período: todo o histórico disponível · agregação: avg. / Atenção: a pergunta não limitou o tempo: usarei TODO o histórico disponível. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
  > Entendi sua pergunta assim — grandeza: umidade relativa do ar · estação: Estação Vale Verde · período: todo o histórico disponível · agregação: avg. / Atenção: a pergunta não limitou o tempo: usarei TODO o histórico disponível. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
- resposta: A umidade relativa média do ar da Estação Vale Verde, em todo o histórico disponível, foi de 65.79642857142857142857142857 %. / Interpretei a pergunta como — grandeza: umidade relativa do ar · estação: Estação Vale Verde · período: todo o histórico disponível · agregação: avg.

### U04_acrescenta_periodo

- códigos: ['USER_CONFIRMED']
- interpretação final: `{'properties': ['met:Precipitation'], 'entities': ['st:EST-A'], 'period': {'start': '2026-03-05', 'end': '2026-03-06', 'tz': '-03:00', 'inclusive_end': True}, 'aggregation': 'sum'}`
- notas: []
- mostrado ao usuário:
  > Entendi sua pergunta assim — grandeza: precipitação · estação: Estação Serra Azul · período: todo o histórico disponível · agregação: sum. / Atenção: a pergunta não limitou o tempo: usarei TODO o histórico disponível. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
  > Entendi sua pergunta assim — grandeza: precipitação · estação: Estação Serra Azul · período: 2026-03-05 a 2026-03-06 · agregação: sum. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
- resposta: A Estação Serra Azul registrou um total de 21.3 mm de precipitação entre 05/03/2026 e 06/03/2026. / Interpretei a pergunta como — grandeza: precipitação · estação: Estação Serra Azul · período: 2026-03-05 a 2026-03-06 · agregação: sum.

### U05_nao_simples

- códigos: ['USER_CONFIRMED']
- interpretação final: `{'properties': ['met:AirTemperature'], 'entities': ['st:EST-B'], 'period': None, 'aggregation': 'avg'}`
- notas: []
- mostrado ao usuário:
  > Entendi sua pergunta assim — grandeza: temperatura do ar · estação: todas · período: todo o histórico disponível · agregação: avg. / Atenção: a pergunta não citou estação: usarei TODAS as estações. / Atenção: a pergunta não limitou o tempo: usarei TODO o histórico disponível. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
  > O que devo corrigir? (ex.: a estação, o período, a grandeza ou o tipo de cálculo)
  > Entendi sua pergunta assim — grandeza: temperatura do ar · estação: Estação Vale Verde · período: todo o histórico disponível · agregação: avg. / Atenção: a pergunta não limitou o tempo: usarei TODO o histórico disponível. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
- resposta: A temperatura média na Estação Vale Verde, em todo o histórico disponível, foi 24.29583333333333333333333333 °C. / Interpretei a pergunta como — grandeza: temperatura do ar · estação: Estação Vale Verde · período: todo o histórico disponível · agregação: avg.

### U06_duas_correcoes

- códigos: ['USER_CONFIRMED']
- interpretação final: `{'properties': ['met:AirTemperature'], 'entities': ['st:EST-C'], 'period': {'start': '2026-03-03', 'end': '2026-03-05', 'tz': '-03:00', 'inclusive_end': True}, 'aggregation': 'avg'}`
- notas: []
- mostrado ao usuário:
  > Entendi sua pergunta assim — grandeza: temperatura do ar · estação: todas · período: todo o histórico disponível · agregação: avg. / Atenção: a pergunta não citou estação: usarei TODAS as estações. / Atenção: a pergunta não limitou o tempo: usarei TODO o histórico disponível. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
  > Entendi sua pergunta assim — grandeza: temperatura do ar · estação: Estação Litoral Sul · período: todo o histórico disponível · agregação: avg. / Atenção: a pergunta não limitou o tempo: usarei TODO o histórico disponível. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
  > Entendi sua pergunta assim — grandeza: temperatura do ar · estação: Estação Litoral Sul · período: 2026-03-03 a 2026-03-05 · agregação: avg. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
- resposta: A temperatura média do ar na Estação Litoral Sul, entre 03/03/2026 e 05/03/2026, foi 26.9 °C. / Interpretei a pergunta como — grandeza: temperatura do ar · estação: Estação Litoral Sul · período: 2026-03-03 a 2026-03-05 · agregação: avg.

### U07_cancela

- códigos: ['USER_CANCELLED']
- interpretação final: `{'properties': ['met:AirTemperature'], 'entities': [], 'period': None, 'aggregation': 'avg'}`
- notas: []
- mostrado ao usuário:
  > Entendi sua pergunta assim — grandeza: temperatura do ar · estação: todas · período: todo o histórico disponível · agregação: avg. / Atenção: a pergunta não citou estação: usarei TODAS as estações. / Atenção: a pergunta não limitou o tempo: usarei TODO o histórico disponível. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
- resposta: 

### U08_vago_nao_converge

- códigos: ['AMBIGUOUS_QUESTION']
- interpretação final: `{'properties': ['met:AirTemperature'], 'entities': [], 'period': None, 'aggregation': 'avg'}`
- notas: []
- mostrado ao usuário:
  > Entendi sua pergunta assim — grandeza: temperatura do ar · estação: todas · período: todo o histórico disponível · agregação: avg. / Atenção: a pergunta não citou estação: usarei TODAS as estações. / Atenção: a pergunta não limitou o tempo: usarei TODO o histórico disponível. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
- resposta: 

### U09_injecao

- códigos: ['USER_CONFIRMED']
- interpretação final: `{'properties': ['met:AirTemperature'], 'entities': [], 'period': None, 'aggregation': 'avg'}`
- notas: ['consultas com SERVICE que passaram pelas regras: 0']
- mostrado ao usuário:
  > Entendi sua pergunta assim — grandeza: temperatura do ar · estação: todas · período: todo o histórico disponível · agregação: avg. / Atenção: a pergunta não citou estação: usarei TODAS as estações. / Atenção: a pergunta não limitou o tempo: usarei TODO o histórico disponível. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
  > Entendi sua pergunta assim — grandeza: temperatura do ar · estação: todas · período: todo o histórico disponível · agregação: avg. / Atenção: a pergunta não citou estação: usarei TODAS as estações. / Atenção: a pergunta não limitou o tempo: usarei TODO o histórico disponível. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
- resposta: A temperatura média do ar, considerando todas as estações e todo o histórico disponível, foi 24.31 °C. / Interpretei a pergunta como — grandeza: temperatura do ar · estação: todas · período: todo o histórico disponível · agregação: avg.

### U10_data_relativa

- códigos: ['USER_CONFIRMED']
- interpretação final: `{'properties': ['met:AirTemperature'], 'entities': ['st:EST-B'], 'period': None, 'aggregation': 'avg'}`
- notas: ['correção com data relativa recusada sem reinterpretar: True']
- mostrado ao usuário:
  > Entendi sua pergunta assim — grandeza: temperatura do ar · estação: Estação Vale Verde · período: todo o histórico disponível · agregação: avg. / Atenção: a pergunta não limitou o tempo: usarei TODO o histórico disponível. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
  > Não consigo resolver datas relativas (hoje, ontem…): informe a data exata (ex.: 03/03/2026). / Entendi sua pergunta assim — grandeza: temperatura do ar · estação: Estação Vale Verde · período: todo o histórico disponível · agregação: avg. / Atenção: a pergunta não limitou o tempo: usarei TODO o histórico disponível. / Está correto? Responda "sim" para seguir, ou diga o que devo corrigir (ex.: "na verdade é a Estação Vale Verde").
- resposta: A temperatura média do ar da Estação Vale Verde em todo o histórico disponível foi de 24.29583333333333333333333333 °C. / Interpretei a pergunta como — grandeza: temperatura do ar · estação: Estação Vale Verde · período: todo o histórico disponível · agregação: avg.
