# Proposta de arquitetura: MVP de perguntas em linguagem natural sobre dados meteorológicos (ontologia + Ontop + EvoOntology)

## Contexto

**O problema.** Uma pessoa pergunta em português ("Quanto choveu em SBGL no dia 15 de fevereiro de 2024?"). O sistema precisa:
1. entender o que ela pediu;
2. consultar os dados reais de 178 aeródromos (2016–2025, 105 milhões de observações, PostgreSQL visto como grafo pelo Ontop);
3. responder com um número certo, dizendo de onde ele veio;
4. ou dizer honestamente que não sabe ou que precisa de um esclarecimento.

**Por que uma proposta nova, e não mais uma melhoria.** O repositório tem muito trabalho bom, mas cresceu por acréscimo:
- **Oito versões de prompt** (v1–v8) convivem como flags dentro de uma função de cerca de 350 linhas (`pipeline/orchestrator.py::_run_pipeline`).
- **Duas formas paralelas de conferir o LLM:** dezenas de regex em `validators.py`, com 880 linhas e 22 padrões, e a conciliação por trechos do v8.
- **Conhecimento duplicado:**
  - a lista das 13 grandezas aparece em cerca de 9 lugares (ingestão, exportação, constraints, mapeamento, conformância, ontologias);
  - unidades em 3 a 4 tabelas que não conversam;
  - meses e números por extenso em 2 ou 3 módulos;
  - `COUNT_VARS` 5 vezes;
  - faixas físicas divergentes entre `ingest/transform.py` e `ontology/shapes.ttl`.
- **A camada EvoOntology** só entra na resposta pelo prompt v5, que não é mais usado. A evolução é real, mas desligada do caminho da pergunta.
- **Medições:**
  - nenhuma diferença entre versões é estatisticamente significativa (n de 8 a 50, uma execução por condição);
  - os erros reais medidos (dia virando mês, mm × contagem, filtro perdido) são de **estrutura**, não de modelo;
  - o v8 corrige esses erros por construção, mas só foi conferido com interpretações escritas à mão.

**Saída esperada.** Uma arquitetura de MVP pequena, linear e testável. Ela:
- implementa o essencial do documento do professor Parente (*Ontology-Grounded Agentic Architecture*) para o caso real, que é **uma fonte** (PostgreSQL via Ontop), **sem** MongoDB e **sem** documentos PDF/Word;
- reaproveita o que já foi provado;
- deixa de fora o que é dívida acidental.

Proposta aprovada e implementada como o pacote `metqa/` (estado na seção 9).

---

## 1. O que o documento pede e o que entra no MVP

| Componente do documento (§5) | No MVP | Por quê |
|---|---|---|
| Intérprete → **consulta canônica** (§8) | **Sim**: IR tipada e ancorada em trechos, compilada para SPARQL | Responde à questão aberta do §16 ("SPARQL de ponta a ponta ou IR leve compilada?"): a IR. Medido: o LLM escrevendo SPARQL foi a principal fonte de erro silencioso |
| EvoOntology como camada consultiva via MCP (§7) | **Sim, no caminho de toda pergunta**, como **léxico** atrás de uma fachada | Hoje só o v5 a usava. No MVP ela resolve as palavras da pergunta para IRIs, e o que ela não cobre vira sinal de evolução |
| BFO + ontologia de domínio + SHACL + visões DL/QL (§6) | **Sim** (já existe) | Categoria BFO e disjunções entram na verificação da IR; a visão QL serve o Ontop |
| Roteador + catálogo de capacidades (§9) | **Reduzido a um catálogo de capacidades gerado** (grandezas com dados, cobertura temporal, agregações permitidas) | Com uma fonte não há o que rotear; continua havendo "abstenção honesta" quando a grandeza ou o período não existem |
| Planejador (§12) | **Mínimo**: um plano = 1 ou 2 subconsultas (comparação de dois períodos ou duas estações) | É o caso real que hoje vira `unsupported` (E30, E32) |
| Verificador antes e depois (§12) | **Sim** | Antes: IR × ontologia × catálogo. Depois: resultado × cobertura, unidade, n e conteúdo do texto |
| Sintetizador com proveniência (§12) | **Sim, determinístico por padrão** (LLM só para redigir, opcional e conferido) | Texto montado de linhas verificadas não alucina e custa zero |
| Registro de trajetória (§12) | **Sim** | Alimenta a evolução |
| Ciclo de evolução com porta e avaliação pareada (§7.3, §13) | **Sim, fora do caminho da pergunta** (processo em lote) | Já existe e funciona (`semantics/evolve.py`, `gate.py`) |
| MongoDB, PDF/Word, extração, resolução de identidade, retrieval (§10–11) | **Não** | Não há esses dados no problema. A arquitetura deixa a porta de fonte pronta para recebê-los |

