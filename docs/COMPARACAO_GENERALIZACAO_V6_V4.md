# Generalização v6 × v4 no grafo real — conjunto RG (24 perguntas)

Mesmo modelo (`gpt-6-luna`), mesmo grafo, uma execução por condição, 23/10/2026. `v4` já com a regra do P-36. Perguntas e oráculo escritos **antes**
de rodar o LLM, validados (19/19 consultas de referência × oráculo pandas). Arquivos: `eval/questions_real_gen.yaml`, `eval/oracle_real_gen.py`,
`eval/reports/llm_run_{v4,v6}_real_gen_*.json`. Custo: v4 US$ 0,935; v6 US$ 0,840 (RG24 rodou à parte porque o teto da execução cortou a rodada em RG23).

## Resultado

| | v4 | v6 |
|---|---:|---:|
| status final igual ao esperado | 22/24 | 21/24 |
| respondíveis corretas (de 19) | 15 | 15 |
| respostas erradas entregues | 2 (RG13, RG14) | 2 (RG17, RG18) |
| falsa ausência de registros | 1 (RG18) | 1 (RG09) |
| abstenção indevida | 1 (RG16) | 1 (RG11) |
| respondeu o que devia recusar | 0 | **1 (RG19)** |
| chamadas ao LLM / reparos | 72 / 14 | 61 / 11 |
| custo | US$ 0,935 | US$ 0,840 (−10%) |

**Neste conjunto o v6 não é melhor que o v4**: as mesmas 15 corretas, o mesmo número de falsas ausências, e um erro a mais de tipo grave (RG19). A economia de custo caiu de
−44% (no conjunto RF) para −10%: nas perguntas simples o v6 gasta o mesmo que o v4, e a vantagem só aparece onde a consulta é montada por código.

## Causa de cada falha (verificada nas consultas e respostas)

| id | versão | o que aconteceu | causa |
|---|---|---|---|
| RG09 | v6 | "sem registros" onde há dados | estação via `VALUES` + `met:reportOf` ao contrário; Estação, Boletim e Observação não eram tipos incompatíveis |
| RG18 | v4 | "sem registros" onde há dados | `?station met:reportOf ?report . ?report met:reportOf st:SBPA`: mesma causa |
| RG11 | v6 | `unsupported` | a pista "quantas vezes" forçava `group_by: value`; era contagem com filtro. **Defeito meu** |
| RG13, RG14 | v4 | total no lugar da série | as regras novas barraram a consulta do LLM e o compilador de reserva ignorava "mensal" e "anual" |
| RG16 | v4 | `unsupported` | a cabeceira não existe no esquema do v4 (esperado) |
| RG17 | v6 | tabela de 36 valores, não a direção mais frequente | superlativo no singular não virava ranking de 1. **Sonda deliberada** |
| RG18 | v6 | máximo de UMA leitura horária (35,2 mm) no lugar da soma do dia (45,6 mm) | idem + "mais chuvoso" lido como máximo. **Sonda deliberada** |
| RG19 | v6 | média de TODAS as estações apresentada como "da capital de São Paulo" | o lugar foi descartado em silêncio (o v4 recusou; pode ser variação do modelo) |

## O que foi corrigido (sem LLM) e o que NÃO está provado

Correções (D-53 a D-58, `DECISOES.md`): tipos incompatíveis declarados para o verificador (Estação × Boletim × Observação), "quantas vezes" fora da pista de agrupar por valor,
mensal/anual/frequência/moda no compilador de reserva, superlativo singular = ranking de 1, "dia mais chuvoso" = soma por dia, lugar não-estação = `unsupported`.
Cada uma tem teste com a consulta ou a pergunta exata que falhou, e a varredura em ~100 perguntas de todos os conjuntos acha **zero falsos positivos**.

**Isso não foi remedido com o LLM.** As correções saíram deste conjunto, então ele deixou de ser medida limpa. Que as regras barram as consultas e interpretações que falharam
está provado; que o modelo, depois do reparo, produz a resposta certa não está.

## Como ler (limites)

- **Este conjunto é parcialmente adversarial ao v6 por desenho** (RG17 e RG18 são sondas de buracos que eu já conhecia), e o conjunto RF favorecia o v6 por construção.
  Não há como dizer, com estes dados, onde está a generalização real (a faixa entre os dois conjuntos não é um limite estatístico). Sem as duas sondas, o v6 teria 2 erros a menos, mas a conclusão "não é melhor que o v4" não muda sem elas.
- n = 24, um modelo, uma execução por condição, sem intervalo de confiança. O modelo varia entre execuções (RG19 pode ter sido sorte do v4).
- O teto por execução (US$ 0,80) cortou a rodada do v6; o RG24 foi rodado depois, sem alterar o código.
