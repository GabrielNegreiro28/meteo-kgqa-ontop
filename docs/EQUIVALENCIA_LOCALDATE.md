# Equivalência `met:localDate` × data-e-hora no grafo real

Gerado por `python -m eval.equivalencia_localdate`. Compara SUM, COUNT, MIN e MAX das duas formas de dizer o mesmo período.

- Estações: SBAA, SBCC, SBFI, SBJE, SBMI2, SBPK, SBSP, SBVC (1 a cada 22 da lista ordenada, de 178)
- Grandezas: met:Precipitation, met:AirTemperature, met:PressureQNH, met:WindSpeed; períodos: 8 (bordas, ver tabela)
- Comparações: **256**; **iguais: 256**; divergentes: **0**
- Comparações em que ambas as formas devolveram 0 linhas: 88 (igualdade vazia não prova nada; foram contadas à parte)
- Tempo médio por consulta: dia local 0.05 s, data-e-hora 0.09 s; total 0.6 min

## Divergências

Nenhuma.

## Por período

| período | comparações | iguais | linhas (n) mínimo–máximo na forma por dia |
|---|---:|---:|---|
| primeiro dia dos dados | 32 | 32 | 0–50 |
| último dia dos dados | 32 | 32 | 0–62 |
| dia bissexto | 32 | 32 | 0–48 |
| início do horário de verão 2016 (P-16) | 32 | 32 | 0–46 |
| início do horário de verão 2018 (P-16) | 32 | 32 | 0–44 |
| virada de ano | 32 | 32 | 0–102 |
| um mês | 32 | 32 | 0–1628 |
| um ano | 32 | 32 | 0–18609 |