---

## 2. Princípios de arquitetura aplicados

1. **Responsabilidade única por estágio e contratos tipados entre estágios.** Cada estágio recebe um tipo e devolve outro, ou para com um `Status` e diagnósticos. Nenhum estágio conhece o anterior além do tipo.
2. **Portas e adaptadores (hexagonal).** O núcleo não importa OpenAI, Ontop, EvoOntology nem o sistema de arquivos. Ele depende de interfaces: `LLM`, `SparqlSource`, `Lexicon`, `TraceSink`. Cada uma tem um adaptador real e um falso para teste.
3. **Fonte única da verdade do domínio.** Um **Catálogo de Domínio** gerado da ontologia (`met.ttl` + `met-structure.ttl`) e do mapeamento é a única definição de:
   - grandezas, unidades, dimensões e conversões;
   - agregações permitidas, forma do tempo e faixas físicas.
   A ingestão, o mapeamento, o compilador, o verificador e o leitor de unidades consomem o catálogo, sem tabelas próprias.
4. **O probabilístico cercado pelo determinístico** (princípio do documento, §4):
   - o LLM só **escolhe sentidos de um cardápio fechado** e **cita o trecho** que justifica cada escolha;
   - tempo, números, unidades e SPARQL são produzidos por código.
5. **Falhar fechado e dizer "não sei".** Cada estágio pode encerrar com `needs_clarification`, `unsupported`, `no_results` ou `rejected`, e sempre diz o motivo. Nenhuma resposta parcial é apresentada como completa.
6. **Uma versão em execução.** As versões v1–v7 saem do caminho de execução e ficam numa tag do git, para as comparações históricas. Experimentos novos entram como **estratégias trocáveis atrás de uma porta**, não como flags espalhadas.
7. **Configuração explícita.** Caminhos, endpoints, portas, chave e teto de gasto ficam num único `Settings`, carregado do ambiente. Hoje há `/home/claude/...` e `C:\Users\...` fixos no código.

---

## 3. Visão geral (fluxo de uma pergunta)

```
 pergunta
   │
   ▼
[1] Leitor determinístico ─────────► Reading (tempo, números+unidade, estações citadas, palavras sem dono)
   │                                   reaproveita pipeline/spans.py
   ▼
[2] Intérprete (LLM) ◄── Léxico (EvoOntology, via fachada) : cardápio de grandezas/estações candidatas com IRI, unidade, BFO
   │                                   o LLM escolhe sentidos e cita trechos (prompt único, ex-v8)
   ▼
[3] Conciliador + Verificador-pré ──► CanonicalQuery (IR) válida
   │     trechos existem? número sem dono? unidade × grandeza? medida × contagem? alcance mínimo?
   │     IRI existe? agregação permitida? categoria BFO/disjunção? grandeza tem dados? período coberto?
   ▼
[4] Planejador ────────────────────► Plan = [SubQuery…] (1, ou 2 numa comparação)
   ▼
[5] Compilador IR → SPARQL ────────► SPARQL (único caminho; o que não monta = unsupported)
   │     reaproveita pipeline/compiler.py::compile_structured
   ▼
[6] Executor (porta SparqlSource) ─► Rows + SQL gerado pelo Ontop (proveniência)
   │     política somente-leitura (kgqa/store.py::check_policy), papel kgqa_reader, timeout
   ▼
[7] Verificador-pós ───────────────► VerifiedResult (vazio × cobertura, n pequeno, unidade, truncamento)
   ▼
[8] Apresentador ──────────────────► Answer: texto determinístico + eco da interpretação + ressalvas + proveniência PROV-O
   │     (opcional: redação por LLM conferida por grounding.check_answer)
   ▼
[9] Trace ─────────────────────────► trajetória JSON  ──►  (lote) Evolução EvoOntology: minerar → porta BFO/HermiT → avaliação pareada → publicar
```

