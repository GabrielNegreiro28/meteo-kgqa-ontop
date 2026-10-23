# Estudo: segurança das etapas com LLM em uma pipeline de perguntas sobre grafo de conhecimento

Autor: Gabriel Negreiro · Estado: rascunho v0.6 (inclui a revisão crítica: ver `REVISAO_CRITICA.md`; protótipo, injeção de falhas, LLM real, ontologia como guia, held-out e fresh, sobre o grafo sintético)

## 1. Problema

A pipeline estudada recebe um texto em linguagem natural com perguntas de um cliente e:

1. **compreende** as perguntas, apoiada em uma ontologia;
2. **escreve uma consulta SPARQL** para um grafo de conhecimento;
3. **executa** a consulta e obtém o resultado;
4. **interpreta o resultado** à luz da pergunta original e **responde em linguagem natural**.

As etapas 1, 2 e 4 dependem de agentes (LLM), que podem alucinar, produzir saída malformada ou cortada,
sofrer rate limit, estourar tempo ou orçamento, e ser manipulados por texto malicioso. A pergunta do estudo é:
**como garantir que essas etapas sejam o mais seguras possível?**

## 2. Princípio de projeto: o LLM propõe, regras validam

> O LLM não faz suposições que o sistema aceite sem conferir. Tudo que ele produz é uma *proposta*;
> regras determinísticas, escritas fora do LLM, decidem se a proposta pode seguir. Na dúvida, o sistema se abstém.

```
pergunta ──> [1 interpretar] ──> regras ──> [2 gerar SPARQL] ──> regras ──> executor somente leitura
              (LLM, JSON)        L2,L3       (LLM, JSON)        L1,L2,L3          │
                                                                                   v
resposta  <── [4 responder] <── regras (L5) <── verificação pós-execução (n, vazio, truncado)
              (LLM, JSON)        │ falhou? └─> resposta determinística copiada dos resultados
```

Cinco propriedades que sustentam o desenho:

