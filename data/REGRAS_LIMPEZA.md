# Regras de limpeza e controle de qualidade — dados reais

Implementadas em `ingest/transform.py`. Nada é apagado: tudo que não vira observação no grafo vai para a
tabela `quarantine` com origem (arquivo + linha do CSV), valor bruto e motivo. Contagens da execução de 15/10/2026.

## Resultado
- 61,7 mi de linhas brutas → **105,4 mi de observações** em 8,67 mi de boletins de 178 aeródromos.
- **230.812 entradas de quarentena** (0,2 %), das quais 203.835 são exclusões por regra (não são erros).

## Regras estruturais
| Regra | O que faz | Por quê |
|---|---|---|
| R1 Tempo | `hora_observacao` = hora local fixa UTC−3; `t_utc = t + 3 h` | Ciclo diurno e artefato de horário de verão (P-16) |
| R2 Horário de verão | linhas às 01:xx de 16/10/2016, 15/10/2017 e 04/11/2018 → quarentena (2.504) | Não dá para saber qual das duas era a das 00:xx |
| R4 Duplicatas | valores idênticos no mesmo boletim colapsam; valores distintos viram observações `seq` 0, 1… com `met:multipleReadings true` | A fonte não identifica qual sensor/pista gerou cada valor (9,3 % das temperaturas do ar) |
| R5 Chuva | só boletins da hora cheia; acumulado em [t−1 h, t]; dia = dia do início do intervalo | Boletins extras têm 0/vazio; a chuva das 23–24 h pertence ao dia anterior |
| R6 Unidades | visibilidade e base de nuvem dam→m; direção do vento dezenas de graus→graus | P-17 (a confirmar com o professor) |
| R7 Vazio | nunca vira zero | — |

## Faixas físicas (quarentena por valor)
temperatura −30…50 °C · ponto de orvalho −40…40 °C · bulbo úmido −30…45 °C · temperatura de pista −30…75 °C ·
umidade 1…100 % · QNH 900…1100 hPa · visibilidade 0…20 km · chuva 0…150 mm/h · duração 0…60 min ·
vento 0…150 kt · rajada 0…200 kt · cobertura 1–9 oitavos (9 = céu obscurecido).

## Controle de qualidade (o que a faixa física não pega)
| Teste | Regra | Movidas | Caso que motivou |
|---|---|---|---|
| Q1a código de erro | mesmo valor de chuva ≥ 50 mm repetido ≥ 5 vezes na estação | 1.351 | SBIT: 941× "100,2 mm" com duração 0 min |
| Q1b par inconsistente | chuva > 0 com duração 0 → descarta a **duração**, mantém a chuva | 9.027 | 2018–2020 em estações do Norte: duração não registrada |
| Q2 sensor travado | mesmo valor ≥ 20 mm em ≥ 3 boletins horários seguidos | 9 | SBSC: 99,1 mm por 11 horas seguidas |
| Q3 pico isolado | difere > 8 (°C ou hPa) dos dois instantes vizinhos (≤ 3 h), no mesmo sentido | 1.851 temp. · 2.296 orvalho · 1.853 QNH | SBCF: 49,6 °C às 3h |
| Q4 rajada | rajada < vento médio, ou > média + 50 kt (mesma cabeceira) | 281 | SBBR: rajada 177 kt com média 3 kt |
| Q5 pico de vento | > 25 kt acima dos dois vizinhos (mesma cabeceira) | 481 | — |

Efeito verificado: SBSC 2024 passou de 11.920 mm para 708 mm; maior chuva diária 342 mm; maior temperatura
44,3 °C (SBME, 18/09/2019 13h); maior rajada 81 kt. Totais anuais de Belém e Guarulhos em 2019 inalterados.

## Limitações conhecidas
- Q1b escolhe confiar na quantidade de chuva; é uma hipótese, não um fato.
- Médias usam todas as leituras válidas; boletins com dois sensores pesam o dobro (efeito pequeno: diferenças de 0,1 °C).
- Nenhum teste cruzado entre variáveis além de Q1b e Q4 (ex.: ponto de orvalho > temperatura).
