# Comparação v6 × v4 no grafo real — conjunto novo (RF01–RF16)

Mesmas 16 perguntas, mesmo modelo (`gpt-6-luna`), mesmo grafo (Ontop sobre PostgreSQL), mesmo índice, uma execução por condição, 23/10/2026.
`v4` = o sistema antes da mudança. `v6` = `v4` + forma do resultado (`group_by`, `attributes`, `order`), com a consulta montada por código.
Arquivos: `RESULTADOS_LLM_REAL_v4_real_fresh_v4.md`, `RESULTADOS_LLM_REAL_v6_real_fresh_v6.md`, `eval/reports/llm_run_{v4,v6}_real_fresh_*.json`.

## Resultado

| | v4 | v6 |
|---|---:|---:|
| status final igual ao esperado | 13/16 | **16/16** |
| respondíveis (11) com resultado conferido | 7 | **11** |
| abstenções indevidas | 3 (RF03, RF04, RF06) | 0 |
| respostas julgadas erradas | 1 (RF01, ver abaixo) | 0 |
| falsa ausência de registros | 0 | 0 |
| chamadas ao LLM | 38 | **22** |
| custo | US$ 0,525 | **US$ 0,293** (−44%) |

## Por pergunta

| id | forma | v4 | v6 |
|---|---|---|---|
| RF01 | precipitação por mês | "errada" (formato) | correta |
| RF02 | 3 estações com maior temperatura média | correta | correta |
| RF03 | velocidade média **por cabeceira** | recusada | correta |
| RF04 | maior velocidade e **em qual cabeceira** | recusada | correta |
| RF05 | precipitação por dia | correta | correta |
| RF06 | medições de pressão **por ano** | erro de execução | correta |
| RF07 | 2 direções de vento mais frequentes | correta | correta |
| RF08 | umidade mínima **por estação** (3 estações) | correta | correta |
| RF09–RF11 | média, dia local, contagem com filtro (formas simples) | corretas | corretas |
| RF12–RF16 | recusas (cidade, grandeza inexistente, fora da cobertura, data relativa, agrupamento inexistente) | todas certas | todas certas |

## Como ler (limites)

1. **O ganho vem de três perguntas, não de oito.** O `v4` também acertou RF02, RF05, RF07 e RF08: o modelo escreve o `GROUP BY` mesmo sem o esquema ter o campo. Onde o `v4` falhou foi (a) **atributo** (RF03, RF04: a cabeceira não existia no esquema) e (b) **uma consulta que o Ontop recusa** (RF06). O `v6` elimina os dois casos.
2. **A "resposta errada" do `v4` (RF01) é diferença de formato, não de valor.** Conferi mês a mês contra o oráculo: os 12 totais e as 12 contagens são iguais. Faltou a coluna `year` e o mês veio como texto `"2021-01"`. O juiz estrito a marca errada. Em substância o `v4` não entregou nenhum número errado neste conjunto.
3. **O conjunto favorece o `v6` por construção.** Eu o escrevi já conhecendo as capacidades novas e os modos de falha da medição anterior. Ele mede se o `v6` funciona nas formas para as quais foi feito, não se é melhor em perguntas arbitrárias. A medida limpa anterior (split test, 7/12) continua sendo a única fora desse viés, e RT04 (filtro categórico) segue sem suporte.
4. **n = 16, um modelo, uma execução por condição**, sem intervalo de confiança. O modelo varia entre execuções com o mesmo código (já visto com RD07).
5. **Custo:** o `v6` gasta uma chamada nas formas novas (~US$ 0,014) porque a consulta e a resposta saem do código. A economia é real, mas vem da montagem determinística, não de o modelo ser melhor.
6. As recusas de Curitiba (RF12) e de "gênero de nuvem" (RF16) vieram do **próprio modelo** (`UNSUPPORTED_BY_MODEL`), não de uma regra. A regra `ENTITY_TEXT_MISMATCH` não foi exercitada aqui.

## Achado novo (v4, RF06)

O Ontop recusa `GROUP BY (YEAR(?t))` com a projeção `(YEAR(?t) AS ?ano)` (HTTP 400, "non-aggregate expression … not allowed in projection"). O `rdflib` aceita. É a segunda consulta que o `rdflib` aceita e o Ontop não (a primeira foi `BIND` com nome em uso, D-43). No `v6` as formas de agrupamento são montadas por código e evitam isso; consultas escritas pelo LLM (formas simples) continuam expostas.
