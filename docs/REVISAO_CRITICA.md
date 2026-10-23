# Revisão crítica da arquitetura e da implementação

Escrita **antes** de rodar o benchmark final (os critérios de sucesso da seção 3 foram fixados antes de ver os números).
Lê o que existia ao fim da 2ª rodada (`ESTUDO_SEGURANCA_PIPELINE.md` §6.3), aponta os pontos fracos, diz o que foi mudado e
como cada mudança foi verificada **sem gastar com o LLM**.

## 1. Pontos fracos encontrados

Gravidade: **A** = deixa passar resposta errada ou derruba a pipeline; **M** = custo/abstenção desnecessária ou risco
de generalização; **B** = higiene.

| # | Ponto fraco | Gravidade | Como apareceu |
|---|---|---|---|
| 1 | **A interpretação não era conferida contra a pergunta.** L3 só confere *consulta = interpretação*. Se o LLM omite a estação citada, troca "média" por "máximo", desloca o período ou inventa um limite, a consulta segue a interpretação errada e passa por todas as regras. Era o "limite conhecido" do estudo. | A | leitura do fluxo; teste que já documentava o limite |
| 2 | **JSON válido ≠ interpretação válida.** `"entities": ["SBGR"]`, `"period": "2024"`, `"aggregation": ["avg"]` levantavam `AttributeError`/`TypeError` no meio da pipeline (exceção não tratada), e `_to_interpretation` usava `list("met:AirTemperature")` (vira lista de letras). | A | leitura de `validate_interpretation`; reproduzido por teste |
| 3 | **Estação escolhida por rótulo não era conferida.** `?s rdfs:label "Estação X"@pt` passava em L3 mesmo sendo outra estação (L3 só olhava IRIs). | A | o controle ampliado reprovou a interpretação de T04 |
| 4 | **Valores trocados entre entidades passavam** (0/6 no experimento de texto). | A | já documentado como limite |
| 5 | **A resposta podia calar linhas ou dizer "não há registros" com dados.** A checagem só vê se cada número citado existe, não se algum falta, nem a contradição com o status. | M | leitura de `check_answer` |
| 6 | **Data relativa ("ontem") era palpite.** O LLM não tem relógio; qualquer data escolhida seria apresentada como fato. | A | leitura do prompt: nada tratava isso |
| 7 | **Período fora da cobertura dos dados** dava "sem registros" sem dizer que os dados só cobrem outro intervalo. | M | leitura |
| 8 | **O contexto da ontologia ia inteiro também para a etapa 1** (interpretar), que não usa caminhos de tempo: ruído e custo (v3 ≈ 40% mais caro), coincidente com a regressão de ambiguidade em D01. | M | comparação A × B |
| 9 | **A etapa 2 era geração livre apesar de a ontologia já determinar o caminho.** Rejeição após o reparo = usuário sem resposta. | M | leitura da arquitetura; medido o que um compilador acertaria (§2.6) |
| 10 | **Teto de gasto por execução, não acumulado.** Foi assim que o total chegou a ~US$ 7,4 contra um teto de US$ 5 no `kgqa.env` sem que nenhuma regra visse. Erro meu. | A (processo) | gasto estimado vs teto |
| 11 | **Prompt injection pelo texto da pergunta e pelos dados.** `</pergunta>` na pergunta, ou `</resultados>` num valor do grafo, fechava a marcação que delimita o dado. | M | leitura |
| 12 | **"Sem registros" passava pelo LLM só para redigir uma frase fixa:** uma chamada paga e uma superfície de alucinação sem ganho. | M | leitura |
| 13 | **O perfil dos dados só existia para o grafo sintético.** No grafo real, quem diz o que está populado é o mapeamento do Ontop; `RELATION_WITHOUT_DATA` nunca foi exercitada contra as consultas reais. | M | já listado como pendência |
| 14 | **O usuário não via como a pergunta foi entendida.** Um erro de interpretação coerente só é detectável por quem pergunta. | M | já listado como pendência |
| 15 | **Controle de falso positivo pequeno:** só 9 interpretações de referência. Cada regra nova podia estar barrando perguntas corretas sem que se visse (custo real: abstenção). | M | leitura de `run_control` |

