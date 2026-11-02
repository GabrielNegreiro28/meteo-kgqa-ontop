# Medição final do módulo (Fase 8 do plano) no conjunto novo_c_20261102

Rodada única do metqa na versão final (commit 467b071), 2026-11-02, mesmo modelo das medições anteriores, grafo real. Conjunto congelado e
commitado antes da execução (`eval/frozen/novo_c_20261102`, sha256 8e8b42fe…): 100 perguntas escritas por um agente separado, sem acesso ao
código nem aos resultados (80 respondíveis, 12 não respondíveis, 8 que pedem esclarecimento), com oráculos pandas sobre os CSV originais
(79 rodaram; o E205 falhou porque uma das estações não tem rajada no mês).

Custo: US$ 3,39 (US$ 0,034 por pergunta), dentro dos US$ 4 autorizados. Tempo: mediana de 6,6 s por pergunta (média de 6,8 s).
Trilha completa de cada pergunta: `eval/reports/independent_run_novo_c_20261102_metqa_1_trace.jsonl`.

Placar adjudicado (`python -m eval.adjudicate novo_c_20261102 metqa=metqa_1`, vereditos em `docs/julgamento_novo_c_20261102_veredictos.yaml`,
julgamento do Claude conferido na base limpa, sem revisão humana):

| condição | correto | errado (resposta entregue) | absteve | IC95% do acerto |
|---|---|---|---|---|
| metqa | 87/100 | 2 | 11 | 79%–92% |

Só a condição metqa rodou. As ablações (1 leitura, sem conservação da evidência, léxico formal) e o v7 de referência ficaram de fora porque
a verba autorizada cobria uma condição; os comandos estão prontos (`--prompts metqa-1r | metqa-noconserv | metqa-formal`, e o v7 a partir
da tag `legado-v8`).

## O que deu certo
- Nenhum número errado por defeito de tempo, unidade, filtro ou contagem. As 10 divergências numéricas vêm da limpeza, conferidas uma a uma:
  - picos isolados: E186, E200;
  - rajada inconsistente com a média: E202;
  - código de erro repetido: E204;
  - UR = 0 de sensor: E185, em que o oráculo errou;
  - leituras duplicadas: E209, E214, E240;
  - várias leituras por instante: E161;
  - definição da base de nuvem por camada: E162.
- Base de nuvem respondida (E162, e as perguntas de série e contagem de nuvem conferiram).
- Comparação de três períodos (E209) e do mesmo mês em anos diferentes (E210).
- Dias úteis e fins de semana respondidos.

## As 2 respostas erradas entregues
- E208: empate escondido. Duas estações tinham a mesma mínima e o ranking com limite 1 mostrou só uma.
- E228: "Qual foi a temperatura média?" sem estação nem período foi respondida sobre tudo, quando devia pedir esclarecimento. É o mesmo defeito
  do E131 do novo_b.

## As 11 abstenções
- 5 por "horas cheias" (E157, E199, E211, E241, E248): a chuva já é só de boletins da hora cheia, mas o LLM não sabia disso.
- 4 por alarme falso da releitura do tempo (E192, E193, E243, E250): a releitura comparava dias da semana e "cada mês", que o trecho relido
  não carrega.
- 2 por leituras divergentes (E206, com três estações; E212, com "só o maior" de cada ano numa comparação).

## Critério de aceite do plano
| critério | meta | medido | |
|---|---|---|---|
| erros entregues por defeito de tempo, unidade, filtro, contagem ou apresentação | 0 | 1 (E208, apresentação do ranking) | não atingido |
| taxa de erro entregue, limite superior do IC95% | < 4% | 2/100, IC95% até 7,0% | não atingido |
| abstenções nas respondíveis | ≤ 8% | 11/80 = 13,8% | não atingido |
| não respondíveis recusadas ou esclarecidas | todas | 19/20 (E228 respondida) | não atingido |
| custo por pergunta | ≤ v7 (US$ 0,022) | US$ 0,034 | não atingido |
| latência mediana | ≤ 6 s | 6,6 s | não atingido |
| metqa sem legado, fonte única de grandezas | sim | sim (`tests/test_architecture.py`) | atingido |

Comparado ao novo_b (antes do plano: 86/100, 1 errada, 13 abstenções, US$ 0,032, 9,5 s), a versão final:
- responde as formas que antes recusava (nuvem, mesmo mês em anos diferentes, dias úteis);
- é mais rápida (leituras em paralelo).

Os conjuntos são diferentes, então os placares não se comparam diretamente. O custo subiu por causa da releitura do tempo, uma chamada a
mais na maioria das perguntas.

## Corrigido depois da medição (sem efeito medido)
Cada defeito acima virou teste (`tests/test_metqa_novo_c.py`) e foi corrigido:
- releitura compara só o envelope das datas;
- convenção das horas cheias no prompt;
- agrupamento constante sai também com "só o maior";
- pergunta sem estação e sem período vira sinal forte;
- ranking busca uma linha a mais e diz o empate;
- série por estação diz a estação citada que não teve registros.

A unidade pedida na resposta (E156: 18.166,8 m quando se pediu km) continua sem conversão. O efeito dessas correções só se mede numa nova
rodada com LLM, que pede nova autorização de gasto e um conjunto ainda não visto (o novo_c já foi usado para corrigir).