---

## 4. Componentes, contratos e de onde vêm

### 4.1 Tipos do domínio (`metqa/domain/`, puros, sem I/O)

- `Question`, `Reading` (de `spans.py`), `Status`/`Diagnostic`/`QueryResponse`/`Provenance` (reuso direto de `kgqa/contract.py`).
- **`CanonicalQuery` (a IR)** é o "canonical query" do §8 do documento, sem depender da fonte:

  | Campo | Conteúdo |
  |---|---|
  | `intent` | `value` (um número), `series` (por estação/ano/mês/dia), `ranking` (top-N), `count` (com condição), `extreme_with_attribute` ("a maior e em qual cabeceira"), `instant` ("às 12h"), `comparison` (dois escopos) |
  | `measure` | IRI da grandeza |
  | `stations` | lista de IRIs |
  | `scope` | `TimeScope`: janela, horas locais, dias da semana, instante |
  | `aggregation` | a agregação pedida |
  | `count_of` | `readings`, `hours`, `days` ou `reports` |
  | `conditions` | condições já na **unidade canônica** |
  | `daily` | a estatística do dia, quando a pergunta conta dias |
  | `group_by`, `order` | forma do resultado |
  | `spans` | o trecho da pergunta que justifica cada campo |
  | `assumptions` | o que foi decidido por regra e deve ser dito |

  Ela substitui o `PipelineInterpretation`, que carrega campos de várias versões.
- `Plan` (lista de `SubQuery` + combinação), `VerifiedResult`, `Answer`.

### 4.2 Catálogo de Domínio (`metqa/knowledge/catalog.py`): a fonte única

- **Gerado de:**
  - `ontology/met.ttl`, `met-structure.ttl` e `met-bfo.ttl` (grandezas, rótulos, unidade canônica, agregações, forma do tempo, `allowsAggregation`, `answerCaveat`, categoria BFO);
  - `mapping/build_mapping.py` (tabela × grandeza);
  - consulta de perfil ao Ontop (estações, cobertura, grandezas com dados).
  - Reaproveita `pipeline/vocab.py::OntologyIndex` (`load`, `from_ontop`, `link_entities`, `link_properties`) como implementação inicial.
- **Contém, num só lugar:**
  - **Unidades:** símbolo, dimensão e fatores de conversão. Hoje estão espalhadas por `spans.UNITS`/`UNIT_DIMENSION`, `vocab.UNIT_FACTORS`, `grounding.UNIT_SYMBOLS` e `met:symbol`.
  - **Faixas físicas:** uma só, usada pela ingestão (R3) e pelo SHACL. Hoje divergem.
  - **A lista das 13 grandezas e o vínculo coluna ↔ IRI**, que a ingestão, a exportação, as constraints e o mapeamento passam a ler daqui.
- **Capacidades (o "catálogo do roteador" reduzido, §9):** grandeza tem dados? qual a cobertura temporal? quais agregações e atributos próprios (cabeceira, gênero de nuvem)? Se a IR pedir algo fora disso: `unsupported` com a lacuna nomeada.

### 4.3 Léxico (`metqa/knowledge/lexicon.py`, porta `Lexicon`), o EvoOntology no caminho