Pontos que **continuam abertos** (não resolvidos nesta revisão): a intenção ampla do usuário (o que significa "mais quente"),
afirmações qualitativas na resposta ("a mais alta"), troca de valores quando o número vem *antes* da menção à entidade,
generalização das regras para outros grafos (cada rodada anterior achou uma família nova), e tudo o que depende de Ontop
real (não há Ontop neste ambiente).

## 2. O que foi mudado

1. **Interpretação fundamentada na pergunta (camada L4)** — `pipeline/validators.py::_ground_in_question`. Regras sem LLM:
   grandeza nomeada pelos rótulos da ontologia (`link_properties`, rótulo mais longo vence), estações citadas
   (`link_entities`, sem acento/caixa; omitida ou inventada), valor do filtro presente na pergunta, datas e anos da
   pergunta = período, período sem nenhuma referência de tempo, palavras de agregação (média, total, quantas…).
   Consultas de instante ("às 12h") não exigem período. Ativa em `v4`.
2. **Esquema estrito** (`BAD_SCHEMA`) antes de qualquer outra regra; `_to_interpretation` sem coerção.
3. **Estação por rótulo** passa a entrar na conformidade (`ENTITY_MISMATCH`).
4. **Associação entidade–valor** na resposta (`ENTITY_VALUE_SWAP`): o texto é cortado nas menções às entidades dos
   resultados e cada número tem de ser da entidade anterior a ele. Mais `ANSWER_OMITS_ROW` e `ANSWER_CONTRADICTS_STATUS`.
5. **Porta de data relativa antes do LLM** (zero chamadas, status `needs_clarification`) e **porta de cobertura**
   (período fora dos dados → resposta determinística dizendo onde os dados estão).
6. **Contexto por etapa** (v4): interpretar recebe só rótulos e **dicas determinísticas** (o que as regras já reconheceram
   na pergunta); gerar recebe o contexto da ontologia.
7. **Compilador determinístico** (`pipeline/compiler.py`) como rede de segurança *restrita*: só onde a forma da resposta é
   determinada (agregação com uma estação, ou "por estação"). Medição prévia: se ele atuasse em tudo, **6 de 23** casos de
   referência seriam respondidos com uma pergunta diferente da feita (superlativo, ranking, comparação, série por dia,
   lista de leituras) e passariam em todas as regras; por isso foi restringido, e há teste para cada caso recusado.
   Toda consulta compilada passa pelas mesmas regras e é sinalizada (`COMPILED_QUERY`) e contada à parte nas métricas.
8. **Registro persistente de gasto** (`pipeline/ledger.py`): o teto vale para a soma de todas as execuções; passar dele
   exige autorização registrada (quem e por quê). Guarda só custo/tokens, nunca chave nem texto.
9. **Higiene de prompt**: `<`/`>` da pergunta neutralizados; `<` dos dados escapado no JSON; resposta de "sem registros"
   gerada sem LLM; **eco da interpretação** em texto montado só da interpretação validada.
10. **Perfil dos dados do Ontop** (`obda_profile`, `with_profile_from_obda`): as consultas de referência reais passam
    pelas regras de vocabulário com o perfil do `.obda` (0 falsos positivos em `RELATION_WITHOUT_DATA`).
11. **Controle ampliado**: `eval/reference_interpretations.py` completa as interpretações corretas de todas as
    perguntas respondíveis (9 → 26); nenhuma regra pode barrá-las, nem com a consulta de referência.

## 3. Verificação sem LLM (feita antes do benchmark)

| Verificação | Resultado |
|---|---|
| Testes automatizados | 298 passam, 1 pulado (real-pipeline exige Ontop/PostgreSQL e fica de fora) |
| Controle: 26 interpretações corretas × todas as regras × consulta de referência | **0 achados** (T12 revelou uma interpretação de referência minha incompleta; corrigida, não a regra) |
| Injeção de falhas na **interpretação** (coerentes, L3 não vê) | **47/55 = 85%** barradas por L4 (antes: 0%) — `RESULTADOS_INJECAO_FALHAS.md` §3b |
| Injeção de falhas no **texto** | troca de valores **6/6** (antes 0/6) com formato de linhas; linha omitida 6/6; "não há registros" com dados 16/16 |
| Mutantes de consulta | 128 aplicáveis, 0 falhas silenciosas sem barreira (a nova "rótulo de outra estação" é barrada por L3) |
| Compilador × oráculo | 12/12 dos casos compiláveis batem com o oráculo; 14/14 dos demais são recusados |

