# Medição no conjunto inédito estudo2_20261125 (gpt-6.2-sol, diretrizes gerais)

Rodada única, 25/11/2026, condição completa, uma repetição. Código: branch `correcoes-estudo` com as diretrizes gerais (D-119, D-121, D-122),
ainda sem commit; versões gravadas na procedência de cada resposta. LLM: gpt-6.2-sol, esforço medium (variáveis de ambiente, o `kgqa.env`
não foi alterado). Conjunto de um segundo agente separado, congelado antes da execução (`eval/frozen/estudo2_20261125`), com referências em
SQL sobre a mesma base limpa que o sistema consulta.

Verba autorizada: US$ 10. Gasto estimado no ledger: US$ 4,97, com o preço conservador de US$ 3/15 por milhão de tokens; pelos tokens
registrados (1,23 milhão de entrada, 85 mil de saída), a US$ 2/10 seriam US$ 3,32. Latência mediana de 7,2 s. Trilhas em
`eval/reports/estudo2_20261125_sol_b1..b4/events.jsonl` (fora do git).

## Placar (120 perguntas)

| | estrito (`eval.study`) | adjudicado |
|---|---|---|
| corretas | 89/120 | 92/120 (77%) |
| respondíveis | 54/80 | 57/80 |
| esclarecimento esperado | 19/20 | 19/20 |
| fora do escopo esperado | 16/20 | 16/20 |
| respostas a respondíveis certas | 54 de 57 | 57 de 57 |
| respostas erradas entregues | 4 | 0 |

Diferenças, conferidas uma a uma:
- T104 e T075 (sem dados no período): o sistema disse corretamente que não há registros; o comparador estrito falha porque o Ontop devolve
  agregado 0 com n = 0 onde a referência tem nulo (o mesmo defeito do primeiro estudo).
- T069 ("quantos boletins de vento calmo teve a Base Aérea de Natal em 2019"): o sistema contou 85 boletins com vento 0 kt; a referência
  conta 119 LEITURAS com condição calma (uma por cabeceira). A pergunta pede boletins: erro da referência.
- T120 (2014): "não há registros, os dados cobrem 2016–2025", sem número, com status `no_results` em vez de `unsupported`.

Para comparação, o primeiro estudo (outro conjunto, gpt-6-luna, regras anteriores) teve 80/120 adjudicadas e 2 respostas erradas. Conjuntos
diferentes: a diferença não é atribuível só ao modelo ou só às diretrizes.

## As 23 abstenções nas respondíveis

| causa | perguntas | natureza |
|---|---|---|
| ranking sem lugar ("os 5 aeroportos com maior umidade"): o modelo pergunta se são todas as estações | T014, T031, T048, T059, T064, T072, T108, T112 | diretriz faltando: ranking sem lugar = todas |
| "Porto Alegre" com duas estações: SBCO (base aérea de Canoas) consta na fonte como "atende Porto Alegre" | T032, T066, T092, T106 | efeito colateral da cidade atendida |
| Goiânia com duas estações | T105 | convenção |
| filtro por gênero ou cobertura da camada de nuvem | T056, T089, T117 | capacidade que falta |
| condição sobre leituras com agrupamento | T067, T116 | capacidade que falta |
| "falta evidência explícita para calc" em chuva sem palavra de cálculo ("chuva dia a dia", "chuva ... em mm") | T033, T070 | regra de evidência rígida |
| número de data na forma ("24/12/2022") tratado como sem uso | T078 | conservação da evidência |
| "ano a ano" sem período; temperatura da pista sem estatística | T074, T100 | ambiguidade defensável |

## Não respondíveis (40)

Nenhuma recebeu número. Esclarecimento: 19 de 20 (T006 "horas de nevoeiro" foi recusada como grandeza inexistente). Fora do escopo: 16 de
20; em 3 o sistema pediu a estatística antes de notar que não há dados (lugar sem estação, ano fora da cobertura) e em 1 deu `no_results`.

## Leitura

- Todas as 57 respostas a perguntas respondíveis estão certas contra o oráculo independente (depois de corrigir a referência da T069).
- As abstenções mudaram de natureza: sumiram as de nomes e regiões que o cadastro não conhecia; apareceram as de ranking sem lugar (8),
  que é uma diretriz faltando, e as de Porto Alegre (4), que vêm de um dado da fonte (SBCO "atende Porto Alegre").
- Uma condição, uma repetição e um conjunto: não mede a variação entre rodadas nem separa modelo e diretrizes.