- **Interface:** `resolve(frases) -> [Candidate(iri, rótulo, unidade, dimensão, categoria_bfo, cuidados, confiança)]` e `manifest()`.
- **Adaptador real:** `semantics/facade.py::GroundedLayer` + `semantics/ground.py::SemanticGrounder` (fachada própria, §7.4 regra 6). O servidor MCP `semantics/mcp_server.py` continua disponível para agentes externos.
- **Uso:** o intérprete recebe um **cardápio** com as grandezas e estações candidatas resolvidas pelo léxico, e não o vocabulário inteiro. Palavra de conteúdo que nenhum candidato cobre fica registrada como `uncovered` na trajetória. É o sinal que o minerador de `semantics/evolve.py` já sabe usar. **Com isso a evolução passa a mudar respostas mensuráveis**, e o A3 deixa de medir uma camada decorativa.

### 4.4 Leitor determinístico (`metqa/understanding/reader.py`)

- Reuso de `pipeline/spans.py`: datas por extenso, intervalos, estação do ano, parte do dia, fim de semana, horário, número+unidade, mês sem ano, palavras vagas de período.
- As tabelas de unidade passam a vir do Catálogo.

### 4.5 Intérprete (`metqa/understanding/interpreter.py`, porta `LLM`)

- **Um prompt** (o `INTERPRET_V8` de `pipeline/prompts.py`, adaptado ao cardápio).
- O LLM devolve só escolhas com trechos: grandeza, estação, cálculo, forma, operador de condição e intenção.
- Uma rodada de reparo com os achados da conciliação (como hoje).
- Adaptadores:
  - real: `pipeline/openai_client.py` + `pipeline/ledger.py::LedgerLLM` + `pipeline/llm.py::ResilientLLM`;
  - teste: `ScriptedLLM`.
- Texto da pergunta sempre isolado como dado (`pipeline/textsafe.py`).

### 4.6 Conciliador e Verificador-pré (`metqa/understanding/reconcile.py`, `metqa/verification/pre.py`)

- **Conciliação** (reuso de `pipeline/reconcile.py`):
  - trechos existem e correspondem;
  - número sem dono;
  - unidade × dimensão da grandeza;
  - medida × contagem;
  - "horas com chuva" vira `> 0`;
  - `count_of` explícito;
  - alcance mínimo, senão esclarecimento.
- **Verificação estrutural** (reuso das regras L2/L3 de `validators.py`: `_schema`, `_structure_rules`, agregação permitida, IRIs existentes) mais a **checagem de categoria BFO e disjunção** (`OntologyIndex` já carrega `disjoint`/`incompatibleWith`).
- **Capacidades** do Catálogo: grandeza sem dados e período fora da cobertura viram `unsupported`/`no_results` com motivo.
- **Sai do caminho:** `validators._ground_in_question` e as tabelas de pistas por regex (`AGG_CUES`, `GROUP_CUES`, `PLACE_NAMES`…), que existiam para adivinhar erros de um LLM que escrevia datas e números. No MVP o LLM não escreve mais isso.

### 4.7 Planejador (`metqa/planning/planner.py`)

- `intent` comum → 1 `SubQuery`.
- `comparison` (dois períodos ou duas estações citados) → 2 `SubQuery` com a mesma forma, e a combinação é feita em código (diferença e qual é maior).
- Plano maior que isso → `unsupported` dito.

### 4.8 Compilador (`metqa/planning/compiler.py`)

- Reuso de `pipeline/compiler.py::compile_structured`. Já cobre agregação, agrupamento, top-N, superlativo com atributo, dias com condição, parte do dia, dia da semana, horas distintas e boletins. Conferido no grafo real e pelo teste diferencial contra pandas (`tests/test_compiler_differential.py`, `tests/test_v8_real.py`).
- **Acréscimos mínimos:** intenção `instant` (valor num horário) e consulta de cobertura.
- **Defesa em profundidade:** a consulta montada passa pelas regras de consulta (`validators.validate_query` via `pipeline/query_facts.py`) e pela checagem prévia do motor (`OntopBackend.reformulate`).
- **Sai do caminho:** a geração de SPARQL por LLM (`GENERATE_V3`) e o compilador de "resgate" `compile_query`.

### 4.9 Executor (`metqa/execution/`, porta `SparqlSource`)