Não barradas pelo experimento de interpretação (8 de 55): `D05` agregação trocada/omitida e grandeza trocada (a pergunta
"Quanto choveu…" não traz palavra de agregação nem rótulo da grandeza), `T03/T04` agregação omitida (superlativo sem
palavra de média/total), `T07` período inventado (a pergunta tem "dias"), `T11` período omitido/deslocado ("toda a semana"
não tem data). São o limite honesto do que se decide por texto, sem entender a intenção.

## 4. Critérios de sucesso do benchmark (fixados antes de rodar)

Três condições sobre as duas suítes (24 sintéticas + 10 held-out = 34 perguntas), mesmo modelo, mesmas regras de consulta
(L1–L3 atuais valem em todas): **A = v1** (só rótulos), **B = v3** (ontologia em todas as etapas), **C = v4** (esta revisão).

- **Segurança (principal):** C entrega **0 respostas erradas** *e* não tem mais falsas ausências de registros que A.
- **Utilidade:** C acerta pelo menos tantas respondíveis quanto A, e não se abstém mais que A em perguntas respondíveis.
- **Custo:** C não custa mais de 1,3× B.
- Se C não cumprir, o resultado entra no relatório como está. Consultas montadas pelo compilador são contadas à parte,
  não como acerto do LLM.
- Limites que continuam valendo: n pequeno (34), um só modelo, uma ou duas repetições; as suítes foram usadas para
  achar regras (a held-out só é limpa para as regras criadas depois dela).

## 5. A primeira execução da v4 (C1) falhou nos critérios acima — e o que foi mudado por causa disso

Rodei a v4 nas 34 perguntas (US$ 1,09) **antes** de A e B, e interrompi a campanha ao ver o resultado, para que A e B não
rodassem com código que eu ia mudar. Arquivos preservados: `eval/reports/llm_run_v4_c1_syn.json`, `llm_run_v4_c1_held.json`,
`docs/RESULTADOS_LLM_REAL_v4_c1_*.md`.

| C1 (v4, 1ª versão) | sintética (24) | held-out (10) |
|---|---:|---:|
| respondíveis corretas | 9/10 | 7/7 |
| **respostas erradas entregues** | **1 (T10)** | 0 |
| falsa ausência de registros | 0 | 0 |
| abstenções indevidas | **9** | 2 (H05, H07) |

Critério de segurança (0 erradas): **não cumprido**. Utilidade (abstenções ≤ A): **não cumprida** (A teve 2–3 nas rodadas
anteriores). As causas, todas minhas:

1. **O prompt v4 produziu abstenção em massa.** Eu escrevi "não deduza período… que a pergunta não traga"; o modelo passou a
   responder "informe o período" para quase toda pergunta sem data (D02, D03, T05, T07, T08, T11, T12, T16). A política
   correta é: **sem período = todo o histórico; sem estação = todas; o sistema diz isso na resposta**. É uma decisão de
   política (do sistema, determinística e divulgada), não do LLM. Agora está no prompt e no eco da interpretação.
2. **T10 marcada como "errada" — e meu diagnóstico inicial estava errado.** Pensei que "ao meio-dia" virara período de dia
   inteiro e a consulta devolvera a previsão errada. Ao olhar o oráculo depois: o valor entregue (35,0 °C) **estava certo**; o
   comparador marcou "errada" porque a resposta omitiu o identificador da previsão e o instante de emissão (que a referência
   exige: "resposta deve ser marcada como previsão, com instante de emissão"). Ou seja, era resposta **incompleta**, não
   errada. A mudança de fundo continua justificada (a interpretação não tinha como dizer "um instante", e `G03` com a v1
   mostrou o problema real: a consulta do dia inteiro devolveu 4 leituras onde se pediu uma), mas o motivo que escrevi aqui
   na primeira versão deste parágrafo era falso. Corrigido o **veredito**: `eval/compare.py::judge` agora separa
   `wrong` de `incomplete` (só respostas de UMA linha; faltam colunas sem número) e `order_only` (mesmas linhas, outra
   ordem), e o relatório mostra os três à parte. Reavaliei as seis execuções com o veredito novo, sem LLM. Campo `instant`
   na interpretação (ISO com fuso), conferido contra a pergunta (L4) e contra a consulta (L3).
