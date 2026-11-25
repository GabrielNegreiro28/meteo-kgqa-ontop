# Medição no conjunto estudo_20261125 (condição completa, uma repetição)

Rodada única do metqa no commit c133138 (base corrigida: relógio dos dados e cadastro de estações), 25/11/2026, LLM gpt-6-luna, grafo
real. Conjunto congelado antes da execução (`eval/frozen/estudo_20261125`, conflitos previstos em `LEIAME.md`): 120 perguntas de um agente
separado, com referências em SQL sobre a MESMA base limpa que o sistema consulta, então o placar mede a consulta e não a limpeza.

Verba autorizada: US$ 4,00. Gasto: US$ 4,005. A verba acabou na 104ª pergunta da agenda: 103 rodaram até o fim, S066 parou por falta de
verba e 16 não rodaram (S007, S012, S018, S019, S021, S025, S033, S068, S079, S080, S088, S090, S095, S105, S110, S118). Custo de US$ 0,039
por pergunta; latência mediana de 4,9 s. Trilhas e respostas em `eval/reports/estudo_20261125_full_b1..b4/events.jsonl`.

## Placar

| | estrito (`eval.study`) | adjudicado |
|---|---|---|
| corretas | 68/104 | 69/103 (67%) |
| respostas a respondíveis que batem com a referência | 44 de 46 | 45 de 46 |
| números errados entregues | — | 0 |

Diferenças entre os dois placares, conferidas uma a uma:
- S074 (Noronha, 2023, sem dados): o sistema disse corretamente que não há registros; o comparador estrito falhou porque o Ontop devolve
  média 0 com n = 0 onde a referência tem nulo. Defeito do comparador, contado como correto no adjudicado.
- S066: interrompida pela verba, fora do placar adjudicado.

## As respostas entregues

Das 46 respostas a perguntas respondíveis, 45 coincidem exatamente com o SQL independente (inclusive séries, rankings, comparações de
períodos, horas locais e dias da semana). A outra, S031 ("QNH de cada mês de 2022 em Curitiba (Afonso Pena)"), trouxe os 12 valores certos de
SBCT e também os de SBBI: "Curitiba" é o município de SBBI e "Afonso Pena" é o apelido de SBCT, e o LLM pegou as duas. Nenhum número errado.

## As 23 abstenções nas respondíveis

| causa | perguntas | natureza |
|---|---|---|
| conflito previsto com a convenção de lugar (cidade com duas estações, nome fora do cadastro) | S003, S006, S009, S024, S037, S057, S065, S096 | registrado antes de rodar |
| região ou adjetivo não reconhecido ("do Nordeste", "do Sul", "do Centro-Oeste", "paulistas") | S010, S035, S046, S058 | defeito: o cadastro só reconhece "região X" e nomes de estado |
| as duas leituras divergem no status (uma responde, a outra pede esclarecimento) | S004, S055, S061, S063, S084, S086 | camada de linguagem |
| filtro pelo gênero da nuvem ("camadas CB", "8 oitavos") | S071, S109 | capacidade que falta |
| condição sobre leituras com agrupamento | S073 | camada de linguagem |
| "Manaus (Eduardo Gomes)" lido como as duas estações de Manaus | S027 | camada de linguagem |
| "5h59" tratado como número sem uso (alarme falso da conservação) | S040 | conservação da evidência |

## Não respondíveis (34)

Nenhuma recebeu número.
- Esclarecimento esperado: 15 de 18. As 3 restantes foram recusadas em vez de esclarecidas porque o lugar não foi reconhecido (S005 Natal,
  S023 e S029 Cuiabá).
- Fora do escopo esperado: 9 de 16. O sistema pediu esclarecimento em vez de recusar em 5 (lugares sem estação: Blumenau, Ouro Preto,
  Gramado; S114 com 1998; S032 "amanhã", que o prompt manda esclarecer) e respondeu "não há registros, os dados cobrem 2016–2025" em 2
  (S038, S047), com status `no_results` em vez de `unsupported`.

## Leitura

- A consulta está certa quando o sistema responde: 45 de 46 respostas exatas contra um oráculo independente sobre a mesma base, e a outra
  com os números certos e uma estação a mais.
- As perdas estão no reconhecimento de lugares (12 das 23 abstenções, mais 3 das não respondíveis) e na concordância entre as leituras (6).
  As 8 previstas eram esperadas pela convenção; as 4 de região são um defeito do cadastro introduzido nesta rodada.
- Uma condição e uma repetição não medem a contribuição das camadas (ablações) nem a variação entre rodadas.

## O que corrigir, sem tocar neste conjunto como teste

Este conjunto agora é conhecido; as correções abaixo precisam ser medidas em outro conjunto inédito.
- Regiões pelo nome sozinho ("Nordeste") quando não é direção de vento, e gentílicos de estado ("paulistas", "mineiras").
- Cidade atendida pelo aeroporto como menção que pode cobrir várias estações ("Cuiabá" → SBCY; "Natal" → SBNT e SBSG) e apelidos populares
  ("Floripa", "Santa Genoveva").
- Nome entre parênteses que identifica uma das estações citadas ("Curitiba (Afonso Pena)").
- Comparador estrito: `no_results` nos dois lados é acerto, independentemente do conteúdo da linha agregada.
- Período fora da cobertura: status `unsupported` (hoje `no_results`, com a mensagem certa).