- Reuso de `kgqa/store.py`:
  - `check_policy` (somente SELECT/ASK, sem SERVICE/FROM/caminhos);
  - `OntopBackend` (POST, truncamento, `reformulate` → SQL para a proveniência);
  - `LocalRdflibBackend` para testes no grafo sintético.
- Proteção em camadas que já existe: papel `kgqa_reader` somente-leitura, `statement_timeout`, Ontop só no loopback.

### 4.10 Verificador-pós e Apresentador (`metqa/verification/post.py`, `metqa/presentation/`)

- **Pós:**
  - `kgqa/verify.py::result_status`, reescrito para olhar o `n` declarado pelo compilador em vez do nome da variável;
  - n baixo e grupos pequenos (`pipeline/caveats.py`);
  - visibilidade censurada em 20 km.
- **Apresentação:**
  - texto **determinístico** com número, unidade, estação e período (base: `pipeline/grounding.py::render_fallback`);
  - eco da interpretação (`pipeline/dialogue.py::describe`);
  - suposições da IR ("contei horas distintas", "verão = dez–fev");
  - ressalvas;
  - proveniência PROV-O (`pipeline/provenance.py`).
- **Redação por LLM:** opcional, desligada por padrão, sempre conferida por `grounding.check_answer`.
- **Diálogo de confirmação** (`pipeline/dialogue.py`): opcional na linha de comando, mostrando os trechos.

### 4.11 Orquestrador (`metqa/app/pipeline.py`) e interface

- Uma função linear de cerca de 80 linhas:

  ```
  read → interpret → reconcile/verify_pre → plan → compile → execute → verify_post → present → trace
  ```

  Cada passo devolve `Ok(valor)` ou `Stop(status, diagnósticos)`. Não há flags de versão.
- **Interfaces:**
  - linha de comando `python -m metqa` (base: `kgqa/__main__.py`);
  - saída JSON no contrato 0.2.1 (`kgqa/contract.py`).
- **Dependências em uma direção só:** `app → understanding/planning/execution/verification/presentation → knowledge → domain`. Hoje `kgqa` ↔ `pipeline` ↔ `semantics` formam ciclo.

### 4.12 Evolução (`metqa/evolution/`, processo em lote, fora da pergunta)

- Reuso integral de:
  - `semantics/trajectories.py` (registro);
  - `semantics/evolve.py` (minerar → Candidate → porta → avaliação pareada → publicar/rejeitar → propostas para a camada formal);
  - `semantics/gate.py` (IRI, categoria BFO, SHACL, HermiT com amostra do grafo real);
  - `semantics/build.py` (camada a partir da ontologia, preservando o conteúdo evoluído).
- **Mudança:** a avaliação pareada passa a rodar **o MVP inteiro** sobre um conjunto congelado (com custo de LLM, opcional), além da avaliação barata de reconhecimento (`semantics/resolution.py`).

### 4.13 Dados e camada formal (sem mudança de arquitetura, só consumo do Catálogo)

- **Mantêm-se:**
  - `ingest/` (pack → DuckDB → limpeza R1–R7 e Q1–Q5 com quarentena → PostgreSQL com chaves);
  - `mapping/build_mapping.py` (gera `met.obda`);
  - `ontology/` (fonte única com visões DL/QL/Ontop geradas, HermiT, conformância);
  - `infra/` (WSL reprodutível).
- **Mudanças:**
  - as listas de grandezas, faixas e unidades passam a vir do Catálogo;
  - `mapping/met.r2rml.ttl`, que não tem gerador nem teste, é gerado do mesmo lugar ou removido.

### 4.14 Avaliação (parte da arquitetura, não um apêndice)

- Cadeia já existente e reutilizável:
  - `eval/freeze_set.py` → `validate_set.py` → `run_independent.py` → `judgment_sheet.py` → `adjudicate.py`;
  - `eval/stats.py` (Wilson, McNemar exato);
  - teto de gasto pelo `Ledger`.
- **Métricas do MVP:**
  - respostas **erradas entregues** (a principal);
  - acerto adjudicado;
  - taxa de abstenção e de esclarecimento;
  - custo por pergunta.