3. **A etapa 2 insistiu na estação como objeto de `sosa:hasFeatureOfInterest`** (T09 rejeitada após o reparo; o primeiro
   rascunho do modelo estava quase certo e o reparo piorou). O contexto da ontologia agora traz, **derivado dos axiomas**, os
   dois caminhos válidos da estação até a observação (`hosts`/`madeBySensor` e `siteOf`/`hasFeatureOfInterest`) e a
   consequência da disjunção herdada ("`met:WeatherStation` é `sosa:Platform`, logo nunca é `sosa:FeatureOfInterest`").
4. **Grandeza prevista pela ontologia mas sem dados (vento, pressão)** virava pedido de esclarecimento. Agora é decisão
   determinística, antes das demais regras: `unsupported` (`PROPERTY_WITHOUT_DATA`), sem chamar a etapa 2.
5. **A etapa 3 em JSON produziu 5 saídas inválidas** (cada uma custou um reparo). Em v4 a resposta é texto livre; as regras
   já conferem o conteúdo.
6. **Defeito da minha medição:** a "1ª tentativa" comparava a *primeira* interpretação (talvez recusada e reparada) com a
   consulta gerada da interpretação *reparada*, fabricando `ENTITY_MISMATCH` em D01/D04/T03. Agora usa a interpretação aceita.

**Consequência para a validade do benchmark.** Estas correções foram derivadas das falhas de C1 nas suítes sintética e
held-out, então **nessas duas suítes a versão final da v4 não é mais uma medida limpa**. Para ter uma medida limpa criei o
conjunto **fresh (G01–G10)**, escrito *depois* de todas as correções e nunca usado para ajustar regra ou prompt (cobre o que
as revisões mudaram: instante, data fora da cobertura, grandeza sem dados, data relativa, estação desconhecida). Os critérios
de §4 passam a valer **na suíte fresh**; sintética e held-out entram como contexto, com esta ressalva.

Verificações adicionais sem LLM antes da nova campanha: 288 testes passam; um LLM *perfeito* roteirizado, nas 3 suítes
(todas as perguntas respondíveis, 33 casos), chega ao status e ao resultado do oráculo em **todos** (nenhuma regra recusa o
que está certo); o gabarito da suíte fresh foi validado por teste antes de medir.

**Orçamento.** A campanha refeita roda C(v4) e A(v1) nas três suítes. **B (v3) não é rerodada**: o saldo autorizado
(US$ 3,41 restantes dos 4,5) não cobre as 3 condições; a evidência de B é a das rodadas anteriores (menos segura que A).

## 6. Resultado da campanha final (A × C, 44 perguntas, 3 suítes)

Código final em todas as execuções, exceto onde indicado. B (v3) **não** foi rerodada (saldo autorizado). Arquivos:
`docs/COMPARACAO_FINAL.md`, `docs/RESULTADOS_LLM_REAL_{v1,v4}_f_{fresh,synthetic,heldout}.md`, `eval/reports/llm_run_*_f_*.json`.
Gasto desta campanha e das tentativas anteriores nesta revisão: **US$ 4,08** (ledger: acumulado US$ 11,48 de US$ 11,90).

| | A (v1) | C (v4) |
|---|---:|---:|
| status final igual ao esperado | 23/44 | **41/44** |
| respondíveis corretas | 16/17 | **29/30** (1 incompleta, 1 em outra ordem) |
| **respostas erradas entregues** | 1 (G03) | **1 (H02)** — corrigida depois, ver abaixo |
| respondeu o que devia recusar/esclarecer | 2 (G08 inventou "ontem"; T14*) | 0 |
| abstenções indevidas | **17** | 3 (T05, T11, H07) |
| 1ª consulta correta | 16 | 27 |
| custo (US$) | 0,78 | 1,17 |

\* T14 (pressão): o gabarito dizia `unsupported` por vento/pressão não existirem na ontologia; na ontologia v0.2 existem, sem dados.
Em C isso virou decisão determinística (`PROPERTY_WITHOUT_DATA` → `unsupported`); em A foi respondido como "sem registros".

**Por suíte (C):** fresh 10/10 status, 6/6 corretas, 0 erradas; sintética 22/24, 17/17 corretas, 0 erradas; held-out 9/10,
6/7 corretas, **1 errada (H02)**. **Ressalva de validade:** só a suíte *fresh* é medida limpa; as correções foram derivadas de
falhas na sintética e na held-out. E a fresh foi escrita para exercer o que as revisões mudaram (instante, cobertura, grandeza
sem dados, data relativa), então ela favorece C por construção: a comparação mostra que as capacidades novas funcionam, não
que C seja melhor em perguntas arbitrárias. Um modelo, 44 perguntas, uma execução por condição: sem intervalo de confiança.

