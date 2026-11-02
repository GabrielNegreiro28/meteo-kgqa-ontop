# MVP (metqa) no conjunto novo_b_100_20261028_validado

Rodada única, commit 3b09a69, 2026-10-31, modelo do kgqa.env, grafo real. Conjunto congelado em `eval/frozen/novo_b_100_20261028_validado`
(100 perguntas: 79 respondíveis, 13 não respondíveis, 8 que pedem esclarecimento), com oráculos conferidos em `docs/validacao_novo_b_100_20261028/`.

Custo: US$ 3,16 (US$ 0,032 por pergunta). Tempo: 9,5 s por pergunta.

Placar adjudicado (`python -m eval.adjudicate novo_b_100_20261028_validado metqa=metqa_1`, vereditos em
`docs/julgamento_novo_b_100_20261028_validado_veredictos.yaml`, julgamento do Claude sem revisão humana):

| condição | correto | errado (resposta entregue) | absteve | IC95% do acerto |
|---|---|---|---|---|
| metqa | 86/100 | 1 | 13 | 78%–91% |

- Nenhum número errado por defeito de consulta. As 7 divergências numéricas vêm de limpeza ou definição, conferidas na base limpa:
  picos isolados descartados pela Q3/Q5 (E74, E95, E98, E99, E105), várias leituras por instante (E60) e leituras duplicadas (E102).
- A resposta errada (E131): "Quanto tempo durou a chuva em SBLP?" foi respondida sobre todo o histórico em vez de pedir o período.
- As 13 abstenções:
  - 6 alarmes falsos de confirmação: E58, E70, E87, E94, E112, E141;
  - 3 comparações do mesmo mês em dois anos (COMPARISON_SHAPE): E111, E113, E114;
  - 3 sobre base de nuvem, que não era grandeza: E55, E81, E93;
  - 1 pelo limite de 6000 caracteres do filtro de dias da semana: E149.
- E78 e E84 tinham a contagem 0 certa, dita como "não há registros". A Fase 1 do plano corrigiu isso, e defeitos de texto encontrados
  na rodada (ano "2.016", diferença de contagem com unidade) também.

Plano de correção: `docs/PLANO_ARQUITETURA_FINAL.md`.
