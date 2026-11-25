# Medição no conjunto estudo_20261125 (condição completa, uma repetição)

Rodada única do metqa no commit c133138 (base corrigida: relógio dos dados e cadastro de estações), 25/11/2026, LLM gpt-6-luna, grafo
real. Conjunto congelado antes da execução (`eval/frozen/estudo_20261125`, conflitos previstos em `LEIAME.md`): 120 perguntas de um agente
separado, com referências em SQL sobre a MESMA base limpa que o sistema consulta, então o placar mede a consulta e não a limpeza.

Execução em cinco blocos (`eval/reports/estudo_20261125_full_b1..b5/events.jsonl`, fora do git). Os quatro primeiros usaram a verba de
US$ 4,00 e pararam na 104ª pergunta da agenda (S066 interrompida pela verba); o quinto, com mais US$ 0,80 autorizados, rodou as 17 restantes
(inclusive a S066 desde o início). Gasto total: US$ 4,64 (US$ 0,039 por pergunta); latência mediana de 4,9 s.

## Placar (120 perguntas)

| | estrito (`eval.study`) | adjudicado |
|---|---|---|
| corretas | 79/120 | 80/120 (67%) |
| respondíveis | 50/80 | 51/80 |
| esclarecimento esperado | 17/20 | 17/20 |
| fora do escopo esperado | 12/20 | 12/20 |
| respostas a respondíveis que batem com a referência | 50 de 53 | 51 de 53 |
| respostas erradas entregues | 5 | 2 (nenhum número errado) |

Diferenças entre os dois placares, conferidas uma a uma:
- S074 (Noronha, 2023, sem dados): o sistema disse corretamente que não há registros; o comparador estrito falhou porque o Ontop devolve
  média 0 com n = 0 onde a referência tem nulo. Defeito do comparador.
- S038 e S047 (anos de 2015 e 2012): o sistema respondeu "não há registros, os dados cobrem 2016–2025", sem número, mas com status
  `no_results` em vez de `unsupported`. Erro de status, não resposta errada.

## As respostas entregues

Das 53 respostas a perguntas respondíveis, 51 coincidem exatamente com o SQL independente (séries, rankings, comparações de períodos, horas
locais, dias da semana). As outras duas:
- S031 ("QNH de cada mês de 2022 em Curitiba (Afonso Pena)"): os 12 valores certos de SBCT e também os de SBBI. "Curitiba" é o município de
  SBBI e "Afonso Pena" é o apelido de SBCT; o LLM pegou as duas.
- S007 ("temperatura média de cada mês do ano em Brasília, considerando 2016–2025 juntos"): pedia a climatologia mensal (12 valores); o
  sistema deu a série de cada mês de cada ano (120 valores). Números certos para a pergunta que respondeu, mas a pergunta era outra: o
  agrupamento por mês do ano, juntando anos, não existe no contrato (`month` é sempre ano e mês).

## As 27 abstenções nas respondíveis

| causa | perguntas | natureza |
|---|---|---|
| conflito previsto com a convenção de lugar (cidade com duas estações, nome fora do cadastro) | S003, S006, S009, S024, S037, S057, S065, S096, S110 | registrado antes de rodar |
| região ou adjetivo não reconhecido ("do Nordeste", "do Sul", "do Centro-Oeste", "paulistas") | S010, S035, S046, S058 | defeito: o cadastro só reconhece "região X" e nomes de estado |
| as duas leituras divergem no status (uma responde, a outra pede esclarecimento) | S004, S025, S055, S061, S063, S084, S086 | camada de linguagem |
| "Cidade (aeroporto)" lido como todas as estações da cidade | S021 (Belém (Val de Cans)), S027 (Manaus (Eduardo Gomes)) | camada de linguagem |
| filtro pelo gênero da nuvem ("camadas CB", "8 oitavos") | S071, S109 | capacidade que falta |
| condição sobre leituras com agrupamento | S073 | camada de linguagem |
| número do texto tratado como sem uso (alarme falso da conservação): "5h59", "P-20" | S040, S033 | conservação da evidência |

## Não respondíveis (40)

Nenhuma recebeu número.
- Esclarecimento esperado: 17 de 20. As 3 restantes foram recusadas em vez de esclarecidas porque o lugar não foi reconhecido (S005 Natal,
  S023 e S029 Cuiabá).
- Fora do escopo esperado: 12 de 20. Em 6, o sistema pediu esclarecimento em vez de recusar (lugares sem estação: Blumenau, Ouro Preto,
  Gramado, Petrópolis; S114 com 1998; S032 "amanhã", que o prompt manda esclarecer); em 2, `no_results` com a mensagem certa (S038, S047).

## Leitura

- A consulta está certa quando o sistema entende a pergunta: 51 de 53 respostas exatas contra um oráculo independente sobre a mesma base;
  nas duas outras, números certos com uma estação a mais (S031) ou um agrupamento diferente do pedido (S007).
- As perdas estão no reconhecimento de lugares (15 das 27 abstenções, mais 3 das não respondíveis) e na concordância entre as leituras (7).
  As 9 previstas eram esperadas pela convenção; as 4 de região são um defeito do cadastro introduzido nesta rodada.
- Uma condição e uma repetição não medem a contribuição das camadas (ablações) nem a variação entre rodadas.

## O que corrigir, sem tocar neste conjunto como teste

Este conjunto agora é conhecido; as correções abaixo precisam ser medidas em outro conjunto inédito.
- Regiões pelo nome sozinho ("Nordeste") quando não é direção de vento, e gentílicos de estado ("paulistas", "mineiras").
- Cidade atendida pelo aeroporto como menção que pode cobrir várias estações ("Cuiabá" → SBCY; "Natal" → SBNT e SBSG) e apelidos populares
  ("Floripa", "Santa Genoveva").
- "Cidade (aeroporto)": o nome entre parênteses identifica uma das estações e vence a cidade.
- Agrupamento por mês do ano juntando anos (climatologia mensal), ou recusa explícita quando pedido.
- Conservação da evidência: minutos de horário ("5h59") e números que fazem parte de nomes ("P-20").
- Comparador estrito: `no_results` nos dois lados é acerto, independentemente do conteúdo da linha agregada.
- Período fora da cobertura: status `unsupported` (hoje `no_results`, com a mensagem certa).