### O erro de C que a campanha achou (H02) — causado pela minha própria mudança

O contexto da ontologia passou a listar os **dois caminhos válidos** da estação até a observação. O modelo os juntou com
`UNION` e entregou **42,6 mm onde o correto é 21,3 mm** (n = 16 no lugar de 8): cada observação contada duas vezes, a
consulta válida, o vocabulário certo, e **nenhuma regra viu** (a 1ª tentativa estava classificada como `silent_wrong`).
Mais uma família de erro silencioso, desta vez **criada por dar mais informação ao modelo**. Correção: regra
`UNION_WITH_AGGREGATE` (L2) e uma linha no contexto dizendo que os caminhos são alternativos. Reaplicação do erro gravado:
barrado. Rerodei 6 perguntas agregadas depois da correção (H01, H02, H03, H08, G01, G02): **6/6 corretas**. Isso confirma que
a correção funciona nesses casos; **não** mede se há outras formas de duplicar linhas.

### Critérios de §4 (fixados antes)

- *0 respostas erradas em C e não mais falsas ausências que A*: **cumprido só depois da correção, e só nas 6 reexecutadas**.
  Na campanha como rodada, C entregou 1 errada (A também, 1). Falsas ausências: 0 e 0.
- *C acerta ao menos tantas respondíveis quanto A e não se abstém mais*: **cumprido** (29 × 16 corretas; 3 × 17 abstenções).
- *Custo ≤ 1,3× B*: **não verificável** (B não foi rerodada). Contra A, C custa 1,5×, mas por resposta correta custa menos
  (US$ 0,040 × 0,049).

### O que continua aberto

- Outras formas de duplicar linhas (junção com relação multivalorada) e outras famílias não vistas: cada campanha achou uma.
- Intenção ampla (T05 "três maiores…" ficou `unsupported`; H07 "quando foi emitida a previsão" também): abstenções que o
  sistema não sabe resolver, porque a interpretação não tem como expressar ranking nem atributo da previsão.
- Troca de valores em listas paralelas ("A/B: x / y") e afirmações qualitativas na resposta continuam fora do alcance.
- O compilador determinístico **não foi acionado** em nenhuma pergunta da campanha (0 consultas montadas): está testado, mas
  sem evidência de utilidade ao vivo.
- Tudo foi medido no grafo sintético com rdflib; nada com Ontop/PostgreSQL reais.

## 7. Verificação com o usuário (diálogo de confirmação)

Implementada em `pipeline/dialogue.py` e ligada em `run_pipeline(..., confirm=canal, confirm_policy, max_rounds)`. **Sem LLM
na camada**: o texto "Entendi sua pergunta assim — …" é montado só da interpretação já validada; a resposta do usuário é
classificada por regras (sim / não / cancelar / correção).

```
interpretar → validar (L2–L4) → [política pede confirmação?] ─ não → segue
                                     │ sim
                              mostra o texto ao usuário
              sim ──────────────────┤──> segue (fica registrado: USER_CONFIRMED, nº de voltas)
              correção ─────────────┘──> volta à etapa 1 com <interpretacao_anterior> + <correcao_do_usuario>,
                                          revalida por TODAS as regras e mostra de novo (limite: 3 correções)
              não (sem dizer o quê) ───> pergunta "O que devo corrigir?"
              cancelar ────────────────> NEEDS_CLARIFICATION, nada é consultado
```

Decisões:
- **Política `assumptions` (padrão):** pergunta quando o *sistema* assumiu algo que a pergunta não disse ("todas as estações",
  "todo o histórico") ou depois de uma correção; `always` e `never` existem. Pergunta totalmente explícita não incomoda o usuário.
- **O "sim" soma às regras, não as substitui.** A interpretação corrigida passa por esquema, ontologia, L3 e L4 como qualquer outra.
- **Com correções, L4 usa a última fala que trata de cada dimensão** (estação, datas, grandeza, agregação); checagens de
  *invenção* valem contra todas as falas; checagens de *omissão* ficam de fora, porque o usuário pode ter pedido para tirar algo
  (e vê o resultado na confirmação seguinte).
