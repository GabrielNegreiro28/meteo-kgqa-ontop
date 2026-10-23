# Avaliação independente: prompts `v4`, `gpt-6-luna`, grafo real (Ontop)

Conjunto congelado (sha256 `0d05a4a3…`, 49 perguntas; perguntas e códigos de referência escritos por outro agente, sem as regras da pipeline).
Uma execução, 2026-10-23, custo US$ 1,7513 (autorização de US$ 1,75 dada pelo usuário). Nenhuma regra, prompt ou pergunta foi alterado depois.

**Cobertura: 48 de 49.** O teto da execução (US$ 1,75) foi atingido antes da última pergunta (**E50 não foi medida**). Os números abaixo são de n=48.
Dados por pergunta: `eval/reports/independent_run_v4_a.json` e `.md` (fora do git; contêm agregados dos dados reais).

## Resultado bruto (automático)
| | n | |
|---|---:|---|
| status igual ao esperado | 34/48 | |
| respondíveis (38): número da referência aparece na resposta | 16 | `match` |
| respondíveis: números divergem, a julgar | 10 | `diverge` |
| respondíveis: a pipeline não respondeu | 12 | abstenções |
| não respondíveis (10): recusa/esclarecimento correto | 8 | |
| não respondíveis respondidas com "sem registros" (`OUT_OF_COVERAGE`) | 2 | E35 (futuro), E37 (2015) |

## Veredito PROVISÓRIO das 10 divergências
Quem julga deveria ser humano independente; este é o **meu** primeiro julgamento, de quem escreveu a pipeline (viés), e precisa de conferência.
Tomei como base a consulta SPARQL que a pipeline executou e as `assumptions` da referência.

| id | provável | por quê |
|---|---|---|
| E05 | **erro da pipeline** | pediu 1 a 15 de setembro; a consulta filtrou o mês inteiro (`<= 2022-09-30`) e entregou como certa |
| E14 | **erro da pipeline** | "abaixo de 1 km" virou `?value < 1` em metros; o certo é 1000. Resultado "sem registros" falso (a referência acha 10 horas) |
| E23 | **erro da pipeline** | "maior chuva acumulada" virou `MAX` por estação, não `SUM`; o ranking entregue é outro |
| E30 | provável erro (resposta incompleta) | pediu a mudança entre dois anos e entregou um valor só, coincidente com o de 2022 |
| E17 | ok | os dois dão 0; o runner marcou `diverge` só porque o status foi `no_results` (limitação do comparador) |
| E13, E19 | provável diferença de limpeza | a referência consolida duplicatas de estação e instante pela média e conta 720 e 2; a pipeline conta 772 e 3 |
| E25 | provável diferença de limpeza | 42,0 contra 41,95 (referência consolida duplicatas) |
| E44, E47 | em aberto | máximo de vento 24 contra 30; média de verão 22,12 contra 22,03. Pode ser limpeza, filtro de valores impossíveis ou fuso |

Então há **pelo menos 3 respostas erradas entregues como certas (E05, E14, E23), talvez 4**, em 38 respondíveis. É uma taxa que o conjunto de
desenvolvimento nunca mostrou (lá, 0 erradas). Os três erros são de interpretação (período parcial de mês, unidade km→m, SUM→MAX), não de dados.

## As 12 abstenções
- **Limitações declaradas da pipeline** (não são bug): mediana (E28, E32), altura de nuvem (E11, E27, E48 visibilidade por faixa do dia), agregação não permitida em duração de chuva (E12), "dia mais quente" ambíguo (E02).
- **Suspeitas de falso positivo das regras novas** (D-67/D-68): E22 e E26 pediram série anual de 2016/2020 a 2025 e foram recusadas por `PERIOD_DATES_MISMATCH`/`PERIOD_PARTIAL_YEAR`. Pergunta legítima barrada.
- **Em aberto**: E15 (`AGGREGATION_MISMATCH`), E18 (`ENTITY_MISMATCH`), E31 (`MISSING_COUNT`). Precisam de leitura caso a caso.

## O que isto muda
1. A conclusão "0 erradas" das medições anteriores **não se sustenta** num conjunto escrito por outro: pelo menos 3 em 38.
2. As regras L4 pegam erros de **mês e de ano**, mas não de **dia parcial dentro de um mês** (E05), **conversão de unidade em limiar** (E14) e **troca de agregação** (E23). Isto são novas lacunas, não corrigidas de propósito para não contaminar o conjunto.
3. Há ao menos 2 falsos positivos das regras de período em séries multi-ano.
4. O comparador numérico automático é fraco para `no_results` (E17).

## Limites desta medição
n=48, uma execução, modelo único, um prompt (`v4`); o veredito de 10 casos é provisório e meu; as referências são código gerado, não verdade (herdam hipóteses de limpeza e fuso). Não gera taxa de acerto com intervalo de confiança até haver julgamento humano de cada divergência.
Qualquer correção das lacunas acima deve ser feita **depois** de registrar este resultado, e a remedição exige um conjunto novo (este já foi visto).