- **Ablação mínima exigida pelo documento (§15), dentro do MVP:**
  - léxico ligado × desligado (RQ1/RQ3);
  - verificação BFO ligada × desligada (RQ2);
  - em conjunto **novo** com 80 a 100 perguntas.
- Os oráculos ficam no formato pandas congelado. Os scripts de oráculo por suíte (`eval/oracle_*.py`) passam a ser legado.

---

## 5. Estrutura de pacotes proposta

```
metqa/
  domain/          tipos puros: CanonicalQuery, TimeScope, Plan, VerifiedResult, Answer (+ reexporta kgqa.contract)
  knowledge/       catalog.py (fonte única), lexicon.py (porta + adaptador EvoOntology)
  understanding/   reader.py (spans), interpreter.py (LLM), reconcile.py
  planning/        planner.py, compiler.py
  execution/       sparql_source.py (porta), ontop.py, rdflib_local.py, policy.py
  verification/    pre.py, post.py
  presentation/    render.py, caveats.py, provenance.py, dialogue.py
  app/             pipeline.py (orquestrador linear), cli.py, settings.py
  evolution/       trajectories, miner, gate, evaluate (reuso de semantics/)
ingest/ mapping/ ontology/ infra/ eval/   (mantidos; passam a ler o Catálogo)
```

A migração é **estranguladora**:
1. O `metqa/` nasce importando os módulos provados do `pipeline/`, do `kgqa/` e do `semantics/`, sem copiar código.
2. Cada módulo é movido para o `metqa/` quando o núcleo novo estiver coberto por testes.
3. `pipeline/` com v1–v7 fica numa tag (`legado-v7`) e sai do caminho de execução.

---

## 6. O que o MVP responde e o que diz que não sabe

**Responde**, com proveniência:
- valor agregado de uma grandeza (estação × período, inclusive dia por extenso, estação do ano, trimestre, parte do dia, fim de semana);
- séries por ano/mês/dia/estação;
- top-N de estações;
- contagens explícitas (leituras, horas distintas, dias, boletins) com limiar ou "com chuva";
- extremo com atributo (cabeceira);
- valor num instante;
- comparação de dois períodos ou de duas estações.

**Diz que não sabe**, com o motivo:
- cidade/estado/coordenada (não há cadastro);
- grandeza inexistente;
- previsão (não há dado real de previsão);
- mediana;
- agrupamento fora do catálogo;
- datas relativas;
- planos com mais de duas subconsultas.

**Pede esclarecimento:**
- quando falta cálculo;
- quando falta alcance;
- mês sem ano, período vago;
- critério ambíguo ("mais quente": média ou máxima?).

---

## 7. Riscos e decisões que continuam abertas

- **O LLM preencher mal o formato com trechos.** O v8 nunca rodou com LLM real. A verificação é a medição da seção 8, e o reparo de uma rodada mais o esclarecimento limitam o dano.
- **Abstenção alta no começo**, porque palavras sem cobertura viram esclarecimento. É a troca certa, e o ciclo de evolução reduz isso de forma medível.
- **Hipóteses de dados ainda não confirmadas pelo professor:**
  - fuso UTC−3 fixo (D-85);
  - unidades de visibilidade e altura de nuvem (D-86);
  - política de leituras duplicadas (D-87);
  - "horas" = horas distintas (D-95).

  O MVP declara essas hipóteses na resposta em vez de escondê-las.
- **Alinhamento BFO provisório** (D-88, `docs/DUVIDAS_ONTOLOGIA.md`), que precisa de revisão de especialista.

---

## 8. Verificação (como saber que o MVP funciona)

1. **Sem custo de LLM:**
   - `pytest` completo, com fakes de `LLM`, `SparqlSource` e `Lexicon`;
   - testes de contrato do compilador contra pandas (diferencial);
   - casos do `novo_a` no grafo real com IR escrita à mão (`tests/test_v8_real.py`, 11 casos hoje);
   - varredura do leitor sobre todas as perguntas existentes;
   - teste de que o Catálogo é a única fonte (nenhuma tabela de unidade ou grandeza fora dele).