| Propriedade | Como se realiza |
|---|---|
| **Saída restrita** | O LLM só devolve JSON com esquema fechado; chave fora do esquema = saída inválida. Cercas ```` ```json ```` são o único ajuste aceito. |
| **Verdade fora do LLM** | O que existe (propriedades, estações, unidades, classes) vem de um índice construído da ontologia e do grafo (`pipeline/vocab.py`). |
| **Falha fechada** | Etapas 1–2 que falham viram um status honesto (`rejected`, `unsupported`, `needs_clarification`, `execution_error`), nunca uma resposta. |
| **Degradação graciosa só onde é seguro** | Se a etapa 4 falha, os resultados já são reais: responde-se com texto determinístico. |
| **Reparo limitado** | Uma única nova tentativa, com a lista de regras violadas; depois, abstenção. Sem laço aberto. |

## 3. Modelo de ameaças por etapa

Estado: ✔ implementado e testado · ◐ parcial · ✘ não coberto. “Medido” remete à seção 6.

### Etapa 1 — compreender a pergunta

| Falha | Exemplo | Defesa | Estado |
|---|---|---|---|
| Propriedade ou entidade inventada | “radiação solar”, “Campo Grande” | índice da ontologia/grafo → `UNKNOWN_PROPERTY/ENTITY` → `unsupported` | ✔ |
| Agregação sem sentido | soma de temperatura | `met:aggregationNote` da ontologia → `SUM_OVER_INSTANTANEOUS` | ✔ |
| Período ou filtro malformado | fim anterior ao início, operador inexistente | validação estrutural da interpretação | ✔ |
| Ambiguidade resolvida “no chute” | “onde fez mais calor?” | o LLM pode devolver `needs_clarification` com alternativas; nada é executado | ◐ (confia no LLM para *notar* a ambiguidade) |
| Interpretação coerente porém errada | pergunta diz “média”, LLM interpreta “máxima” | nenhuma regra decide isso | ✘ (ver §7) |
| Excesso de recusa | declara `unsupported` algo que o grafo tem | nenhuma regra verifica | ✘ |

### Etapa 2 — gerar o SPARQL

| Falha | Defesa | Camada | Medido |
|---|---|---|---|
| Escrita, `SERVICE`, `FROM`, forma de consulta proibida | `check_policy` (já existente) | L1 | 18/18 (escrita 9, `SERVICE` 9) |
| Consulta truncada pelo limite de tokens | parse falha; além disso `finish_reason=length` descarta a saída antes | L1 + `ResilientLLM` | 9/9 |
| IRI de classe/propriedade inventado | todo IRI conferido contra a ontologia | L2 | 18/18 |
| Estação inexistente, rótulo inventado | IRIs de estação e rótulos `@pt` conferidos contra o grafo | L2 | 5/5 |
| Tipar por superclasse sem inferência (`?o a sosa:Observation`: vazio em silêncio) | classe sem instâncias diretas no regime sem inferência → `CLASS_WITHOUT_DIRECT_INSTANCES` | L2 | 7/7; e *replay* da consulta real do modelo (T03) |
| Tipos disjuntos na mesma variável (D-13) | fecho de `subClassOf` + `owl:disjointWith` | L2 | teste unitário (`test_disjoint_types_are_flagged`); sem mutante no experimento |
| Propriedade/estação válida, mas diferente da interpretação | conjuntos de propriedades e estações da consulta == os da interpretação | L3 | 13/13 |
| Operador de fronteira trocado, filtro omitido ou extra | comparações extraídas da álgebra == filtros da interpretação | L3 | 20/21 (1 mutante equivalente: filtro redundante) |
| Período deslocado ou omitido | limites `≥ início` e `< fim+1d` (ou `≤ fim` em datas) conferidos | L3 | 5/5 |
| Agregação errada | funções de agregação da consulta == a pedida (+ contagem) | L3 | 8/8 |
| Previsão vaza para “valor registrado” (D-08) | vocabulário de previsão proibido em pergunta de observação | L3 | 1/1 |
| Agregação sem `?n` (“zero” vira “sem dados”, e a amostra some; D-10) | toda consulta agregada precisa de um `COUNT` vinculado e projetado como `?n` | L3 | 8/8 |

### Etapa 3 — executar e verificar

Já existia no repositório e é reutilizado sem mudança: executor somente leitura com timeout e limite de
linhas (`kgqa/store.py`), usuário de banco somente leitura com `statement_timeout`, e a classificação
`answered` × `no_results` pelo `?n` (`kgqa/verify.py`). O pipeline acrescenta o diagnóstico `TRUNCATED`.

### Etapa 4 — responder em linguagem natural

| Falha | Defesa (`pipeline/grounding.py`) | Medido |
|---|---|---|
| Dígito do valor alterado | todo número do texto precisa existir nos resultados (aceita arredondamento e vírgula/ponto pt-BR) | 16/16 |
| Número inventado (“média histórica 27,3”) | idem | 17/17 |
| “Sem dados” apresentado como zero | com `no_results` nenhum número fora da pergunta é permitido | 1/1 (amostra pequena) |
| Resultado truncado apresentado como completo | texto precisa declarar “parcial/truncado” | 8/8 |
| Unidade omitida | a unidade vem da ontologia (`met:canonicalUnit`), não do LLM, e precisa aparecer | 14/14 |
| **Valores trocados entre entidades** | a checagem por conjunto de números **não detectava** (0/6); a associação entidade–valor (revisão) detecta | **6/6** (listas paralelas "A/B: x / y" continuam fora do alcance) |
| Injeção de prompt vinda da pergunta ou do dado | resultados vão em bloco `<resultados>` tratado como dado; a saída ainda passa pela checagem numérica e a consulta pela política | ◐ |

Quando a checagem reprova duas vezes, ou o LLM está indisponível, a resposta é gerada por
`render_fallback`: cada valor é copiado dos resultados, nada é calculado.

### Transversal — limites e falhas de infraestrutura (`pipeline/llm.py`)

| Falha | Tratamento | Teste |
|---|---|---|
| Rate limit | retry com backoff exponencial respeitando `retry_after`, máximo 3 tentativas | ✔ |
| Timeout | idem; esgotadas as tentativas, falha explícita | ✔ |
| Provedor fora do ar | circuit breaker: abre após 3 falhas, bloqueia sem chamar o provedor, meia-abertura após o cooldown | ✔ |
| Saída cortada (`finish_reason=length`) | nunca utilizada; vira `OUTPUT_TRUNCATED` | ✔ |
| Orçamento esgotado | verificado **antes** da chamada (`KGQA_BUDGET_USD` do `kgqa.env`) | ✔ |
| Saída que não é JSON / chave extra | `InvalidOutput`; uma tentativa de reparo com a mensagem do erro | ✔ |
| Falha na etapa 1 ou 2 | `execution_error`, sem resposta | ✔ |
| Falha na etapa 4 | resposta determinística + diagnóstico `ANSWER_FALLBACK` | ✔ |

## 4. O protótipo

Diretório `pipeline/`, sobre os módulos que já existiam (`kgqa/contract.py`, `store.py`, `verify.py`).

| Arquivo | Papel |
|---|---|
| `ontology/met-structure.ttl` | **camada estrutural da ontologia**: relações (domínio→imagem), forma do tempo por tipo de observação, tipo de observação por grandeza, agregações permitidas, semântica de período, símbolos de unidade. Não é carregada pelo Ontop |
| `pipeline/vocab.py` | índice derivado da ontologia e do grafo: vocabulário, tipos, formas de tempo, agregações; gera o contexto do LLM (`prompt_context("ontology")`) |
| `pipeline/query_facts.py` | extrai da álgebra SPARQL: IRIs, tipos, comparações, agregações, projeção |
| `pipeline/validators.py` | camadas L1 (política), L2 (vocabulário, **checagem de tipos dos caminhos**), L3 (conformidade com a interpretação, agregações e período segundo a ontologia) |
| `pipeline/grounding.py` | L5: checagem da resposta; resposta determinística de reserva |
| `pipeline/llm.py` | interface do LLM, `ResilientLLM` (retry, circuit breaker, orçamento), `ScriptedLLM`, JSON estrito |
| `pipeline/openai_client.py` | adaptador Chat Completions (urllib): mapeia 429/5xx/timeout/auth, estima custo, nunca expõe a chave |
| `pipeline/prompts.py` | instruções das etapas; `v1`/`v2` (contexto só com rótulos) e `v3` (contexto gerado da ontologia) |
| `pipeline/orchestrator.py` | fluxo completo, com um reparo por etapa e trilha de eventos |
| `eval/safety_experiment.py` | injeção de falhas e ablação; gera `docs/RESULTADOS_INJECAO_FALHAS.md` |
| `eval/run_llm_pipeline.py` | roda a pipeline com LLM sobre as 24 perguntas; mede respostas erradas entregues, abstenções, reparos e a ablação da 1ª tentativa; gera `docs/RESULTADOS_LLM_REAL.md` |
| `eval/questions_heldout.yaml`, `eval/oracle_heldout.py` | **10 perguntas novas** (held-out) com consultas de referência e oráculo próprios, criadas depois das regras e sem ajuste de prompt nelas |
| `eval/compare_runs.py` | compara condições de contexto (A × B) sobre várias execuções; gera `docs/COMPARACAO_CONTEXTO.md` |
| `tests/test_pipeline.py`, `test_openai_client.py`, `test_flexible_compare.py`, `test_ontology_guidance.py`, `test_heldout.py`, `test_revision.py`, `test_fresh.py` | 298 testes (1 pulado): caminho feliz, reparo, rejeição, abstenção, infraestrutura, limites conhecidos, controles de falso positivo, adaptador com HTTP simulado, régua de avaliação, ontologia como guia (inclui *replay* de falhas reais do LLM) |

A **conformidade com a interpretação (L3)** é o núcleo da ideia: a interpretação é registrada em estrutura
(propriedades, entidades, filtros, período, agregação, tipo de registro) e a consulta gerada é *derivada de
volta* da álgebra e comparada. A consulta pode ser escrita de mil formas; a álgebra é única.

Nenhum provedor de LLM está implementado. Os testes usam `ScriptedLLM` (respostas roteirizadas, inclusive
falhas) e o experimento de injeção nem chama LLM: ele aplica as falhas diretamente às consultas e aos textos.
Um adaptador de provedor entra atrás da mesma interface (`LLMClient.complete`). Nada foi enviado a serviços externos.

## 5. Método do experimento

Injeção de falhas, determinística e de custo zero, sobre o grafo sintético (rdflib):

- **Base**: 9 consultas de referência corretas do `eval/questions.yaml`, cada uma com sua interpretação. As referências `T03`, `T07`, `T12` e `T16` violavam o D-10 e ganharam `COUNT(?v) AS ?n` (conferidas contra o oráculo).
- **Falhas de consulta**: 16 operadores (IRI inventado, propriedade/estação válida porém errada, operador de
  fronteira, período deslocado, filtro omitido ou extra, agregação errada, `?n` omitido, vazamento de previsão,
  escrita, `SERVICE`, truncamento). Aplicáveis: **106 mutantes**.
- **Verdade de cada mutante**: o mutante é executado (quando a política permite) e comparado ao **oráculo
  independente** (`eval/oracle.py`, Python puro sobre o CSV): *errada em silêncio*, *vazia*, *equivalente*,
  *perigosa* ou *erro de sintaxe*.
- **Controle**: as 9 consultas corretas **não podem** gerar achados.
- **Falhas de texto**: 6 operadores sobre respostas corretas, medidos contra a checagem numérica.
- **Ablação**: sem validação → L1 → L1+L2 → L1+L2+L3.

## 6. Resultados

Detalhe completo em `docs/RESULTADOS_INJECAO_FALHAS.md` (gerado). Resumo:

| Configuração | escrita/rede chega ao armazenamento | errada em silêncio | vazia (honesta) |
|---|---:|---:|---:|
| sem validação | 18 | 33 | 28 |
| L1 política/sintaxe | 0 | 33 | 28 |
| L1 + L2 vocabulário | 0 | 33 | 8 |
| **L1 + L2 + L3 conformidade** | **0** | **0** | **0** |

Leitura:

- **L1** elimina o perigo (escrita, rede) mas não muda nada sobre respostas erradas. Já existia.
- **L2** transforma consultas com IRI inventado, que voltariam como “sem registros” (uma resposta enganosa), em
  erro tipado imediato e reparável.
- **L3** é o que captura as **33 respostas erradas em silêncio** (propriedade trocada, fronteira, período,
  agregação...). Sem ele, a consulta é válida, executa e devolve um número plausível.
- **Controle**: 9/9 consultas corretas passam sem achados. *Esse controle encontrou um defeito meu*: a primeira
  versão da regra D-10 barraria `T03` e `T07`, que estavam corretas segundo o oráculo mas não projetavam `?n`.
  A decisão foi **tornar `?n` obrigatório** e corrigir as referências, em vez de enfraquecer a regra. Uma versão
  intermediária (`?n` projetado, sem exigir o `COUNT`) deixou passar `T03` com `?n` nunca vinculado; hoje se exige o
  `COUNT` de fato.
- **Texto**: números alterados, inventados, unidade e truncamento omitidos são detectados em 100% dos casos
  aplicáveis (n=8 a 17 por tipo; “sem dados como zero” tem n=1).
- Também houve um **crash** na checagem numérica com números gigantes no texto, corrigido e coberto por teste.

### 6.1 Execução com LLM real (`gpt-6-luna`, grafo sintético, 24 perguntas)

Cada execução custou ~US$ 0,35–0,40 (estimativa) e levou 2–80 s por pergunta. **Uma execução por versão**: o
modelo não é determinístico e n=24, então diferenças de 1–2 perguntas **não são significativas**. Detalhe em
`docs/RESULTADOS_LLM_REAL_v1.md` e `_v2.md`.

**Protocolo.** `v1` é a linha de base, sem ajuste. Depois de ver a v1, criei a `v2` com dois acréscimos motivados por
falhas do split **dev** (D05, D07). Como eu já tinha visto os resultados do **test**, a v2 **não é medida limpa** nele:
trate `dev` como conjunto de ajuste e `test` como indicativo.

| | v1 (base) | v2 (ajustada em dev) |
|---|---:|---:|
| status final igual ao esperado | 13/24 | 13/24 |
| respondíveis com resultado correto | 10/12 | 10/11 |
| **respostas erradas entregues** (com dados) | **0** | **0** |
| **falsa ausência de registros** (“não há registros”, havendo dados) | **2** (D05, T06) | **1** (T03) |
| abstenções indevidas (pergunta respondível não respondida) | 7 | 8 |
| respostas a perguntas que deveriam ser recusadas | 0 | 0 |
| reparos usados / respostas de reserva | 0 / 5 | 6 / 0 |
| dev: status igual / correto | 6/8 · 5/6 | 7/8 · 6/6 |

**O que a execução real ensinou** (e os mutantes não mostravam):

1. **Nenhuma resposta com dados incorretos foi entregue em 48 execuções** (24 × 2; medido no resultado da consulta, e o texto passou pela checagem numérica). Mas o modo de falha dominante foi
   outro: **dizer “não há registros” onde há dados** (D05, T06 na v1; T03 na v2). É uma resposta errada e
   enganosa, e **passou por todas as regras** na v1. Origem: consulta válida que não casa com o grafo
   (precipitação consultada como instante, quando é um intervalo; tipar por `sosa:Observation` sem inferência).
   A ablação da primeira tentativa mostra isso: das consultas que não devolveram o oráculo, as “vazias” passaram
   por todas as camadas (2 na v1, 1 na v2). A regra `CLASS_WITHOUT_DIRECT_INSTANCES` foi criada a partir da falha de T03 e pega essa
   consulta em *replay*; a de D05/T06 foi tratada por contexto de prompt (v2), **sem regra determinística ainda**.
2. **O L3 barrou uma resposta errada real**: em T06 (v2) o modelo fechou o período em `23:59:59` e perderia o
   último intervalo de 6 h; a regra rejeitou (`PERIOD_MISMATCH`) e o reparo não resolveu → `rejected`, em vez de um
   total incompleto apresentado como certo. Foi o único caso de “errada em silêncio” na primeira tentativa (v2; na v1 não houve).
3. **Excesso de cautela é o custo de segurança**: 7–8 perguntas respondíveis viraram `needs_clarification`, quase
   sempre por *“período não informado”* (T05, T07, T08, T11, T12, T16). Para o modelo, “qual a média na Estação X?”
   é ambíguo sem período; a referência assume “todo o período”. **Isso é uma decisão de política, não um erro do
   modelo**: assumir “todo o período disponível” e declará-lo na resposta, ou perguntar. Em T10 o modelo
   inventou ambiguidade absurda (“09/03/2026 pode ser 3 de setembro”).
4. **Recusas mal classificadas, porém seguras**: nas perguntas fora da ontologia (D07 vento, T14 pressão) o modelo
   pediu esclarecimento em vez de declarar `unsupported`, e a instrução da v2 não corrigiu. Nenhuma foi respondida.
5. **A etapa 4 devolveu texto em vez de JSON em 5 de 24 casos** (v1): sem reparo, caía na resposta de reserva
   (correta, porém seca). Com **um reparo na etapa 4** (v2) as respostas de reserva foram a zero. Sem a camada de
   reserva, esses 5 casos teriam sido erro de infraestrutura.
6. **O modelo recusa parâmetros** (`response_format`): o adaptador removeu e registrou. A saída estrita em JSON
   continua sendo garantida por nós, não pelo provedor.

**Defeitos da minha própria régua, achados no caminho** (relevantes porque “avaliar o avaliador” faz parte do estudo):
o comparador casava colunas por *nome* da variável e marcou como “ERRADAS” 4 respostas corretas (o modelo escreveu
`?observation`, não `?obs`); a correção passou a casar por valor. Uma versão intermediária aceitava **a agregação errada**
(omitia a própria coluna do valor) — pego por teste; hoje só se omite coluna declarada `optional` na referência. Também
tratava “vazio = vazio” como divergente quando as colunas projetadas diferiam. A primeira rodada ficou arquivada em
`eval/reports/*_pass1_namebased*` como registro.

### 6.2 A ontologia como guia: o que mudou e o que isso rendeu

**Diagnóstico que motivou a mudança.** Nas execuções acima a ontologia só dizia *quais termos existem*. O conhecimento de
*como as coisas se ligam* (que grandeza é acumulada, que forma de tempo ela usa, que unidade é um recurso e não um
texto, que previsão não é observação) estava em parágrafos escritos à mão no prompt ou em regras avulsas no código.
Das falhas reais do modelo, as mais perigosas (“não há registros” onde há dados) vinham dessa lacuna.

**O que foi feito.** Os relacionamentos passaram a ser axiomas em `ontology/met-structure.ttl` (arquivo separado, porque usa
`owl:allValuesFrom` e classes como valores, fora do OWL 2 QL do Ontop, que continua lendo só `met.ttl`):

| Axioma na ontologia | Deriva-se dele (sem texto escrito à mão) |
|---|---|
| domínio/imagem de `sosa:hosts`, `madeBySensor`, `observedProperty`, `phenomenonTime`, `hasBeginning`..., `met:forStation`... | a lista de **relações** entregue ao LLM e a **checagem de tipos dos caminhos** (`TYPE_CLASH`) |
| `InstantaneousObservation ⊑ ∀phenomenonTime.Instant`; `AccumulatedObservation ⊑ ∀phenomenonTime.Interval`; `Instant ⟂ Interval` | o **caminho de tempo** de cada grandeza no contexto e o erro de “instante × intervalo” |
| `met:Precipitation met:observedAs met:AccumulatedObservation` (13 grandezas) | classe de observação e forma do tempo de cada grandeza |
| `met:allowsAggregation` (soma só para acumulados; direção e nuvens só `count`) | `AGGREGATION_NOT_ALLOWED` (substitui a leitura frágil do texto de `aggregationNote`) e as agregações no contexto |
| `met:requiresFullContainment true` em `AccumulatedObservation` (decisão D-06) | `PERIOD_MISMATCH` específico: o fim do intervalo exige `<=` e não `<` |
| `qudt:unit rdfs:range qudt:Unit` | `RESOURCE_COMPARED_TO_STRING` (`FILTER(?u = "unit:DEG_C")` é sempre falso) |
| `met:symbol` por unidade | resposta com `°C`, `mm`, `kt` em vez de `DEG_C`, `MilliM` |
| `owl:disjointWith` | lista de classes disjuntas no contexto e `DISJOINT_TYPES`/`TYPE_CLASH` |

**Controles.** Nenhuma regra nova barra consulta correta: 0 falsos positivos nas 34 consultas de referência (19
sintéticas + 15 reais). O mutante `intervalo consultado como instante` (2/2), `fim do intervalo estrito` (2/2), `unidade
comparada com texto` (1/1) e `superclasse sem inferência` (7/7) são barrados; o experimento de injeção agora tem **118
mutantes** e nenhuma falha silenciosa sem barrar.

**Replay das falhas reais.** As três falsas ausências de registros da seção 6.1 (D05 e T06 na v1, T03 na v2) e as três
da execução intermediária com contexto da ontologia (D05, T06 entregues **como respondidas e erradas**, T02 como
“sem registros”) são hoje pegas pelas regras (`TYPE_CLASH`, `PERIOD_MISMATCH`, `RESOURCE_COMPARED_TO_STRING`,
`CLASS_WITHOUT_DIRECT_INSTANCES`), todas com testes de *replay*.

**Comparação A (contexto só com rótulos) × B (contexto gerado da ontologia).** Mesmo código de regras nas duas, duas execuções
por condição, 24 perguntas, `gpt-6-luna` (`docs/COMPARACAO_CONTEXTO.md`):

| | A #1 | A #2 | B #1 | B #2 |
|---|---:|---:|---:|---:|
| **respostas erradas entregues** | 0 | 0 | 0 | 0 |
| **falsa ausência de registros** | 0 | 0 | 0 | 0 |
| status igual ao esperado | 13 | 13 | 14 | 14 |
| respondíveis corretas | 10/10 | 10/10 | 11/11 | 11/11 |
| 1ª consulta correta (de 12 que chegaram à geração) | 9 | 10 | 11 | 11 |
| 1ª consulta errada, barrada pelas regras | 3/3 | 2/2 | 1/1 | 1/1 |
| reparos | 9 | 6 | 6 | 7 |
| abstenções indevidas | 9 | 9 | 8 | 8 |
| custo estimado (US$) | 0,43 | 0,41 | 0,61 | 0,60 |

Leitura, com a ressalva de n pequeno:

1. **As regras derivadas da ontologia é que impedem a entrega errada.** Em A, o modelo errou 5 primeiras consultas em 2
   execuções (`TYPE_CLASH`×4, `PERIOD_MISMATCH`×4, ...) e **todas foram barradas**: nenhuma resposta errada chegou ao
   usuário. Na execução intermediária, *antes* dessas regras, D05 e T06 chegaram a ser entregues respondidas e erradas.
2. **O contexto gerado da ontologia reduz o desperdício, não a segurança.** Em B a primeira consulta saiu certa em 11/11
   das tentadas (A: 9–10), com menos erros a reparar, e D05 (precipitação) passou a ser respondida corretamente nas duas
   execuções (em A foi `rejected` nas duas: o reparo não bastou). Mas a condição B custa **~40% mais** (contexto maior).
3. **Efeito colateral negativo em B**: D01 virou pedido de esclarecimento nas duas execuções (“temperatura” é ambígua entre
   5 grandezas). Defensável, mas é regressão sistemática no gabarito.
4. **O que a ontologia não descreve, o modelo não consegue consultar.** T10 (previsão) foi rejeitada (ou virou pedido de esclarecimento) em A e B: o
   contexto não trazia as relações de `met:Forecast` nem a disjunção com observação. A correção que tentei (listar *todas* as
   relações) **causou uma regressão**, descrita e corrigida na seção 6.3.
5. As **abstenções indevidas** (“período não informado”, “temperatura ambígua”, recusas mal rotuladas) não mudaram de
   natureza: são política e modelo, não estrutura do grafo.

**Honestidade sobre o procedimento (ver também 6.3).** As regras `AGGREGATION_NOT_ALLOWED`, `PERIOD_MISMATCH` por contenção,
`RESOURCE_COMPARED_TO_STRING` e a forma do tempo foram criadas **depois de ver as falhas do modelo nas mesmas 24
perguntas**. Elas são genéricas (erros de tipo e de semântica de período, validados contra 34 consultas corretas), mas
os números de A e B **não são uma medida cega**: um conjunto novo de perguntas e outros modelos são necessários.

### 6.3 Segunda rodada: o contexto "completo" foi uma regressão, o conjunto novo e o que ainda falha

Esta seção corrige e complementa a 6.2. **Teve um erro meu que piorou o sistema e que as regras da época não pegaram.**

**1. Regressão causada por mim.** Para cobrir previsão (T10), passei a listar no contexto *todas* as relações que a
ontologia declara. O modelo então usou `met:inReport`/`met:reportOf` (declaradas na ontologia, mas **sem nenhuma
asserção neste grafo**) para chegar à estação. Consulta válida, vocabulário válido, vazia por construção.

| Condição (24 perguntas, 2 execuções) | B (contexto da ontologia) | B2 (+ todas as relações) |
|---|---:|---:|
| 1ª consulta correta | 11 e 11 | **2 e 2** |
| falsa ausência de registros | 0 e 0 | **7 e 9** |
| resposta errada entregue | 0 e 0 | 0 e **1** |

**Lição de fundo:** a ontologia diz o que *pode* existir; quem diz o que *está populado* é o dado (no Ontop, o
mapeamento). Um contexto gerado só da ontologia induz consultas para relações vazias. A correção foi gerar o
contexto da **interseção ontologia ∩ perfil dos dados** (`data_predicates`, `properties_with_data`) e acrescentar
`RELATION_WITHOUT_DATA`. Com o grafo real, o perfil deve vir do mapeamento `.obda`; isso **ainda não está implementado**
(hoje o perfil vem de `data/synthetic.nt`).

**2. Conjunto held-out (10 perguntas novas, gabarito validado por 21 testes antes de medir).**

| Execução | respondíveis corretas | erradas entregues | falsa ausência | abstenção indevida |
|---|---:|---:|---:|---:|
| B2, antes da correção do perfil (`v3_h1`) | 1/8 | 0 | **5** | 2 |
| B com perfil dos dados (`v3_h2`) | 5/8 | 0 | **2** | 1 |

As 2 falsas ausências restantes (H03, H08) e as de D02, D04 e T07 nas 24 perguntas têm **a mesma causa nova**: o modelo
usou a *estação* como objeto de `sosa:hasFeatureOfInterest`, mas no grafo esse objeto é o *local* (`met:Site`). A
ontologia agora declara `sosa:Platform ⟂ sosa:FeatureOfInterest` e a checagem de tipos passou a considerar estações
citadas como constante ou por `VALUES`. **Essa regra foi derivada de D02/D04/T07 e pega H03 e H08, que não foram usadas
para criá-la**, o que é a evidência de generalização mais forte do estudo (pequena: 2 casos).

**3. Falha de tipo de função.** `BIND(xsd:date(?t) AS ?dia)` (T16, e T07 na primeira rodada, que eu havia classificado como
"peculiaridade do rdflib" por engano): `xsd:date()` não existe no SPARQL 1.1, o rdflib deixa o dia sem valor e 7 grupos
viram 1, **uma resposta errada entregue como respondida**. Regra `UNSUPPORTED_FUNCTION`.

**4. Falha de infraestrutura real.** Uma execução caiu com `ConnectionResetError` no meio da leitura, que o adaptador não
tratava (só `TimeoutError`/`URLError`). Agora é `LLMTimeout` retentável. O mesmo vale para `http.client.IncompleteRead`.

**Reaplicação das regras finais às primeiras consultas ruins já gravadas (sem LLM):** das 51 válidas (excluindo a
rodada `pass1`, rotulada pelo comparador defeituoso), **41 são pegas sem precisar da interpretação**; as 10 restantes
dependem da interpretação (previsão, contenção de período) e, com ela, já eram pegas na pipeline. *É reaplicação, não
medida ao vivo*: depois das regras do item 2 e 3 **não houve nova execução com o LLM**.

**O que NÃO foi medido (limites desta seção):**
- A condição A (só rótulos) **não foi medida no held-out**: a execução caiu pela falha de rede do item 4.
- Nenhuma execução ao vivo com `RELATION_WITHOUT_DATA`+`TYPE_CLASH` de estação+`UNSUPPORTED_FUNCTION` ativas juntas.
- Nas 24 perguntas a última execução comparável (A=`v1_s3`, B=`v3_s6`) deu, antes dessas últimas regras: A com 0 erradas e 0
  falsas ausências, **B com 0 erradas e 3 falsas ausências** (a família da estação). Ou seja, **na última medida ao vivo o
  contexto da ontologia (B) foi pior que só rótulos (A) em segurança**, e só ficou à frente em primeira consulta (10 × 9)
  e menos abstenções (7 × 10); custo 0,71 × 0,40 US$.
- **Gasto**: ~US$ 7,4 estimados no total, acima do teto de US$ 5 do `kgqa.env` (estimativa conservadora). Parei de rodar.

**Leitura honesta.** O contexto gerado da ontologia melhora a chance de acertar a primeira vez, mas **também abre
famílias novas de erro** (relações vazias, estação × local) que só as regras de validação seguram. O que sustenta a
segurança é a combinação *regras derivadas da ontologia e do perfil dos dados* + abstenção, não a qualidade do prompt.
Cada família nova foi descoberta rodando o LLM, o que indica que o conjunto de regras **ainda não está completo**: espere
mais famílias em outros grafos e perguntas.

### 6.4 Revisão crítica e campanha final (v4)

Detalhes, lista de pontos fracos, correções e critérios fixados antes de medir: **`docs/REVISAO_CRITICA.md`**. Resumo:

- **15 pontos fracos** achados por leitura do código (interpretação não conferida contra a pergunta; JSON válido derrubando a
  pipeline; estação por rótulo não conferida; troca de valores; data relativa; teto de gasto só por execução; injeção de
  prompt; perfil do Ontop; controle de falso positivo pequeno…). Todos com teste; 298 testes passam.
- **Injeção de falhas na interpretação**: 85% barradas por L4; no texto, troca de valores 6/6, linha omitida 6/6.
- **Campanha ao vivo (44 perguntas, um modelo, uma execução por condição)**: A (v1) × C (v4). C: 41/44 no status esperado,
  29/30 respondíveis corretas, 3 abstenções indevidas; A: 23/44, 16/17, 17 abstenções. Erros entregues: **C 1 (H02), A 1 (G03)**.
- **A primeira versão da v4 falhou nos critérios que eu mesmo fixei** (9 abstenções por "informe o período"; um comparador que
  eu julguei errado). Corrigi o prompt (sem período = todo o histórico, dito ao usuário), criei o campo `instant`, o
  contexto com os caminhos derivados e a decisão determinística de grandeza sem dados, e **corrigi um erro de diagnóstico
  meu** (T10 era resposta incompleta, não errada).
- **Mais uma família silenciosa, criada pela própria melhoria**: dar ao modelo os dois caminhos válidos da estação até a
  observação levou a um `UNION` que dobrou a soma (42,6 mm no lugar de 21,3 mm). Regra `UNION_WITH_AGGREGATE`; 6/6 reexecutadas certas.
- **Lição geral**: mais contexto derivado da ontologia melhora o acerto, mas cada pedaço de contexto também abre um modo de
  erro novo que só uma regra de validação segura. A segurança vem da combinação *contexto + regras + abstenção + medição*, e a
  medição precisa de suítes que não foram usadas para ajustar as regras (aqui, só a *fresh*).

### Risco residual medido

1. **(Superado na revisão; ver §6.4)** Valores trocados entre entidades no texto (era 0/6): ambos os números existem nos resultados. É o único risco
   residual medido; nenhum mutante de consulta escapou das regras neste conjunto.
2. **1 mutante equivalente passou** (filtro redundante removido): inofensivo.
3. **18 mutantes barrados com resultado coincidente**: a consulta de fato diverge da interpretação; barrar é
   correto, o resultado só seria igual por acaso dos dados.
4. **Suíte real**: `RD03`, `RD04` e `RT02` (`eval/questions_real.yaml`) também violam o D-10 e **não foram
   alteradas**, pois só podem ser validadas contra o Ontop. Com `?n` obrigatório, um LLM que copie esse estilo
   seria rejeitado até que sejam corrigidas.

## 7. Limites: o que as regras NÃO garantem

Estes pontos são resultado do estudo, não defeitos a esconder:

- **Interpretação errada porém coerente: reduzida, não eliminada.** L3 mede a consulta contra a interpretação. A revisão
  acrescentou L4 (interpretação conferida contra a **pergunta**: estações citadas, valores, datas, palavras de agregação,
  grandeza nomeada): **47/55 = 85%** das interpretações corrompidas de modo coerente são barradas (era 0%). Os 8 restantes são
  o que se decide por texto sem entender a intenção ("Quanto choveu…" não traz palavra de agregação nem rótulo da grandeza).
  Continua válido o teste que documenta o limite para as versões v1–v3, que não têm L4.
- **Concordância não é correção.** Mesmo princípio da sua proposta de arquitetura: várias candidatas que
  concordam não provam acerto.
- **Falsos negativos de “ambiguidade” e de “fora do escopo”** dependem do LLM notar; não há regra que prove que
  uma pergunta *era* ambígua ou suportada (excesso de recusa não é medido).
- **Fidelidade semântica fina do texto** (ênfase, comparação, “maior” versus “menor” em frase) não é verificada;
  só números, unidade e truncamento.
- **Resultados sintéticos e amostra pequena**: grafo de 2,6 mil triplas; o experimento com LLM tem 24 perguntas, **uma
  execução por versão e um único modelo**, sem intervalo de confiança. As falhas injetadas são *fabricadas* e as do
  LLM real são poucas: nenhum dos dois estima a taxa de erro de produção.
- **Falsa ausência de registros** (consulta válida que não casa com o grafo) era o modo de falha real mais perigoso. Hoje é
  coberta por regras **derivadas da ontologia** (tipos de caminho, forma do tempo, unidade como recurso, superclasse sem
  inferência), mas só enquanto a ontologia descreve o padrão de dados em questão: padrões que ela não descreve
  (ex.: nuvens por camada, relatórios) não têm checagem. O caso geral ainda exige sondagem de cobertura (§8).
- **O conjunto de regras não está completo**: cada rodada com o LLM revelou uma família nova de consulta válida e vazia
  (superclasse sem inferência, intervalo como instante, unidade como texto, relação sem dados, estação como local,
  função fora do SPARQL). Não há razão para crer que acabaram. O experimento de injeção de falhas (128 mutantes) só
  cobre o que já foi descoberto. A campanha final achou mais uma (UNION de caminhos alternativos duplicando linhas, §6.4).
- **O perfil dos dados vem do grafo sintético** na pipeline; para o real há `with_profile_from_obda`, e as consultas de referência
  reais passam pelas regras de vocabulário com ele (0 falsos positivos), mas **nada foi rodado com Ontop/PostgreSQL**.
- **A camada estrutural é provisória e mantida à mão**: não está alinhada com a BFO e pode divergir de `met.ttl` e do mapeamento
  Ontop; falta um teste que compare as duas ontologias com o mapeamento real.
- **O oráculo compartilha limites com os dados**: não detecta erro do gerador sintético.

## 8. Recomendações e próximos passos

Em ordem de retorno esperado, já incorporando o que a execução real e a ontologia-guia mostraram (§6.1, §6.2):

0. **Repetir ao vivo, com todas as regras ativas**, A × B no held-out e nas 24 perguntas (a última medida ao vivo foi
   anterior às regras de estação × local e de função), com mais execuções e outros modelos. Requer **nova autorização de
   gasto**: o acumulado estimado (US$ 7,4) já passou do teto de US$ 5 do `kgqa.env`.
0b. **Derivar o perfil dos dados do mapeamento Ontop** (`.obda`/R2RML) para o grafo real, em vez do grafo sintético.

1. **Detectar “falsa ausência de registros”** (modo de falha real dominante). Quando o resultado é vazio, sondar a
   cobertura com uma consulta de contagem fixa (propriedade + estação, sem filtros de tempo/valor): se há dados fora
   dos filtros, **não afirmar “não há registros” de forma categórica** e acionar reparo ou avisar “nenhum registro
   nos critérios; a fonte tem registros desta grandeza fora deles”. É o análogo da “verificação pós-execução” da
   arquitetura do professor (“resultado vazio onde o catálogo declara completude”). A regra de superclasse já cobre um caso.
2. **Decidir a política de período ausente**: perguntar (hoje, seguro e mais lento: 6 das 7 abstenções indevidas) ou
   assumir “todo o período disponível” **e declarar isso na resposta**. Exige decisão de produto, não de modelo.
3. **Eco da interpretação ao usuário** (ou ao agente seguinte) antes de executar consultas caras, e *confirmação*
   para períodos, agregações e entidades inferidas. Defesa para o risco residual principal (§7).
4. **Resposta em slots**: o LLM preenche campos por linha de resultado e o sistema monta a frase. Elimina a troca de
   valores entre entidades (a checagem por conjunto não pegava; a associação entidade–valor da revisão pega, §6.4).
5. **Pré-checagem determinística de “fora da ontologia”**: casar termos da pergunta com rótulos/sinônimos da
   ontologia *antes* de aceitar um pedido de esclarecimento. O modelo trocou `unsupported` por esclarecimento em D07 e T14.
6. **Repetir o experimento com variância**: k ≥ 3 execuções por pergunta, temperaturas diferentes e mais de um
   modelo; só assim diferenças de 1–2 perguntas deixam de ser ruído. Ampliar de 24 para um conjunto maior, com `test`
   realmente intocado por ajuste de prompt.
7. **Avaliação de recusa** (resolvida em parte): hoje mede-se abstenção indevida e resposta indevida; falta medir a
   *qualidade* da recusa (motivo correto, alternativas úteis).
8. **Teste de injeção de prompt vinda do dado**: rótulos e literais do grafo com instruções, para medir se a
   etapa 4 as segue. A defesa atual (bloco de dados + checagem numérica) é plausível, não demonstrada.
9. **Trilha de auditoria**: a consulta executada, a interpretação, as regras acionadas e o custo já ficam na
   `trace`; persistir e anexar à resposta, como a arquitetura do professor pede (procedência).
10. **Backend real**: repetir sobre o Ontop/PostgreSQL (`questions_real.yaml`, 105 mi de observações), onde há
    inferência OWL 2 QL (a regra de superclasse muda com `OntologyIndex.load(inference=True)`), custo de consulta,
    `LIMIT` e latência. Ajustar `RD03`, `RD04` e `RT02`, que violam o D-10.

## 9. Relação com a arquitetura do professor

A proposta *Ontology-Grounded Agentic Architecture* tem o mesmo espírito: portões determinísticos ao redor de
passos probabilísticos, verificador antes e depois da execução, abstenção no lugar de aproximação e
procedência em cada fato. Este estudo detalha, para o trecho *interpretar → consultar → responder*, **quais
portões** existem, **o que cada um captura** e **o que ainda passa**. O verificador pré-execução da arquitetura
(“toda restrição da pergunta aparece na consulta canônica; IRIs, domínios e ranges conferem com a ontologia”)
é, aqui, a camada L3 + L2.

## 10. Reproduzir

```bash
pip install -r requirements.txt            # rdflib, pyshacl, duckdb, pandas, pytest...
python -m pytest tests --ignore=tests/test_real_pipeline.py -q   # 298 testes (1 pulado), sem rede, custo zero
python -m eval.safety_experiment                 # regenera docs/RESULTADOS_INJECAO_FALHAS.md
python -m eval.run_llm_pipeline --dry-run        # valida o arcabouço sem LLM
python -m eval.run_llm_pipeline --env ../METEOROLOGIA/kgqa.env --budget 1.5 --prompts v1|v2|v3 --tag _s1   # LLM real (gasta ~US$ 0,35-0,6 por execução)
python -m eval.compare_runs A=eval/reports/llm_run_v1_s1.json,eval/reports/llm_run_v1_s2.json B=eval/reports/llm_run_v3_s1.json,eval/reports/llm_run_v3_s2.json
python -m eval.run_llm_pipeline --reevaluate eval/reports/llm_run_v1.json --prompts v1      # recalcula métricas sem LLM
```

Os testes da suíte real (`tests/test_real_pipeline.py`) dependem do ambiente Linux com Ontop e PostgreSQL e
são pulados fora dele.