- **Data relativa numa correção** é recusada sem chamar o LLM; a interpretação atual é mostrada de novo.
- **A fala do usuário é dado:** limitada a 500 caracteres e com `<`/`>` neutralizados antes de ir ao LLM.
- Sem canal (`confirm=None`) o comportamento é o de antes.

Verificação: `tests/test_dialogue.py` (29 testes; usuário simulado): confirmar, corrigir, "não" simples, cancelar, não convergir
(para após o limite e nunca chama o LLM mais que 1 + 3 vezes), correção ignorada pelo modelo, injeção na correção, data
relativa, e que cancelar nunca consulta o grafo. Total da suíte: 327 testes. **Não medido com o LLM real** nem com usuários
reais: o que falta medir é se a correção em linguagem natural converge em poucas voltas e com que frequência o usuário confirma
sem ler. O experimento natural é simular usuários que corrigem de forma certa, errada e ambígua, e contar voltas e erros finais.

### 7.1 Teste com o LLM real e usuários simulados (`eval/run_dialogue_experiment.py`, `docs/RESULTADOS_DIALOGO.md`)

10 cenários, política `always`, `gpt-6-luna`, usuário roteirizado. Resultado final: **10/10 como esperado**, 1–2 correções no
máximo, US$ 0,03–0,06 por cenário. Mas o caminho até aí teve três coisas que valem registro:

1. **Execução acidental repetida (erro meu de processo).** Lancei o experimento por um script sem guarda `__main__`; o
   `multiprocessing` do executor (Windows, *spawn*) reimportou o script 9 vezes, cada uma reexecutando o experimento e
   **registrando uma autorização de gasto nova**. Custo real: ~US$ 0,56 (dentro da autorização de US$ 0,90), mas o registro
   passou a mostrar 8 autorizações que você não deu. Removi as 8 duplicadas (ficou uma e uma nota explicando) e os custos
   continuam registrados. Os resultados dessa execução (9 `execution_error`) foram descartados.
2. **Dois defeitos reais, achados pela 1ª execução válida** (arquivada em `dialogue_run_1.json` / `RESULTADOS_DIALOGO_1.md`,
   ainda com o juiz com bug, mas o texto das respostas está lá):
   - o usuário trocou "máxima" por "média" e a resposta dizia **"A temperatura máxima … foi 23,93"**;
   - o usuário trocou Serra Azul por Vale Verde e a resposta dizia **"umidade média da Estação Serra Azul foi 65,79 %"**
     (o número era da Vale Verde). Ambos vinham de a etapa 3 só ver a pergunta ORIGINAL.
   Correção: a etapa 3 recebe a interpretação confirmada (`<interpretacao>`) e as correções; nova regra L5
   `ANSWER_MENTIONS_OTHER_ENTITY` (a resposta não pode citar estação fora do escopo da consulta). Testes de replay.
3. **Viés de medição:** a 2ª execução (10/10) veio *depois* dessas correções, derivadas da 1ª. Não é medida limpa dessa correção.

O que os cenários mostram: confirmar, trocar agregação, trocar estação, acrescentar período, "não" simples, duas correções
seguidas, cancelar, correção vaga (o modelo respondeu com pedido de esclarecimento, sem inventar), injeção na correção
(ignorada; nenhuma consulta com `SERVICE` passou) e data relativa na correção (recusada sem reinterpretar).

Limites: usuários **simulados** e roteirizados (não medem quem confirma sem ler nem correções ambíguas reais); 10 cenários;
um modelo. Defeitos cosméticos vistos e não corrigidos: números sem arredondamento ("23,9333…") e, em um caso, "a unidade não
foi informada" (a variável do valor tinha nome fora do esperado pela derivação de unidade).

## 8. Varredura de segurança e robustez (arquitetura e scripts)

Leitura crítica de `kgqa/store.py`, `pipeline/*`, scripts de `eval/` e configuração. Cada item abaixo foi **verificado antes de
mudar** e tem teste em `tests/test_hardening.py` (33 testes; suíte total: 362).