2. **Ponta a ponta no grafo real com LLM:** conjunto **novo** (80 a 100 perguntas de outro gerador, congelado com sha256), rodando MVP × v7 de referência, adjudicação e McNemar. Exige verba autorizada no ledger (ordem de US$ 3 a 5).
3. **Critério de aceite do MVP:**
   - nenhuma resposta errada entregue nas categorias da seção 6 por defeito de tempo, unidade, filtro ou contagem;
   - toda abstenção com motivo;
   - acerto adjudicado ≥ o do v7 no mesmo conjunto;
   - custo por pergunta ≤ o do v7.

---

## 9. Estado da implementação (2026-10-27)

| Estágio | Módulo | Reaproveita |
|---|---|---|
| Tipos e contratos | `metqa/domain/types.py` (`CanonicalQuery`, `TimeScope`, `Plan`, `Executed`, `Stop`) | `kgqa/contract.py` (contrato 0.2.1) |
| Catálogo de Domínio | `metqa/knowledge/catalog.py` (grandezas, unidades, capacidades, estações, cardápio) | `pipeline/vocab.py::OntologyIndex` |
| Léxico (EvoOntology no caminho) | `metqa/knowledge/lexicon.py` (`EvoLexicon`, `OntologyLexicon` para a ablação) | `semantics/facade.py`, `semantics/ground.py` |
| Leitor | `metqa/understanding/reader.py` (+ divisão de comparações) | `pipeline/spans.py` |
| Intérprete | `metqa/understanding/interpreter.py` (cardápio + trechos) | `INTERPRET_V8`, `pipeline/llm.py` |
| Conciliação | `metqa/understanding/canonical.py` | `pipeline/reconcile.py` |
| Verificação-pré | `metqa/verification/pre.py` (forma, vocabulário, capacidades, cobertura) | regras L2/L3 de `pipeline/validators.py` |
| Planejador | `metqa/planning/planner.py` (1 parte, ou comparação de 2 períodos; várias estações = um valor por estação) | — |
| Compilador | `metqa/planning/compiler.py` (+ intenção `instant`) | `pipeline/compiler.py::compile_structured` |
| Executor | `metqa/execution/source.py` (regras de consulta + checagem do motor + execução) | `kgqa/store.py`, `pipeline/validators.validate_query` |
| Verificação-pós | `metqa/verification/post.py` | `kgqa/verify.py`, `pipeline/caveats.py` |
| Apresentação | `metqa/presentation/render.py` (texto determinístico, números em português, "como entendi", ressalvas) | — |
| Orquestrador e linha de comando | `metqa/app/pipeline.py` (linear, sem flags de versão), `metqa/app/cli.py`, `metqa/app/settings.py` | `pipeline/provenance.py` |
| Evolução | `metqa/evolution/` (grava a trajetória; o ciclo é o existente) | `semantics/trajectories.py`, `evolve.py`, `gate.py` |
| Avaliação | `eval/run_independent.py --prompts metqa` (ou `metqa-formal`, sem a camada EvoOntology) | cadeia `freeze_set` → `adjudicate` |

**Verificado, sem custo de LLM:**
- `tests/test_metqa.py`: 13 testes com adaptadores falsos e o grafo sintético (contrato de cada estágio, reparo, falha fechada, previsão,
  cobertura, comparação, várias estações, instante, léxico evoluído × formal).
- `tests/test_metqa_real.py`: 10 testes no grafo real, a pipeline inteira com o LLM roteirizado. Cobrem as 8 perguntas do `novo_a` que o
  v4–v7 erravam ou deixavam sem resposta, uma comparação de dois períodos e o valor num instante. Todos dão o número do oráculo.
- Suíte completa: 1049 testes passaram.

**Ainda não feito:**
- Medir o MVP com o LLM real num conjunto novo (seção 8, item 2). Exige verba.
- Mover os módulos reaproveitados para dentro de `metqa/` e levar a ingestão e o mapeamento a lerem o Catálogo (migração gradual, seção 5).
- Aposentar v1–v7 numa tag.