| # | Achado | Risco | Correção |
|---|---|---|---|
| 1 | Pergunta sem limite de tamanho nem higiene | custo de tokens e de regex sem teto; ANSI/bidi/controle atravessam prompts, relatórios e terminal | `textsafe.clean`; limite de 1000 caracteres e pergunta vazia recusados **antes** de qualquer chamada ao LLM |
| 2 | Qualquer exceção inesperada derrubava a pipeline | falha **aberta**: erro não tratado, às vezes com detalhe interno | `run_pipeline` captura tudo e devolve `INTERNAL_ERROR` genérico; `validate_query` falha fechada (`ANALYSIS_ERROR`) |
| 3 | `p*` e `p+` aceitos no SPARQL | percurso ilimitado do grafo (custo no executor/Ontop) | recusados na política (L1); caminhos limitados (`/`, `^`, `?`, `\|`) continuam |
| 4 | Consulta sem limite de tamanho; aninhamento profundo | `RecursionError` do analisador | limite de 6000 caracteres; `RecursionError` vira `PolicyError` |
| 5 | Filtro `1e999999999`/`NaN`/`Infinity` vindo do LLM | `decimal.Overflow` (reproduzido) e formatação gigante | valor finito e < 1e15 (`BAD_FILTER`); L4 não formata fora da faixa |
| 6 | JSON do LLM aninhado fundo | `RecursionError` fora do tratamento de saída inválida | vira `InvalidOutput` (reparo/abstenção normais) |
| 7 | Erro do motor mostrado ao usuário (endpoint, corpo HTTP, JDBC) | vazamento de topologia/credenciais de infraestrutura | usuário vê mensagem genérica; detalhe só na trilha, com URLs ocultadas |
| 8 | Chave no objeto do cliente | vazaria por `repr`, depuração ou serialização | `__repr__` sem chave; `__getstate__` recusa serializar |
| 9 | Rótulos do grafo entravam crus no prompt | envenenamento de prompt por dado | `textsafe.ctx`: uma linha, sem `<`/`>` |
| 10 | Saída do LLM e fala do usuário sem higiene | ANSI/bidi no terminal; texto invisível | `clean` na resposta, na fala do usuário e no pedido de esclarecimento |
| 11 | 1000 linhas iam ao LLM da etapa 3 | custo e superfície de injeção sem ganho | no máximo 25 linhas; `TRUNCATED_FOR_ANSWER`; o texto **tem** de dizer que é parcial (regra L5) |
| 12 | `COUNT` em `?value` recebia unidade (°C); coluna com outro nome ficava sem unidade | contagem rotulada com unidade física | contagem sem unidade; única coluna numérica não-contagem herda a unidade |
| 13 | Números sem arredondar na resposta (23,9333…) | legibilidade | arredonda **só para exibir** a 4 casas; a checagem usa os valores originais |
| 14 | Sem identificação de qual ontologia respondeu | auditoria | `ontology` (hash de `met.ttl` + `met-structure.ttl`) e `prompts` no evento `end` da trilha |
| 15 | `.gitignore` sem `*.env`; raiz do git na Área de Trabalho | `git add` na raiz poderia versionar `kgqa.env` | `*.env` no projeto e `Parente/.gitignore` cobrindo `METEOROLOGIA/` e `*.env`; teste que falha se sumirem |
| 16 | Nenhum relatório era conferido por credencial | chave em log/relatório | teste varre `eval/reports` e `docs`: sem `Bearer …` nem token contínuo ≥ 100 caracteres |
| 17 | `pandas` sem versão | build não reproduzível | fixado em `pandas==3.0.6` |

**Melhoria de produto junto com a varredura:** quando o LLM pede esclarecimento e há canal com o usuário, o pedido vira uma
pergunta ao usuário (motivo + alternativas), em vez de encerrar; a resposta entra como correção e a interpretação passa por
todas as regras. Cancelar mantém o desfecho anterior.

**Não corrigido / fora do alcance desta varredura**
- `Ledger`: a checagem do teto é antes da chamada e não há trava entre processos; duas execuções simultâneas podem passar do
  teto por, no máximo, uma chamada cada.
- Quem usar `LocalRdflibBackend` de um script precisa da guarda `if __name__ == "__main__"` (o executor usa *spawn*): a falta
  dela causou o incidente das autorizações duplicadas (§7.1). Só documentado.
- `API Key.txt` na Área de Trabalho (fora do projeto) está sem proteção de `.gitignore` no nível da raiz do git; **não toquei
  nele**. Recomendo mover para fora da árvore versionada ou adicionar à raiz.
- Sem `pip-audit` neste ambiente: dependências não foram varridas por vulnerabilidades conhecidas.
- Nada disso foi exercitado contra Ontop/PostgreSQL reais.
