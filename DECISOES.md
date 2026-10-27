# Decisões, hipóteses e pendências — módulo KGQA (SPARQL)

Responsável: Gabriel Negreiro. Estado: incremento 2 — grafo virtual sobre os dados reais (sem LLM). Atualizado em 15/10/2026.

## Confirmadas (pelo Gabriel/equipe)
- C-01 Entrada externa do módulo: pergunta em linguagem natural (pt-BR). Reconfirmada em 14/10/2026: o router do professor envia a pergunta em LN e o módulo executa todo o pipeline de grafo (interpretação, contexto, geração, validação, execução, verificação).
- C-02 Ontologia orienta a geração de SPARQL, a validação semântica e a avaliação (com limites reconhecidos).
- C-03 Saída: resultados estruturados para integração; texto é opcional (demonstração).
- C-04 Domínio: meteorologia (reconfirmado em 14/10/2026). Dados reais chegarão como CSV.
- C-05 O router é do professor e envia LN ao módulo; o módulo não depende do intérprete compartilhado.
- C-06 Stack do grafo real: Ontop (grafo virtual, mapeamento) — escolhido pelo Gabriel em 14/10/2026.

## Decisões provisórias de implementação (reversíveis)
| ID | Decisão | Por quê | Como reverter |
|---|---|---|---|
| D-01 | Python 3.11 + rdflib 7.6 em memória (só para a suíte sintética) | Zero infraestrutura; SPARQL 1.1 completo para 2,6 mil triplas | Implementar outro `SparqlBackend` (Oxigraph, Fuseki, GraphDB) |
| D-02 | Ontologia provisória sobre SOSA + OWL-Time + QUDT | SOSA é Recomendação W3C/OGC para observações; separa sensor, propriedade, resultado e tempos | Substituir `ontology/met.ttl`; reescrever as 16 consultas de referência |
| D-03 | Sem regime de inferência (consultas usam tipos explícitos) | Resultados previsíveis; inferência vira variável a avaliar depois | Materializar RDFS/OWL RL antes de consultar e reavaliar |
| D-04 | Instantes com offset local fixo −03:00 | Datas da pergunta são locais; offset explícito evita ambiguidade | Normalizar para UTC e converter na interpretação |
| D-05 | Dia D = [D 00:00, D+1 00:00); "entre D1 e D2" inclui D2 inteiro | Interpretação usual de período em pt-BR | Mudar regra no interpretador e nas referências |
| D-06 | Precipitação = acumulado em [h, h+6h); entra num período se o intervalo inteiro estiver contido | Evita contar parcialmente um acumulado | Exigir dados horários ou rateio explícito |
| D-07 | `time:inXSDDateTime` + `xsd:dateTime` (propriedade obsoleta na OWL-Time) | rdflib 7.6.0 compara `xsd:dateTimeStamp` de forma errada e silenciosa (teste `test_backend_quirks.py`) | Voltar a `inXSDDateTimeStamp` num backend que o suporte |
| D-08 | Previsão (`met:Forecast`) não é `sosa:Observation` | Pergunta sobre valor "registrado" não pode usar previsão | Alinhar com a ontologia oficial |
| D-09 | Resultados no formato W3C SPARQL 1.1 Query Results JSON | Preserva tipo, idioma, IRI; é padrão | — |
| D-10 | Toda consulta agregada projeta `?n` (contagem) | AVG/SUM sobre vazio retorna 0 em SPARQL 1.1; sem `?n` não se distingue "zero" de "sem dados" | — |
| D-11 | Executor em processo filho com timeout; não injeta LIMIT | rdflib não tem timeout; LIMIT mudaria a semântica de agregações. Limita linhas *buscadas* e marca `truncated` | Usar timeout nativo do triplestore |
| D-12 | Representação interna (`Interpretation`) existe, mas não é interface externa | Respeita C-01 e facilita diagnóstico | — |
| D-13 (planejada) | Validação semântica da consulta gerada usa axiomas de disjunção da ontologia para rejeitar padrões insatisfazíveis antes de executar (ex.: mesma variável tipada como observação e previsão) | Análogo, no nível da consulta, às verificações WF do BFO-OBDA no nível do mapeamento: erro tipado em vez de resultado vazio silencioso | — |
| D-14 | Respostas esperadas da avaliação valem para o regime "sem inferência"; cada caso registra o regime | Com inferência (RDFS, OWL 2 QL, BFO) consultas por classe podem ganhar respostas e agregações podem mudar | Recalcular oráculo por regime |
| D-15 | Ontop 5.5.0 sobre **PostgreSQL 16** (não DuckDB); DuckDB fica para preparação e oráculo | O driver JDBC do DuckDB só sai pelo Maven Central, bloqueado nos dois ambientes; o do PostgreSQL vem do GitHub | Trocar o banco atrás do Ontop: mesmas tabelas, outro `jdbc.url` e driver |
| D-16 | Uma tabela por variável observável; mapeamento Ontop gerado por script (`mapping/build_mapping.py`) | O Ontop poda tabelas pela propriedade constante na consulta; padrão único para 13 variáveis | — |
| D-17 | Sensores virtuais (um por estação × variável) para manter o caminho estação → `sosa:hosts` → sensor → observação | A fonte não identifica instrumentos; o caminho fica igual ao do grafo sintético e as consultas se transferem | Mapear sensores reais se o cadastro existir |
| D-18 | Nó de tempo (`time:Instant`/`time:Interval`) por observação, não compartilhado entre estações | Instantes compartilhados obrigavam o Ontop a usar DISTINCT sobre UNIONs: 5–76 s e erro interno com ORDER BY; por observação, 0,1–0,3 s | Voltar a instantes compartilhados se o Ontop otimizar esse caso |
| D-19 | Chaves primárias e estrangeiras declaradas no PostgreSQL | Integridade (falham se houver IRI duplicado) e otimização do Ontop (eliminou um junção de 8,6 mi × 8,9 mi derivada por raciocínio OWL 2 QL sobre o range de met:reportOf) | — |
| D-20 | Usuário `kgqa_reader` somente leitura no banco, com `statement_timeout` de 60 s | Defesa em profundidade além da política SPARQL; o Ontop NÃO repassa o cancelamento quando o cliente desiste | Ajustar teto conforme o contrato de latência |
| D-21 | Top-level `LIMIT max_rows+1` acrescentado pelo executor Ontop (substitui D-11 nesse backend) | Um LIMIT de nível superior só corta linhas finais, não altera valores; evita materializar milhões de linhas e detecta truncamento | — |
| D-22 | Oráculo real em pandas lendo `DOUBLE`; nada ordenado pelo DuckDB | DuckDB 1.5.6 devolveu top-n errado em `ORDER BY DECIMAL DESC LIMIT` após DELETEs (sumiu após compactar a base; teste em `test_backend_quirks.py`) | — |
| D-23 | Controle de qualidade Q1a–Q5 além das faixas físicas (ver `data/REGRAS_LIMPEZA.md`) | Faixa física não pegou códigos de erro (100,2 mm), sensor travado, picos isolados e rajadas impossíveis | Ajustar limiares com o professor |

## Hipóteses sobre o banco real (NÃO verificadas)
- H-01 Haverá observações com estação, variável, instante/intervalo, valor e unidade identificáveis.
- H-02 O professor fornecerá ou permitirá derivar um grafo RDF (direto, via mapeamento R2RML/Ontop, ou por materialização).
- H-03 Volume pequeno o suficiente para rdflib na fase de protótipo — provavelmente falso no banco real.
- H-04 O grafo oficial pode vir por (a) materialização com OntoPy/BFO-OBDA (arquivos -> RDF em memória + SPARQL) ou (b) grafo virtual via Ontop sobre banco relacional. Nos dois casos o módulo consome SPARQL; muda o backend, o regime de inferência e os tempos.
Nenhum campo do protótipo deve ser assumido no banco real.

## Pendências
- P-01 Confirmar ontologia oficial e alinhamento com BFO (equipe de ontologia).
- P-02 Formato de entrega dos dados reais e responsável pelo grafo.
- P-03 Provedor de LLM e restrições (custo, dados sensíveis, execução local).
- P-04 Contrato de saída v0.1 precisa ser revisado com quem consome (verificação/síntese).
- P-05 Regime de inferência oficial (nenhum, RDFS, OWL 2 QL/RL).
- P-06 ~~Leitura dos PDFs~~ — lidos em 30/09/2026 (Calvanese 2018; BFO-OBDA, JOWO/FOIS 2026).
- P-07 Alinhamento BFO da ontologia meteorológica (levar à equipe de ontologia), pontos em aberto:
  estação e sensor como MaterialEntity; observação como Process (WF4 exige hasParticipant);
  temperatura como Quality inerente ao ar/local (WF3 exige inheresIn) — mas SOSA usa propriedade
  *genérica* (met:AirTemperature), não qualidade particular; valor medido como entidade de informação
  (WF5 exige isAbout); previsão: é sobre o quê, se a qualidade futura ainda não existe?;
  OWL-Time x regiões temporais da BFO. Obs.: "Information Content Entity" vem do IAO/CCO, não do
  núcleo ISO 21838-2 — confirmar qual extensão a equipe usará.
- P-08 Identidade entre fontes: se a mesma estação existir em outra fonte, adotar IRI canônico
  (padrão canIriOf de Calvanese/Xiao 2018) e devolver esse IRI na procedência.

## Após a arquitetura "Ontology-Grounded Agentic Architecture" (Parente, 30/09/2026)
- P-09 RESOLVIDA (14/10/2026): entrada em LN, ver C-01/C-05. Texto original: Interface de entrada: no documento, um *Interpreter agent* compartilhado gera a consulta canônica
  (SPARQL sobre IRIs da ontologia) e o adaptador de grafo é um "serializador determinístico" dela.
  Isso contradiz C-01. Decidir com a equipe: (a) o módulo recebe a consulta canônica e o NL→SPARQL
  vira contribuição ao intérprete; ou (b) mantém NL como entrada própria. Proposta: núcleo do módulo
  aceita consulta canônica; caminho NL fica como camada opcional.
- P-10 Política do executor rejeita FROM/FROM NAMED. A arquitetura guarda fatos extraídos de documentos
  em named graphs por versão, com PROV-O e filtro por confiança. Trocar a proibição por lista de grafos
  permitidos quando houver triple store real.
- P-11 RESOLVIDA (14/10/2026): meteorologia. Texto original: Domínio: o exemplo do documento é contratos/fornecedores (ERP); o protótipo é meteorologia.
  Confirmar se meteorologia continua sendo o domínio-alvo.
- P-12 Prioridade baixa enquanto o contrato com o router não for definido. Novos requisitos para o adaptador: filtros de acesso compilados na consulta (verificar presença),
  aceitar IRIs vinculados pelo planner (VALUES em blocos, bind-join), indicar cobertura/completude no
  status `no_results`, gerar o descritor do catálogo de capacidades a partir de ontologia/SHACL,
  registrar a consulta executada no trace.
- P-13 Agora interna ao módulo (controlamos ontologia, mapeamento CSV→RDF e consultas). Texto original: Vocabulário do triple store: se o grafo usar padrões SOSA (observação → resultado → valor) e a
  consulta canônica for escrita sobre outro vocabulário, o "serializador" precisa reescrever a consulta.
  Confirmar que grafo e ontologia formal compartilham o mesmo vocabulário.
- P-14 Ingestão do CSV real (dados levantados em 14/10/2026, ver data/DICIONARIO_DADOS.md): mapear colunas para a ontologia, definir fuso, unidades, instantâneo x acumulado e ausências a partir dos dados, não do protótipo.
- P-15 RESOLVIDA (15/10/2026): Ontop sobre PostgreSQL (C-06, D-15). 105,4 mi de observações; consultas de referência em 30 ms–2,9 s.
- P-16 (decisão de trabalho D-85, não confirmada) Fuso: dados parecem estar em UTC−3 fixo para todas as estações, com artefato nas datas de início do
  horário de verão (2016-10-16, 2017-10-15, 2018-11-04). D-04 continua válida se confirmado.
- P-17 (decisão de trabalho D-86, não confirmada) Unidades a confirmar: visibilidade e altura de nuvem em dezenas de metros; vento em kt; direção em dezenas de graus.
- P-18 Falta cadastro de estações (nome, local, coordenadas): necessário para perguntas como "em Manaus".

## Após o incremento 2 (15/10/2026)
- P-19 O Ontop avisa que `rdfs:range xsd:boolean` está fora do OWL 2 QL (ignorado). Resto da ontologia dentro do perfil.
- P-20 Exportar o mapeamento para R2RML (`ontop mapping to-r2rml`), formato pedido pela arquitetura do professor.
- P-21 Pasta `METEOROLOGIA\_transferencia` no OneDrive do Gabriel (~480 MB de cópias compactadas): pode ser apagada.
- P-22 Próximo passo do módulo: interpretação + recuperação de contexto (léxico de rótulos, fragmento da T-Box)
  e gerador com LLM, avaliado com `eval/questions_real.yaml` (dev/test separados).

## Camada semântica consultiva — EvoOntology ligado à ontologia formal (22/10/2026)
| ID | Decisão | Por quê | Como reverter |
|---|---|---|---|
| D-24 | EvoOntology (MIT) como dependência fixada no commit `c94389b` (`requirements.txt`); só o núcleo `evoontology/`, sem os plugins | O núcleo não tem dependências e roda como biblioteca; os plugins exigem um agente de código | Remover `semantics/` e a linha do `requirements.txt` |
| D-25 | Fachada própria `semantics/facade.py` (`GroundedLayer`) | `Term.from_dict` descarta campos desconhecidos: o IRI e a categoria BFO que o documento exige nos Termos não chegariam ao agente. Atende à regra 6 de §7.4 (interface estável) | — |
| D-26 | v0 da camada gerada da ontologia, sem texto escrito à mão (`semantics/build.py`); evidência = só procedência da ontologia | Perguntas de `eval/` como Evidência contaminariam o conjunto que avalia a evolução | — |
| D-27 | `ontology/met-bfo.ttl`: alinhamento com a BFO **provisório**, fonte única da categoria | §7.4 regra 2: a categoria é copiada da ontologia, nunca inventada pelo agente. Não é carregado pelo Ontop | Substituir pelo alinhamento oficial (P-07) |
| D-28 | `resolve_semantics` é chamada **pelo pipeline**, de forma determinística, sobre os trechos da pergunta; não pelo LLM | O cliente de LLM é de uma chamada só, sem laço de ferramentas. **Desvio do §8**, que descreve o agente chamando a ferramenta | Trocar por laço de ferramentas quando o cliente suportar |
| D-29 | Só correspondência **exata** (nome ou sinônimo) entra no bloco `<semantica>` | O casamento do núcleo é por subconjunto de palavras e ignora ordem e palavras de uma letra: `vento e a rajada` casava com `rajada de vento` | — |
| D-30 | Prompt **v5** = v4 + bloco `<semantica>` na etapa 1; v1–v4 intactos. `semantics_check` só **registra** concordância na trilha | Preserva as medições já feitas; nenhuma regra nova barra sem medição de falso positivo (REVISAO_CRITICA §1, item 15) | Usar `--prompts v4` |

Porta de validação (`semantics/gate.py`, §7.4 regra 4): IRI existe, categoria BFO igual à da ontologia, IRI único, agregações e unidade não contradizem os axiomas. **Limite:** Restrição em texto livre não é conferível por regra.

### Pendências novas
- P-23 **Medir v5 contra v4 com o LLM real** nas suítes fresh/held-out. Não foi feito: só testes com LLM roteirizado. Saldo do teto: US$ 11,48 de 11,90 já registrados; exige `--authorize-usd`.
- P-24 Ciclo de evolução em lote com avaliação pareada (Parent × Candidate) sobre conjunto congelado + regressão. O servidor MCP e a porta já existem; faltam o ambiente de avaliação sobre `eval/` e o agente de evolução.
- P-25 Trilha → trajetórias do EvoOntology. `semantics`/`semantics_check` já saem na trilha; falta o conversor e os sinais de reparo/abstenção/fallback.
- P-26 Lacunas de sinônimo vistas na cobertura (64 de 78 perguntas reconhecidas): "choveu", "chuvoso", "mais quente/fria/úmida", gênero de nuvem (cumulonimbo). **Não preencher à mão olhando as perguntas de avaliação**; é o que a evolução deve aprender das trajetórias.
- P-27 Categoria BFO de precipitação, vento e visibilidade como `quality` é discutível (ver `met-bfo.ttl`). Levar à equipe de ontologia junto com P-07.
- P-28 Estações e conceitos SKOS de gênero de nuvem ainda não são Termos (sem categoria BFO).

## Ambiente do grafo real no WSL (22/10/2026)
| ID | Decisão | Por quê | Como reverter |
|---|---|---|---|
| D-31 | Ontop + PostgreSQL rodam no **WSL2 (Ubuntu)**, dados em `~/metdata` (fora do OneDrive); `~/.wslconfig` com 6 GB, 8 GB de swap, 8 CPUs | Os scripts são Linux; o Java do Windows é o 1.8 (o Ontop 5.5 exige 17+); o WSL padrão tinha 3,8 GB | Apagar `~/.wslconfig` |
| D-32 | Ferramentas instaladas no espaço do usuário (sem `sudo`): `uv`, JDK 17 Temurin, Ontop CLI 5.5.0, `postgresql-42.7.4.jar`; Python 3.12 em `~/metdata/venv` | `sudo` pede senha e o Python 3.14 do Ubuntu 26.04 não tem `pgserver`. **Sem conferência de checksum dos downloads** | `rm -rf ~/tools ~/metdata/venv` |
| D-33 | Caminhos por `MET_HOME` (`infra/*.sh`, `ingest/{transform,export_pg}.py`, `eval/oracle_real.py`, 2 testes); `pg.sh` ganhou `init` (cria o cluster) e só usa `runuser` como root | Os caminhos eram fixos de outro ambiente (`/home/claude`) e **os testes reais eram pulados em silêncio** quando o arquivo não existia | — |
| D-34 | `ontop.sh` copia `met.ttl`/`met.obda`/`met.properties` para `$MET_HOME/ontop_cfg` e aponta o Ontop para a cópia | O Ontop lê caminhos como URI: `Área de Trabalho` (espaço e acento) dá `Illegal character in path` | — |
| D-35 | `parse_json_object` tem limite explícito de profundidade (32), contado sem recursão | A defesa dependia do `RecursionError` do `json.loads`, que varia com o Python: um JSON de 5000 níveis passava no 3.12 (WSL) e falhava no 3.13 (Windows) | — |

Reiniciar o ambiente (o WSL desliga serviços quando para): `source ~/metdata/env.sh; bash infra/pg.sh start; bash infra/ontop.sh start`.
Resultado: `rebuild.sh` em ~28 min; `run_reference --suite real` 15/15 (RD03 levou 16,5 s, a mais lenta); suíte inteira 422 passam, 0 pulados.

## Índice a partir do grafo real (22/10/2026)
| ID | Decisão | Por quê | Como reverter |
|---|---|---|---|
| D-36 | `OntologyIndex.from_ontop(backend)`: ontologia dos arquivos (`load(with_data=False)`); estações, cobertura e grandezas com dados do Ontop; predicados/classes do `.obda`. Ao vivo, sem cache (1,5 s). Falha de forma explícita se uma consulta falhar ou se não houver estações | Um índice sem estações faria toda estação virar "desconhecida" e a pipeline recusaria tudo sem dizer por quê. As consultas são baratas (< 1,2 s) | `OntologyIndex.load()` continua sendo o índice sintético |

Resultado no grafo real: 178 estações (rótulo = sigla), cobertura 2016-01-01 a 2025-12-31, **as 13 grandezas têm dados** (vento e pressão, que no sintético caíam em `PROPERTY_WITHOUT_DATA`). RD02 de ponta a ponta com LLM roteirizado: 3196,0 mm em 8760 medições, igual ao oráculo.

### Achados que definem a Fase 3 (verificados no grafo real)
- P-29 **O contexto do LLM não menciona** `met:localDate`, `met:runwayDesignator`, `met:multipleReadings` nem `met:windCondition` (sem domínio declarado, ou com imagem `xsd:`, então `_ontology_context` os omite). Sem `runwayDesignator`, perguntas "por cabeceira" (RT01, RT02) não têm como ser respondidas pelo LLM.
- P-30 **`PERIOD_MISMATCH` recusa a consulta de referência real de RD02**, que usa `met:localDate` (o atalho documentado no README). As regras só reconhecem o caminho de tempo por intervalos. O compilador de reserva monta pelo caminho de intervalos e acerta (29 ms). Decidir se `met:localDate` é aceito pelas regras ou se o contexto continua ensinando só os intervalos.
- P-31 **Tamanho do contexto no real:** ~1,2 mil tokens (`labels`) e ~2,4 mil (`ontology`), metade só de 178 linhas `- st:SIGLA | SIGLA`. Mostrar só as estações citadas na pergunta, mais a contagem. Isso altera o prompt de v1–v4 no real; v1–v4 medidos no sintético não mudam.

## Período por dia local — opção B (22/10/2026)
| ID | Decisão | Por quê | Como reverter |
|---|---|---|---|
| D-37 | As regras aceitam `met:localDate` para períodos de **dias inteiros**: `_check_day_period` confere as datas contra o período da interpretação (`>= início`, `<= fim`, ou `= dia`; datas constantes no padrão valem só para um dia). Recusa: mistura com limites por data-e-hora (`PERIOD_MIXED_FORMS`), fuso diferente de UTC−3 (`LOCALDATE_TZ`), instante (`PERIOD_UNEXPECTED`/`INSTANT_MISMATCH`) e `localDate` sem período. O contexto ensina a forma só quando o grafo a popula | A consulta de referência real de RD02 era recusada (`PERIOD_MISMATCH`); o dia local não tem a armadilha do fuso da forma por data-e-hora | Remover o ramo `uses_day` em `_conformance` |

Verificação (as três condições da recomendação):
1. **Mutações:** `tests/test_localdate.py` (24): 10 limites errados recusados, mistura, instante, fuso, sem período, e 8 formas equivalentes aceitas. Conferido que os testes **dependem** da regra: com o ramo sempre-aceita, 10 falham; sempre-recusa, 9 falham.
2. **Equivalência medida no grafo real** (`eval/equivalencia_localdate.py`, `docs/EQUIVALENCIA_LOCALDATE.md`): 256 comparações, **0 divergências**; 88 eram vazias nas duas formas (não provam nada); **168 com dados, todas iguais**, 38 delas de precipitação nos 8 tipos de período (artefatos de horário de verão P-16, dia bissexto, virada de ano).
3. **Instante fora de `met:localDate`:** garantido por regra e por teste.

**Limites da evidência:** 8 estações (1 a cada 22), 4 das 13 grandezas, 8 períodos; sem períodos de vários anos; precipitação é toda horária (um acumulado mais longo que cruzasse a meia-noite divergiria: início-do-dia ≠ intervalo inteiro contido). Se um dia houver, a opção A volta para essa grandeza.
**Não medido:** se o LLM real passa a escrever `met:localDate` quando o contexto o ensina, e se isso reduz recusas. Isso é a Fase 4.

## Contexto do LLM no grafo real (22/10/2026)
| ID | Decisão | Por quê | Como reverter |
|---|---|---|---|
| D-38 | O contexto mostra, por grandeza, os **atributos próprios** (`atributos próprios (?obs <atributo> ?x)`), lidos do `.obda` (`obda_observation_attributes`): `met:runwayDesignator` no vento (velocidade, direção, rajada), `met:windCondition` só na velocidade. Texto vem do `rdfs:comment` da ontologia | P-29: sem isso o LLM não tinha como escrever "por cabeceira" (RT01, RT02) | Esvaziar `idx.attributes` |
| D-39 | Regra `ATTRIBUTE_NOT_AVAILABLE` (L3): atributo que a grandeza pedida não tem (ex.: cabeceira com temperatura) é consulta vazia por construção. Atributos comuns (`localDate`, `multipleReadings`, `sourceFile`…) nunca são sinalizados. Desligada sem perfil real | Mesma família de `PROPERTY_WITHOUT_DATA`: recusar antes de executar | Remover o bloco em `_conformance` |
| D-40 | Estações numa **linha só** quando o rótulo é o próprio código (grafo real); com nomes distintos (sintético) o formato não muda | P-31: 178 linhas `- st:SBAA \| SBAA` repetiam a sigla. v1–v4 medidos no sintético continuam idênticos (teste compara o texto exato) | — |

Efeito no grafo real: contexto `labels` 4616 → 2703 caracteres (−41%); `ontology` 9549 → 8483 (−11%, pois agora carrega o que faltava). RT01 ("cada cabeceira de SBGR em 2019") passa de ponta a ponta com a consulta de referência executada como veio e os 4 valores do oráculo (09R 9407, 09L 9406, 27R 9403, 27L 9406). P-29 e P-31 resolvidas; P-30 resolvida por D-37.

**Aprendizado de processo:** o canal de comandos deste ambiente reduz `\` para `\` dentro de scripts. Um `"\n"` virou quebra de linha real, um `\t` virou TAB e uma continuação de linha com `\` foi engolida (corrigidos em `pipeline/vocab.py`). Edição de código com barra invertida deve usar a ferramenta de edição de arquivo, não heredoc.

## Fase 4 — primeira medição com LLM real no grafo real, split dev (22/10/2026)
Autorização: US$ 2,00 (Gabriel Negreiro, registrada no ledger). `gpt-6-luna`, prompt `v4`, 8 perguntas (`questions_real.yaml`, split dev), Ontop/PostgreSQL reais. Arquivos: `docs/RESULTADOS_LLM_REAL_v4_real_dev_r{1,2,3}.md`, `eval/reports/llm_run_v4_real_dev_r{1,2,3}.json`.

| Rodada | Status esperado | Erradas entregues | Falsa ausência | Custo | O que mudou antes dela |
|---|---:|---:|---:|---:|---|
| r1 | 6/8 | 0 | **1** (RD02) | US$ 0,231 | — (estado após as Fases 1–3) |
| r2 | 7/8 | 0 | 0 | US$ 0,260 | D-41, D-42, D-43 |
| r3 | 7/8 | 0 | 0 | US$ 0,253 | D-44 |

Custo real: **~US$ 0,03 por pergunta** (a estimativa era US$ 0,06–0,08). Gasto desta fase US$ 0,74; saldo do ledger US$ 1,33.

| ID | Decisão | Por quê (medido) | Como reverter |
|---|---|---|---|
| D-41 | **Revisão de D-37:** `PERIOD_MIXED_FORMS` removida. As duas formas de período (`met:localDate` e data-e-hora) podem aparecer juntas **se CADA uma conferir** com o período; qualquer limite que não confira segue `PERIOD_MISMATCH` | RD02/r1: o modelo escreveu as duas, a consulta estava certa (= oráculo) e a regra a barrou; o reparo a estragou. Filtros se somam (AND): redundância consistente não conta nada duas vezes | Reintroduzir o finding quando `timed and uses_day` |
| D-42 | `RELATION_DIRECTION` (L2): estação **constante** como sujeito/objeto na posição errada (ex.: `st:SBBE met:reportOf ?r`) | Causa da **falsa ausência** de RD02/r1 ("sem registros" onde há 3196 mm). O domínio/imagem só se propagava para variáveis, e Estação × Boletim não são disjuntas | Remover o bloco em `_type_check` |
| D-43 | `BIND_REUSES_VARIABLE` (L2): `BIND(… AS ?v)` com `?v` já no padrão (ignora os `Extend` internos do rdflib, `__agg_N__`) | RD03/r1: o rdflib aceita, o Ontop responde HTTP 400 e o usuário via erro de execução sem reparo | Remover o campo `bind_conflicts` |
| D-44 | `ENTITY_TEXT_MISMATCH` (L4): o texto da estação que o modelo escolheu tem de ter relação com os rótulos/código dela nos dados; conta como `unsupported` | RD07/r2: "Manaus" virou `st:SBEG` por conhecimento externo e a resposta saiu "em Manaus, choveu 3914,9 mm". Documento §8: entidade não resolvida com confiança não se adivinha. Cadastro de estações (P-18) é o que permitiria responder "Manaus" de verdade | — |
| D-45 | Runner: suíte `real`, índice do Ontop; **só timeout do LLM** é repetido | O `TIMEOUT` de consulta lenta no Ontop tem o mesmo código e reexecutaria o LLM até 4x | — |

**Leitura honesta (limites):**
- **Dev não é medida limpa.** As correções D-41 a D-44 foram derivadas dessas mesmas 8 perguntas. Só o **split test (12 perguntas) ainda não foi rodado** e deve ser rodado **uma vez**.
- n = 8, um modelo, uma execução por rodada, sem intervalo de confiança. **O LLM varia entre rodadas com o mesmo código**: RD07 foi recusada em r1, respondida em r2 (sem mudança de código nesse ponto) e recusada em r3 depois de D-44.
- RD04/r3 saiu `rejected`: depois do reparo o modelo escreveu os limites de data-e-hora **sem fuso** (`"2024-01-01T00:00:00"`), o que cortaria as últimas 3 h do ano. A regra barrou uma resposta errada; é abstenção segura, não erro. O modelo insiste em escrever as duas formas apesar do contexto pedir uma só.
- O total de precipitação de Manaus/SBEG (3914,9 mm) parece alto para a região e **não foi investigado**; a consulta foi descartada por D-44.
- Não medido: `v5` (camada semântica) contra `v4` (P-23); RT02 (subconsulta aninhada) e demais perguntas do split test.

## Split test — a medida limpa (22/10/2026)
Rodado **uma vez**, no mesmo estado do código do dev (nenhuma alteração entre a rodada 3 e esta). `v4`, `gpt-6-luna`, 12 perguntas (`RT01–RT12`), US$ 0,3365. Arquivos: `docs/RESULTADOS_LLM_REAL_v4_real_test_r1.md`, `eval/reports/llm_run_v4_real_test_r1.json`.

| | dev (r3, não limpo) | **test (limpo)** |
|---|---:|---:|
| status final igual ao esperado | 7/8 | **7/12** |
| respondíveis corretas | 4/4 | **5/6 conferidas**; 4 respondíveis recusadas |
| **respostas erradas entregues** | 0 | **1 (RT12)** |
| falsa ausência de registros | 0 | 0 |
| abstenções indevidas | 0 | 4 (RT01, RT02, RT04, RT05) |
| custo | US$ 0,25 | US$ 0,34 |

**Nada foi corrigido depois deste resultado.** Qualquer ajuste daqui para a frente é derivado destas 12 perguntas e exige um conjunto novo para medir.

### Achados (causas verificadas no relatório)
- P-32 **O esquema da interpretação não expressa** agrupamento (RT01 "por cabeceira", RT05 "em cada ano"), atributo no resultado (RT02 "em qual cabeceira"), ranking/moda (RT12 "três mais frequentes") nem filtro categórico (RT04 "cumulonimbo (CB)"). O modelo respondeu `unsupported` com honestidade (1 chamada, `UNSUPPORTED_BY_MODEL`). O esquema é `{properties, entities, filters numéricos, period, instant, aggregation}`. Maior lacuna frente à consulta canônica do documento (agregados, ordenação, rótulo de intenção).
- P-33 **A correção de P-29 (D-38) só chegou à etapa 2.** A etapa 1 recebe o contexto `labels`, que não lista os atributos próprios, e foi nela que RT01/RT02 foram recusadas ("cabeceira não está disponível entre as estações ou dimensões listadas"). **Corrijo uma afirmação minha anterior:** "RT01 passa de ponta a ponta" valia só com a interpretação roteirizada, que pula a etapa 1. Com o LLM real RT01 não passa.
- P-34 **RT12 (única resposta errada):** "três direções de vento mais frequentes em SBGR" virou `met:WindSpeed` + `count`, e a resposta foi "contagem da velocidade do vento 37622; os dados não informam as três direções mais frequentes". O texto admite a lacuna e o eco mostra a interpretação, mas é outra pergunta respondida com status `answered`. L4 não objetou porque o rótulo `vento` (altLabel de `WindSpeed`) é reconhecido na pergunta, e "direções de vento" não casa com o rótulo `direção do vento` (plural e preposição). O alias genérico `vento` é ambíguo entre velocidade, direção e rajada.
- P-35 **RT10** ("temperatura amanhã"): esperado `unsupported`, obtido `needs_clarification` pela porta `RELATIVE_DATE` (sem custo, antes do LLM). Recusa segura; o gabarito e a porta divergem. Não alterar o gabarito depois de ver o resultado.

Boas: RT03, RT06, RT07, RT08, RT09 corretas (incl. `met:localDate`, 2 reparos em RT09) e RT11 com esclarecimento esperado. Nenhuma falsa ausência.

## Forma do resultado — esquema da interpretação ampliado (prompt v6, 22/10/2026)
Origem: split test limpo (7/12), P-32 a P-34. 4 das 5 falhas vinham do esquema, que não expressava agrupamento, atributo, ranking nem filtro categórico. **Nada disto foi medido com o LLM real ainda**; só com LLM roteirizado, regras e o oráculo independente.

| ID | Decisão | Por quê | Como reverter |
|---|---|---|---|
| D-46 | A interpretação ganha `group_by` (`station`, `year`, `month`, `day`, `value`, ou atributo próprio da grandeza), `attributes` (superlativo: "em qual cabeceira") e `order` (`{by: aggregate, direction, limit 1–100}`). Todos opcionais; vazios = comportamento de sempre | P-32 | Usar `--prompts v5` |
| D-47 | Com esses campos, a consulta é **montada por código** (`compile_structured`), nunca escrita pelo LLM; sem montagem possível a resposta é `unsupported` (`UNSUPPORTED_SHAPE`), nunca um palpite. A resposta é a **tabela copiada dos resultados**, sem a chamada de redação | Fiel à interpretação por construção (o que a pergunta pede é conferido em L4); evita troca de valores entre grupos no texto livre; 1 chamada ao LLM em vez de 3. Alinha com o documento: a parte formal decide o significado | `ps.structured = False` |
| D-48 | Regras novas: **L2/L3** (`UNKNOWN_DIMENSION`, `DIMENSION_WITHOUT_DATA`, `GROUP_BY_NEEDS_AGGREGATION`, `VALUE_GROUP_NEEDS_COUNT`, `GROUPED_FILTER_AMBIGUOUS`, `ATTRIBUTES_*`, `ORDER_NEEDS_GROUP_BY`, `STRUCTURE_NEEDS_ONE_PROPERTY`…) e **L4** (a forma tem de estar na pergunta e o que a pergunta pede tem de estar na forma: `GROUP_BY_NOT_IN_QUESTION/OMITTED`, `ATTRIBUTE_*`, `ORDER_NOT_IN_QUESTION/LIMIT_MISMATCH/DIRECTION_MISMATCH/OMITTED`). Só agem com `structured=True` (v6) | Sem L4 os campos novos passariam sem conferência | — |
| D-49 | `link_properties` compara por palavras **normalizadas** (sem de/do/da, plural reduzido): "direções de vento" = "direção do vento" | P-34 (RT12): o apelido genérico `vento` (velocidade) ganhava. **Vale para todos os prompts com L4 (v3–v6)**; os testes de controle não acharam falso positivo | Voltar o casamento por regex em `vocab.py` |
| D-50 | Fora do escopo: **filtro categórico** (RT04, gênero de nuvem + contar boletins distintos) | Exige modelar a camada de nuvens (P-28), não só o esquema. A pergunta é recusada com `unsupported` | — |
| D-51 | Convenção de colunas: `station`, `year`, `month`, `day`, `measured`, o atributo pelo nome curto (`runway`, `condition`), `value` (agregação), `n`, `t`. Só `met:localDate` para o período | As consultas de referência de cada pergunta usam nomes próprios; a comparação do conjunto novo foi escrita na convenção | — |

**Verificação (sem LLM):**
- 5 formas da medição (RT01, RT02, RT05, RT06, RT12): a consulta montada passa nas regras e **confere com o oráculo** no grafo real.
- **Conjunto novo `eval/questions_real_fresh.yaml` (RF01–RF16)**, escrito depois das correções e antes de rodar qualquer LLM nele: 11 respondíveis (8 de forma nova, 3 simples) e 5 recusas. As 11 consultas de referência conferem com o oráculo pandas (`run_reference --suite real_fresh`, 11/11).
- As 8 interpretações corretas das perguntas novas de forma passam em L4 **sem nenhum achado** (frases que as regras não viram ao serem escritas), e as 8 consultas montadas conferem com o oráculo.
- Um empate na fronteira de ranking foi achado ao montar o gabarito (SBSV 2021, 2º e 3º lugar com 706) e a pergunta foi trocada por SBFZ 2021 (sem empate).
- Suíte: **563 passam no WSL (0 pulados)**.

**Limites:**
- **A melhoria na resposta do LLM real não foi medida.** Falta ver se o modelo preenche `group_by`/`attributes`/`order` corretamente a partir da linguagem natural (L4 só barra o que erra). O custo estimado de rodar `v6` nas 16 perguntas é ~US$ 0,35–0,50; saldo do ledger US$ 0,99.
- Dois pontos de linguagem das regras L4 são palpites a validar: as expressões de agrupamento são listas de padrões, e a omissão de dimensão pode barrar uma pergunta correta (custo: abstenção).
- Ranking com empate no último lugar corta arbitrariamente (desempate por chave, ascendente); o texto não avisa do empate.
- `attributes` só vale para superlativo (max/min), com `OPTIONAL` para a leitura sem atributo; com agrupamento o atributo entra como dimensão.

## Medição do v6 × v4 no conjunto novo (23/10/2026)
Detalhes e limites em `docs/COMPARACAO_V6_V4_REAL_FRESH.md`. Gasto desta medição US$ 0,82 (v6 US$ 0,293; v4 US$ 0,525); **saldo do ledger US$ 0,17**.

| | v4 | v6 |
|---|---:|---:|
| status esperado (16) | 13 | **16** |
| respondíveis corretas (11) | 7 (+1 de formato) | **11** |
| chamadas ao LLM / custo | 38 / US$ 0,525 | **22 / US$ 0,293** |

- **A "resposta errada" do v4 em RF01 é de formato, não de valor** (12 totais e 12 contagens iguais ao oráculo; faltou a coluna `year` e o mês veio como texto). O juiz estrito a conta errada.
- O v4 também acertou RF02, RF05, RF07 e RF08 (o modelo escreve o `GROUP BY` mesmo sem o campo no esquema). O ganho do v6 está nos atributos (RF03, RF04) e em evitar a consulta que o Ontop recusa (RF06), mais custo menor.
- **O conjunto favorece o v6 por construção** (escrito por quem já conhecia as capacidades e as falhas). A medida limpa sem esse viés continua sendo o split test (7/12).
- P-36 **Consulta aceita pelo rdflib e recusada pelo Ontop (2ª vez):** `GROUP BY (YEAR(?t))` com projeção `(YEAR(?t) AS ?ano)` dá HTTP 400. Consultas simples escritas pelo LLM seguem expostas; sem regra ainda.
- P-37 O `v6` ainda não foi rodado no split test (`RT01–RT12`), onde 4 das 5 falhas do v4 eram de esquema. Rodá-lo lá seria reutilizar um conjunto já visto (não é medida limpa para o v6) e o saldo (US$ 0,17) não cobre.
- P-38 Sem verificação sobre o `v5` (camada semântica) contra o `v4` (P-23).

## P-36 resolvida — expressão sobre a chave do GROUP BY (23/10/2026)
| ID | Decisão | Por quê | Como reverter |
|---|---|---|---|
| D-52 | Regra `GROUPED_PROJECTION_EXPR` (L2): `SELECT (YEAR(?t) AS ?a) … GROUP BY (YEAR(?t))`, ou seja, expressão **não agregada** sobre a chave do grupo calculada depois do agrupamento. Detecta, na álgebra, um `Extend` cuja expressão usa uma variável `Aggregate_Sample` (o rdflib trata a chave como amostra). A mensagem ao LLM aponta a forma aceita: `GROUP BY (YEAR(?d) AS ?ano)` e projetar `?ano` | RF06 do v4: o Ontop respondeu HTTP 400 ("non-aggregate expression … not allowed in projection when using GROUP BY") e o usuário veria erro de execução sem reparo. 2ª consulta que o rdflib aceita e o Ontop recusa (1ª: D-43) | Remover `grouped_expr_projections` |

Verificação: a consulta EXATA do v4 é barrada antes de executar; agregado composto (`SUM/COUNT`), função sobre agregado (`ROUND(AVG())`), chave com nome e variável como chave **não** são barrados; nenhuma consulta de referência (sintéticas, reais, conjunto novo) nem montada por `compile_structured` cai na regra; e no motor real a forma inválida dá o erro e a com nome executa. Suíte: 572 passam no WSL.

**Limite:** é a regra de uma classe conhecida. Outras diferenças rdflib × Ontop vão aparecer. Uma defesa geral seria tratar o HTTP 400 do motor como falha **reparável** (devolver a mensagem do motor, higienizada e truncada, ao LLM uma vez), em vez de erro de execução final. Não implementado: a mensagem do motor ao LLM precisa de revisão de vazamento (varredura de segurança, item 7).

Como P-36 está resolvida, a linha de base v4 do `docs/COMPARACAO_V6_V4_REAL_FRESH.md` (RF06) está **levemente pior do que o v4 corrigido seria**. Qualquer comparação nova deve rodar o v4 com esta regra.

## Generalização v6 × v4 (conjunto RG) e correções (23/10/2026)
Autorização: US$ 2,00 (Gabriel Negreiro, registrada no ledger). Gasto desta medição US$ 1,78; **saldo US$ 0,40**. Relatório: `docs/COMPARACAO_GENERALIZACAO_V6_V4.md`.

| | v4 | v6 |
|---|---:|---:|
| status esperado | 22/24 | 21/24 |
| corretas (de 19) | 15 | 15 |
| erradas / falsa ausência / abstenção / respondeu o que devia recusar | 2 / 1 / 1 / 0 | 2 / 1 / 1 / **1** |
| custo | US$ 0,935 | US$ 0,840 |

**Conclusão: na generalização o v6 tem a mesma contagem de acertos do v4 (sem prova de equivalência) e tem um erro de tipo grave a mais (RG19).** O resultado de 16/16 no conjunto RF era favorecido por construção.

| ID | Correção (sem LLM) | Falha medida | Como reverter |
|---|---|---|---|
| D-53 | `met:incompatibleWith` em `met-structure.ttl` (Estação, Boletim, Observação, Plataforma); `OntologyIndex.check_disjoint`, usado só pelo verificador de consultas e **fora do contexto do LLM** (prompts já medidos não mudam). Mensagem de `TYPE_CLASH` com a dica de `met:reportOf` | RG09 (v6), RG18 (v4): falsa ausência por relação ao contrário. A correção do RD02 (D-42) só cobria estação constante | Remover as linhas `incompatibleWith` |
| D-54 | "quantas vezes" removido da pista de `group_by: value` | RG11: contagem com filtro virava `unsupported`. **Defeito meu (D-48)** | Reincluir em `GROUP_CUES["value"]` |
| D-55 | O compilador de reserva (`compile_query`) recusa mensal/anual/mês a mês/ano a ano/dia a dia/frequência/moda | RG13, RG14 (v4): respondia o total no lugar da série | Remover do `SERIES_OR_RANKING` |
| D-56 | Superlativo no SINGULAR ("o dia mais chuvoso", "a direção mais frequente") = ranking de 1: `SINGULAR_RANK`, pistas de dia/mês/ano, `ORDER_OMITTED` para limite 1 e regra no prompt v6 ("mais chuvoso" = soma por grupo; critério ambíguo continua pedindo esclarecimento) | RG17, RG18 (v6) | Remover `SINGULAR_RANK` |
| D-57 | `UNRESOLVED_PLACE` (L4): sem estação na interpretação, um nome próprio no meio da pergunta que não seja parte de rótulo de estação (e não seja "Brasil") vira `unsupported` | RG19 (v6): média de TODAS as estações apresentada como "da capital de São Paulo" | Remover `unresolved_places` |
| D-58 | O runner aceita a suíte `real_gen`; `eval/oracle_real_gen.py`, `eval/questions_real_gen.yaml` | — | — |

Verificação: tests/test_gen_regressions.py (29 testes, com as consultas e perguntas exatas das falhas), varredura de falso positivo em ~100 perguntas (UNRESOLVED_PLACE sinaliza só as 5 que citam cidade e devem ser recusadas; TYPE_CLASH não dispara em nenhuma consulta de referência) e as formas de RG13–RG18 montadas por código conferem com o oráculo. **607 testes passam no WSL (0 pulados).**

**Limites:** as correções saíram do conjunto RG, que **deixou de ser medida limpa**. Que as regras barram o que falhou está provado; que o LLM, depois do reparo, acerta, não foi remedido (saldo US$ 0,40). RT11 ("dia mais quente", esperado `needs_clarification`) pode passar a ser respondido com group_by de dia (D-56); não remedido.
P-39 Fallback do v4 também pode ser acionado mais vezes agora que há mais regras barrando a consulta do LLM; o compilador de reserva é restrito mas é código antigo.

## Análise crítica e endurecimento (23/10/2026)
Base: `docs/ANALISE_CRITICA.md` (IDs A-xx). Nenhum gasto com LLM. Todas as decisões abaixo têm teste.

| ID | Decisão | Motivo (medido) | Como reverter |
|---|---|---|---|
| D-59 | O endpoint do Ontop escuta só em `127.0.0.1` (`SERVER_ADDRESS=${ONTOP_BIND:-127.0.0.1}`); `stop` também mata o processo Java filho | Escutava em `*:8080` sem autenticação, contra o que o cabeçalho dizia (A-10, A-32) | `ONTOP_BIND` (não recomendado) |
| D-60 | Ontop sobe com `--dev` por padrão (`ONTOP_DEV=0` desliga); expõe `/ontop/restart` e actuator só no loopback | A checagem prévia e o SQL na procedência dependem de `/ontop/reformulate` (A-14) | `ONTOP_DEV=0`: o pipeline segue sem checagem do motor (status `unavailable`) |
| D-61 | Checagem prévia pelo motor (`OntopBackend.reformulate`, `Reformulation`; `orchestrator._engine_check`): `ENGINE_REJECTED` (dialeto inválido) e `EMPTY_BY_CONSTRUCTION` (reformulação vazia) antes de executar. Vale para o laço do LLM, o compilador de reserva e o ramo estruturado | Três incidentes de lacuna rdflib × Ontop (BIND, GROUP BY, relação invertida) tratados regra a regra (A-03, A-03b) | Não chamar `_engine_check` |
| D-62 | Contrato 0.2.0: `Provenance` ganha `generated_sql`, `engine`, `versions`, `prov_turtle` (PROV-O via rdflib, `pipeline/provenance.py`). Falha ao montar a procedência nunca derruba a resposta | §7.4 r.3 e §10/§12 do documento do professor (A-04, A-11) | Contrato 0.1.0 |
| D-63 | Ressalvas determinísticas na resposta (`pipeline/caveats.py`; anotação `met:answerCaveat` em `met-structure.ttl`): visibilidade censurada em 20 km, rajada, temperatura de pista, QNH; amostra pequena (n < 10% da mediana, ≥ 3 grupos); "contagens são de leituras, não boletins"; "dias em UTC−3" na descrição | 79,8% das leituras de visibilidade valem 2000 (dam); 19/178 estações com < 5.000 leituras; 32,3% extras no vento (A-17..A-20) | Esvaziar `answerCaveat` / não chamar `caveats` |
| D-64 | Trajetórias EvoOntology (`semantics/trajectories.py`, `--record-trajectories`) com os sinais do §13; `SemanticGrounder.uncovered` lista palavras sem Termo; `.evoontology/trajectories/` fora do git | O ciclo de evolução não tinha insumo (A-12). **Não há agente de evolução**: só o registro | Não passar `--record-trajectories` |
| D-65 | `eval/stats.py` (Wilson, McNemar exato) e relatórios com intervalo; `UNRESOLVED_PLACE` ganha lista explícita `PLACE_NAMES` (80 topônimos, sem "pará" por colidir com a preposição) e detecta lugar em minúsculas; "diariamente" vira pista de dia; suíte de robustez com 238 variações geradas | Placar sem incerteza (A-01); recall das regras de linguagem nunca medido (A-23, A-24); dois bugs meus achados pelos controles | Remover `PLACE_NAMES` |
| D-66 | Engenharia: `.gitattributes` (LF), `infra/setup_wsl.sh` com versões e SHA-256 fixados (confiança no primeiro uso), `infra/env.example.sh`, `infra/verify.sh`, README reescrito | CRLF quebrava `.sh`; ninguém montava o ambiente pelo README (A-30, A-33, A-34) | — |

**Pendências novas.** P-40: SHA-256 de `setup_wsl.sh` vêm do primeiro download, não de fonte independente. P-41: `--dev` expõe `/ontop/restart`; proteger se o endpoint deixar o loopback. P-42: ressalvas e trajetórias não foram medidas com LLM real. P-43: **o trabalho continua fora do git** (67 entradas pendentes); commit é decisão do Gabriel.

## Revisão independente do Codex e correções (23/10/2026)
Origem: `docs/AVALIACAO_CODEX.md` (C01–C20); quadro completo em `docs/ANALISE_CRITICA.md`, seção 9. Cada decisão tem teste em `tests/test_codex_review.py` (e nos arquivos citados).
Sem gasto com LLM. **Nenhuma foi remedida com o LLM real.**

| ID | Decisão | Motivo (reproduzido) | Como reverter |
|---|---|---|---|
| D-67 | L2 recusa `FILTER` com OR, NOT, EXISTS ou filtro dentro de OPTIONAL/MINUS (`FILTER_NOT_CONJUNCTIVE`) e agregação (AVG/SUM/MIN/MAX) cujo argumento não seja a variável de `qudt:numericValue` (`AGGREGATE_ARGUMENT`) | Um OR no período ampliava o período (média de 2019 virava 2016–2025); `AVG(?v*0)` devolvia 0 com n certo (C01) | Remover os dois laços em `_vocabulary` |
| D-68 | L4 confere, nos dois sentidos, o que a pergunta traz: mês nomeado (`PERIOD_MONTH_MISMATCH`, `PERIOD_OMITTED`), só o ano ⇒ ano inteiro (`PERIOD_PARTIAL_YEAR`, salvo semestre, trimestre, verão, "desde"…), limiar "acima/abaixo de N" ⇒ filtro (`FILTER_OMITTED`), parte do dia ⇒ `unsupported` (`DAYPART_UNSUPPORTED`) | Janeiro virava o ano; o ano virava janeiro; "acima de 30" sumia; "durante o dia" virava o dia inteiro (C02) | Remover o bloco "Restrições da pergunta" em `_ground_in_question` |
| D-69 | `ASK` é sempre `ANSWERED` (falso = "Não") e responde sem LLM; unidade estrangeira ao lado de número (K, °F, mph, Pa, mmHg…) é erro `WRONG_UNIT`, não aviso | ASK verdadeiro virava "Não há registros"; "20,4147 K" para °C passava (C03, C04) | `result_status` e `FOREIGN_UNIT_RE` |
| D-70 | `met:alsoDomain` na camada estrutural: `met:localDate` vale para Observation e WeatherReport | O mapeamento emite nos dois e a ontologia dizia só Observation, disjunta de WeatherReport: consulta válida levava `TYPE_CLASH` (C08) | Remover `alsoDomain` |
| D-71 | Piso absoluto de 30 leituras por resultado (exceto em contagem, onde n é a resposta); o texto das ressalvas diz que fuso e escala são hipóteses | O alerta relativo não via top-1/top-2 nem o caso "todos pequenos" (C10, C11) | `ABS_MIN_READINGS` |
| D-72 | Q2 (sensor travado) exige horas CONSECUTIVAS (1 h entre as leituras), não linhas vizinhas. **Banco reconstruído em 23/10/2026 (966 testes passaram no WSL): a quarentena Q2 continua com as mesmas 9 linhas e `obs_precip` com 7.500.529 linhas, ou seja, os 9 casos reais eram mesmo horas consecutivas (SBSC, 99,1 mm por 11 h) e a correção não mudou os dados; o defeito era só potencial** | 25 mm em 01/01/2019, 01/06/2019 e 01/01/2020 eram marcadas como travadas (C09) | Restaurar o trecho `stuck` anterior |
| D-73 | Procedência: contrato 0.2.1 (`executed_sparql`, `complete`); o SQL registrado é o da consulta ENVIADA (com LIMIT); as versões ganham impressão de mapeamento, limpeza, camada estrutural, alinhamento BFO e código; falha na procedência vira `PROVENANCE_INCOMPLETE`. As Evidências do EvoOntology ganham IRI PROV-O (campo `query`) e o grafo `evidence_prov()` | Procedência silenciosa e sem identidade dos dados (C12, C13). **A v0 já publicada em `.evoontology/` não foi regravada** (versões publicadas não se sobrescrevem) | Contrato 0.2.0 |
| D-74 | `eval.stats`: perguntas diferentes entre condições dão erro (ou `allow_partial` com a lista de excluídas); vírgula junta arquivos da mesma condição; "empate" vira "mesma contagem, sem prova de equivalência"; o 7/12 do split é rotulado "só status" (6/12 pela métrica de RF/RG) | O comando do README ignorava RG24 e dava 19/23 (C15, C06, C20) | — |
| D-75 | A checagem do motor continua consultiva, mas a indisponibilidade é dita (`ENGINE_CHECK_UNAVAILABLE`); `require_engine=True` recusa executar sem ela (`ENGINE_CHECK_REQUIRED`) | Verificação opcional e invisível (C14) | `require_engine=False` (padrão) |
| D-76 | O ledger RESERVA o custo máximo da chamada (entrada estimada + `max_tokens` × preço de saída) sob trava de arquivo antes de chamar, e ajusta ao custo real depois; chamada que falha depois de enviada fica registrada com o custo da entrada | Com 0,39 gastos e teto 0,40, uma chamada de 0,05 era aceita (total 0,44) (C16) | `LedgerLLM` anterior |
| D-77 | `cap_rows` aceita comentário depois de LIMIT; SHACL cobre as 8 unidades e os inteiros do mapeamento real; `infra/ontop.sh stop` mata só os filhos e a instalação deste Ontop (nunca `kill 0`); `setup_wsl.sh` confere o SHA do driver já instalado; testes de infra conferem SHA de 64 hex e o comportamento real do `stop` | C17, C18, C19 | — |

**Pendências novas.** P-44 (resolvida): rebuild feito, sem diferença nos dados. P-45: remedir com o LLM real as regras D-67 e D-68 (podem barrar perguntas boas). P-46: a v0 do EvoOntology só é regravada numa v1 (evolução). P-47: C05, C06 e C07 seguem abertos.

## Sonda pós-correções com LLM real (23/10/2026)
Autorização: o Gabriel respondeu "quero" à oferta de usar o saldo do ledger (US$ 0,40, dentro do teto já vigente; nenhum teto foi elevado). Gasto US$ 0,337; **saldo ≈ US$ 0,06**. Conjunto novo `eval/questions_real_probe.yaml` (RP01–RP08, oráculo `eval/oracle_real_probe.py`), escrito depois das correções e antes de rodar; 6 consultas de referência conferem com o oráculo. Prompt v6, uma execução. Relatório: `docs/RESULTADOS_LLM_REAL_v6_probe.md`.

**Resultado: 8/8 de status certo; 6/6 respondíveis corretas; 0 erradas, 0 falsa ausência, 0 abstenção indevida, 0 resposta a pergunta que devia ser recusada.**
- **Falsos positivos das regras novas (D-67/D-68): nenhum na primeira tentativa.** As 4 primeiras consultas certas do LLM (RP01, RP03, RP05, RP08) passaram sem reparo: mês nomeado, limiar "passou de 35", superlativo singular e ano inteiro não foram barrados.
- RP04 ("durante a noite"): uma rodada de reparo e depois `unsupported` pelo modelo, com a mensagem "restringe o período à noite, que não pode ser representado". RP06 (Campinas): `unsupported` direto.
- **Atenção: 2 dos 6 acertos vieram do compilador de reserva, não do LLM** (RP02 e RP07: o LLM errou o período ou usou um IRI inexistente e relações sem dados; as regras barraram, depois de 1 e 3 reparos, e a consulta foi montada por código). A ablação confirma: 2 primeiras tentativas teriam chegado vazias ao usuário sem as regras, e as duas foram barradas por L2.
- Limites: n = 8, um modelo, uma execução, mesmo autor das regras. Serve para achar um problema (não achou falso positivo), não mede taxa de acerto. P-45 fica **parcialmente** atendida: as regras de mês, semestre e limiar não barraram pergunta boa nestas 8, mas intervalos de meses ("entre março e maio") precisaram do compilador de reserva em 3 reparos.

## Avaliação independente e prompt v7 (compilar primeiro)

- **Medição** (`docs/RESULTADOS_INDEPENDENTE_v4_a.md`, 48/49, v4): pelo menos 3 respostas erradas entregues (E05 período parcial de mês, E14 limiar em km lido como metros, E23 `MAX` no lugar de `SUM`). Causa comum: o LLM escreveu a consulta livre e as regras tentaram adivinhar o erro depois.
- **D-78 (v7)**: a consulta é MONTADA por código sempre que há montagem determinística, incluindo agregação simples e contagem com limiar (`compile_structured(force=True)`); o LLM só escreve SPARQL onde não há montagem. Filtro numérico leva `unit`; o código converte para a unidade canônica da grandeza (`vocab.convert_filter_value`: km→m); unidade desconhecida = não monta (`FILTER_UNIT_UNKNOWN`), nunca chuta a escala. Nova regra L4 `FILTER_UNIT_MISMATCH` (a pergunta diz "N km" e o filtro não tem `unit:KiloM`). Reverter: `--prompts v6`.
- **Teste diferencial** (`tests/test_compiler_differential.py`): 40 especificações sorteadas (semente fixa) são montadas, executadas no Ontop e comparadas com pandas sobre a camada limpa: 40/40 iguais, sem LLM e sem custo. Garante o COMPILADOR; não garante que o LLM preencha a especificação certa.
- **Não medido**: o v7 com LLM real ainda não rodou (o conjunto independente já foi visto, então seria viciado nas 3 falhas; precisa de perguntas novas). Não corrigido: falsos positivos `PERIOD_PARTIAL_YEAR` em séries multi-ano (E22/E26), política de leituras duplicadas (E13/E19/E25), mediana e parte do dia.
- **D-79 (v7, dias com condição)**: novo campo `daily` na interpretação (`{"agg","op","value","unit"}` com `aggregation: "count"`): "em quantos DIAS a máxima passou de X" agrega cada dia e conta os dias; a consulta tem dois subselects (dias que cumprem = `value`, dias com dados = `n`) sem cálculo sobre o argumento de agregação (D-67 intacta). Regras novas: `DAILY_SHAPE`, `DAILY_NOT_IN_QUESTION`, `DAILY_OMITTED` ("quantos dias" + limiar sem `daily` é recusado, pois contar leituras dá outro número). Resolve a classe de E15.
- **Achado do teste diferencial**: limiar NEGATIVO (`FILTER(?v < -2)`) não era reconhecido por `query_facts` (o parser entrega `UnaryMinus`), então "abaixo de -2 °C" seria recusada com `FILTER_MISSING` (falha segura, mas pergunta legítima barrada). Corrigido; o sorteio agora cobre 56 especificações (inclui `daily`), 56/56 iguais ao pandas.
- **D-80 (E22/E26, falso positivo meu)**: "de 2016 a 2025" era lido como só o ano 2016 (`_YEAR` exige preposição antes do ano), e o período 2016–2025 da interpretação correta era recusado (`PERIOD_DATES_MISMATCH` e `PERIOD_PARTIAL_YEAR`). `question_years` agora também pega as duas pontas de "A a B", "entre A e B" e "A-B". Efeito colateral tratado: sem período é aceito quando o intervalo de anos da pergunta cobre toda a cobertura dos dados (RG14). O ano final menor que o pedido ("2016 a 2024" para "2016 a 2025") continua recusado. Medido só com testes, não com LLM.
- **D-81 (E18, E31)**: investigadas reproduzindo a interpretação com LLM roteirizado no grafo real. **E18** (contagem com limiar): o LLM escreveu a estação como `met:stationCode "SBLO"` e L3 recusou (`ENTITY_MISMATCH`, que só reconhece a estação pelo IRI); no v7 a consulta é montada por código com `st:SBLO` e o número bate com o pandas (sem mexer na regra: ela é conservadora de propósito). **E31** (comparação entre duas estações): `GROUP_BY_NOT_IN_QUESTION` recusava `group_by: ["station"]` porque o texto traz "SBRB ou SBPV" e não "por estação"; regra ajustada (duas ou mais estações NOMEADAS pedem um valor por estação). A pipeline devolve os dois totais; a DIFERENÇA não é calculada (a etapa de resposta não calcula): o usuário a lê dos dois números. `MISSING_COUNT` no SPARQL livre do LLM (colunas `?n1`/`?n2`) continua válido: é convenção de nome do D-10.

## Ontologia formal (BFO, DL/QL, raciocinador)

- **D-82**: alinhamento com a BFO 2020 axiomatizado (`ontology/met-bfo.ttl`: subClassOf/subPropertyOf para BFO e IAO, uma classe de qualidade por grandeza, `met:denotesQuality`). Imports fixados por SHA-256 em `ontology/imports/SOURCES.md` (BFO sem alteração; módulo IAO extraído com ROBOT). `met-external.ttl` declara os termos de SOSA/OWL-Time/QUDT/SKOS usados (o perfil DL exige). Mudança de modelagem registrada: `met:Site` passou de `site` para entidade material (porção de atmosfera). Todas as colocações são hipótese: `docs/DUVIDAS_ONTOLOGIA.md`. Reverter: git revert deste conjunto de commits.
- **D-83**: visões geradas de UMA fonte (`ontology/build_views.py`): DL completa (domínio alternativo `met:alsoDomain` vira `owl:unionOf`), QL (só axiomas QL; sem `xsd:date`, sem união) e `met-ontop.ttl` (QL sem domínios e imagens: com eles `?s a sosa:Sensor` estourava 60 s e a suíte ficou ~55% mais lenta). O Ontop passou a carregar `met-ontop.ttl`; consulta por categoria BFO (`?o a obo:BFO_0000015`) devolve as observações (antes, vazio). Resultados de consultas existentes inalterados (suíte e teste diferencial iguais).
- **D-84**: verificação formal em `tests/test_ontology_formal.py`: perfis DL/QL pelo ROBOT, consistência e satisfatibilidade pelo HermiT, 5 mutações que o raciocinador TEM de recusar (inclui o defeito C08), e conformância do que o mapeamento produz no grafo real (amostra + ontologia num arquivo só, com controle negativo). Lição: o ROBOT lê cada arquivo sozinho e propriedade não declarada nele vira anotação; sem o controle negativo o teste de conformância passava sem verificar nada.
- Verificado: WSL 93 + 974 passed (em duas partes, após o sistema encerrar uma rodada única por falta de memória), Windows 951 passed e 116 skipped.

## Decisões tomadas por delegação (sem confirmação do professor)

**Origem:** as quatro perguntas abaixo seriam levadas ao professor. O responsável pelo projeto (Gabriel) delegou a decisão a Claude ("você pode decidir o que achar mais coerente; apenas explicite isso nas decisões"), em 2026-10-23.
**Status de todas:** decisão de trabalho de Claude, **não** confirmada pelo professor nem por especialista. Cada uma é reversível e diz o que muda. Se o professor responder diferente, vale a resposta dele e estas entradas são substituídas.

- **D-85 Fuso (P-16): manter UTC−3 fixo (horário de Brasília) para todas as estações.** Por quê: é o padrão que os dados mostram (a hora 01:00 duplicada nas datas de início do horário de verão em todas as estações, DICIONARIO_DADOS §fuso) e um fuso por estação exigiria um cadastro de estações que a fonte não tem. O aviso já aparece ao usuário ("dias em UTC−3, hipótese ainda não confirmada para todas as estações", `pipeline/dialogue.py`). Efeito se estiver errado: o "dia" de estações do Amazonas e do Acre (UTC−4/−5) fica deslocado em algumas horas; contagens por dia perto da meia-noite mudam. Reverter: mudar `ingest/transform.py` e refazer a carga (~28 min).
- **D-86 Visibilidade (P-17): `visibpre` está em dezenas de metros; converte-se para metros (×10), e 2000 significa "20 km ou mais", tratado como 20.000 m.** Por quê: é o que o dicionário já assumia e coincide com o padrão METAR/ICAO (visibilidade de 10 km ou mais = 9999 m; aqui o teto do sistema de origem é 20 km). Cerca de 80% das leituras estão no teto, então médias e máximos ficam **truncados**, e a ressalva já acompanha toda resposta que usa visibilidade (`met:answerCaveat` em `PrevailingVisibility`). Decisão nova: **estatísticas de visibilidade são sobre o valor registrado, não sobre a visibilidade física**; não tentar "corrigir" o teto. Reverter: fator em `ingest/transform.py`.
- **D-87 Leituras duplicadas (mesma estação e hora com mais de um valor distinto): manter TODAS, cada uma com `met:multipleReadings true` e `seq` 0, 1…; não consolidar.** Por quê: a fonte não identifica o sensor nem a pista, então não há como saber qual valor é o "certo"; a média inventaria um valor que ninguém mediu, e "o último" é arbitrário. Consequência assumida: **uma contagem conta LEITURAS, não horas**: "quantas horas passou de 35 °C" pode contar a mesma hora duas vezes (medido: 772 pelo sistema contra 720 numa referência que consolida pela média, E13 da avaliação independente). Referências que consolidam serão classificadas como `cleaning_difference`, não como erro do sistema. **Correção (D-87 foi escrito com um erro meu):** a resposta JÁ avisa que contagens são de leituras (`pipeline/caveats.py`, desde antes); eu não conferi o código e afirmei que a dívida existia. O que faltava era a contagem de DIAS (`daily`), que herdava o aviso errado; agora tem o seu próprio (n = dias com dados). Em aberto: contar boletins distintos (`COUNT(DISTINCT ?report)`), a decidir depois de medir quantas horas têm duplicata por grandeza. Reverter: R4 em `ingest/transform.py` (consolidar) e refazer a carga.
- **D-88 Alinhamento com a BFO (P-07): seguir com o alinhamento PROVISÓRIO escrito por Claude, sem esperar revisão de especialista.** Por quê: o trabalho de consulta não depende da revisão (a BFO entra como hierarquia e disjunção; as consultas por categoria funcionam), e a verificação formal garante só **consistência interna** (HermiT) e **conformidade com o mapeamento**, não que a modelagem seja a melhor. Fica claro no arquivo (`met:alignmentStatus "provisional"`), em `docs/DUVIDAS_ONTOLOGIA.md` e aqui. Uma revisão futura troca só `ontology/met-bfo.ttl`; os testes formais dizem se a troca quebra algo. Riscos conhecidos: `met:Site` como porção de atmosfera, observação como processo, qualidades só como classes.

Mantém-se a pergunta ao professor sobre **perguntas reais de usuários da área** (10 a 20): é a única forma de ter um conjunto de avaliação que o autor das regras não escreveu.

## Ponto de entrada, porta com raciocinador e ciclo de evolução (sem verba)

- **D-89 Linha de comando** (`python -m kgqa`): padrão `v7`, confirmação da interpretação quando há suposição (só com terminal), `--json` (contrato 0.2.1), `--show-query` (SPARQL e procedência), teto por sessão (`--budget`, padrão US$ 0,10) além do ledger. Falha de início diz só o tipo do erro e o que conferir (Ontop, kgqa.env), sem detalhe interno. Testada com LLM roteirizado e, no grafo real, com uma contagem conferida contra o pandas. **O padrão `v7` ainda não foi medido com LLM real**; está dito no README.
- **D-90 Porta de validação com raciocinador** (`semantics/gate.py`): além de IRI/BFO/agregação/unidade, confere (a) que a unidade citada por uma Restrição é aceita pelas formas SHACL e (b) que as Relações `has_domain`/`has_range` do Candidate não tornam a ontologia inconsistente nem deixam classe insatisfatível (HermiT sobre a visão completa + axiomas, e opcionalmente sobre a amostra do grafo real). Sem ROBOT/Java o passo vira `unavailable` e só bloqueia no modo estrito (`require_reasoner=True`, o da evolução). Mutação coberta: domínio de `met:inReport` na estação (contradiz a BFO). **Limite:** relações de outros tipos (`observed_as`) não são axiomas OWL e não passam pelo raciocinador; Restrição em texto livre continua sem checagem por regra.
- **D-91 Camada publicada em dia**: a porta recusou todo Candidate derivado da v0 porque `term.Site` ainda dizia `site` (a v0 foi gerada antes de D-82 mudar a colocação). Conserto: `semantics.build --rebuild` grava a próxima versão se a ativa difere do que a ontologia produz (`ontology_v1`, versão anterior mantida) e um teste (`test_the_published_active_layer_is_not_stale_against_the_ontology`) impede que a camada commitada volte a ficar defasada. Isto também fecha a pendência de regravar a v0 com as Evidências PROV-O.
- **D-92 Ciclo de evolução** (`docs/CICLO_EVOLUCAO.md`): minerador DETERMINÍSTICO (não é um LLM; é dito), Candidate = um sinônimo com Evidência ligada às trajetórias, porta, avaliação pareada Parent × Candidate com o **mesmo avaliador e os mesmos casos** (reconhecimento de grandeza contra o gabarito da consulta de referência; validação congelada disjunta da construção + regressão), aceite só com melhora estrita e sem regressão, e a máquina de estados do núcleo (orçamento de rodadas congelado, só Accept publica). O que alteraria a camada formal ou a ferramenta vira **proposta** (`proposals/pending.json`), nunca remendo. Proteções do minerador contra falso sinônimo: palavras que a pipeline já interpreta, fragmentos de nomes de Termos e palavras que aparecem em perguntas de outra grandeza. **Limite central:** o avaliador mede reconhecimento de sinônimos, não resposta correta; o efeito ponta a ponta exige LLM (`docs/PLANO_ABLACAO.md`). As trajetórias usadas são de SEMENTE a partir do gabarito (`gold_seed`), não de uso real.
  Resultado de uma execução (cópia do workspace): "choveu" → precipitação, validação 0,864 → 0,932, sem regressão, aceito como `ontology_v2` **só na cópia** (publicar é decisão do responsável).

## Arquitetura v8: interpretação ancorada em trechos (plano aprovado em 2026-10-27)

- **D-93 Leitura determinística da pergunta** (`pipeline/spans.py`): datas (numéricas e por extenso), meses, anos, intervalos, trimestre, semestre,
  estação do ano, parte do dia, dias da semana, horário, número com unidade e unidade citada sem número são lidos por código, com trecho e posição.
  Por quê: no `novo_a`, "dia 15 de fevereiro de 2024" virou fevereiro inteiro porque a regra de conferência só conhecia `dd/mm/aaaa` (E07, E11, E43);
  uma gramática fechada de calendário em português é testável contra todas as perguntas, e a regra por forma de escrever não acaba nunca.
  Convenções declaradas: estações do ano **austrais e meteorológicas** (verão de 2022 = dez/2021 a fev/2022; outono mar–mai; inverno jun–ago;
  primavera set–nov); partes do dia madrugada [0,6), manhã [6,12), tarde [12,18), noite [18,24), "durante o dia" [6,18); "fim de semana" = sábado
  e domingo; mês sem ano é lido mas não vira janela (quem concilia pede o ano). Efeito se estiverem erradas: a janela muda, e a resposta diz qual usou.
- **D-94 Interpretação ancorada em trechos (prompt `v8`, `pipeline/reconcile.py`)**: o LLM decide só o sentido (grandeza, estação, cálculo, forma
  do resultado) e cita o trecho literal que justifica cada decisão; não escreve datas, números nem unidades. Tempo vem só da leitura (D-93); o valor
  e a unidade de um limiar vêm do trecho citado; SPARQL só pelo compilador (o que ele não monta é `unsupported`). A conciliação confere por
  MECANISMO, não por frase: trecho existe e corresponde; número da pergunta sem dono; unidade citada x dimensão da grandeza ("minutos de chuva"
  não é precipitação em mm); medida x contagem ("quantos mm" não é contar leituras). As regras de `_ground_in_question` continuam valendo para v4–v7.
- **D-95 O que a contagem conta é explícito** (`count_of`): "quantas horas" = horas locais DISTINTAS (uma hora com duas leituras conta uma vez);
  "quantos dias" = dias (exige a estatística do dia); "quantos boletins" = boletins distintos; "vezes/leituras/registros" = leituras. Sempre dito
  na resposta. Antes o sistema contava leituras quando a pergunta dizia horas (E13, E17 do novo_a).
- **D-96 "Horas/dias com chuva" = precipitação > 0** (no dia: soma do dia > 0); "sem chuva" = 0. Por regra, dito na resposta (E15 do novo_a: o v4–v7
  perdia a condição e contava todas as leituras do ano).
- **D-97 Esclarecer em vez de chutar** (v8): sem cálculo pedido (e sem forma de resultado) -> pergunta qual cálculo; sem estação, sem período e sem
  forma de resultado nem "toda a rede" -> pergunta o alcance; mês sem ano e período vago ("toda a semana") -> pergunta as datas; dois períodos
  disjuntos (comparação) -> `unsupported` dito. (E41, E42 do novo_a.)
- **D-98 Hora local no compilador**: o instante do grafo está em UTC; a hora local h é a UTC (h+3) mod 24 (D-85) e o dia da semana sai da lista de
  datas locais da janela. Horas distintas = `COUNT(DISTINCT CONCAT(STR(?d), "T", STR(HOURS(?t))))`: o Ontop 5.5 recusa `SELECT DISTINCT`/`GROUP BY`
  sobre `HOURS()` num subselect (erro interno "non-grouping bindings"), conferido no grafo real. `tests/test_v8_real.py`: 11 casos do novo_a no
  grafo real, sem LLM, iguais ao oráculo pandas ou à diferença de limpeza já julgada (linhas idênticas repetidas no CSV).

## MVP `metqa/` (arquitetura aprovada em 2026-10-27, `docs/ARQUITETURA_MVP.md`)

- **D-99 Uma pipeline linear em vez de versões por flag**: o MVP (`metqa/`) tem UM caminho (leitor → intérprete → conciliação e verificação →
  planejador → compilador → executor → verificação → texto → trilha), portas para LLM, fonte SPARQL e léxico, e configuração única
  (`metqa/app/settings.py`). Os módulos provados de `pipeline/`, `kgqa/` e `semantics/` são reaproveitados por importação (migração
  estranguladora); `pipeline/orchestrator.py` (v1–v8) fica para as comparações históricas. Por quê: oito versões como flags numa função de
  ~350 linhas e duas formas paralelas de conferir o LLM eram complexidade acidental; os erros medidos eram de estrutura, não de modelo.
- **D-100 A EvoOntology no caminho de toda pergunta, como léxico**: o intérprete recebe um cardápio do Catálogo com o destaque do léxico
  (camada publicada); palavra sem cobertura vai para a trilha. Antes ela só entrava pelo prompt v5. `--lexicon ontology` desliga a camada
  (ablação RQ1/RQ3 do documento).
- **D-101 Texto da resposta determinístico**: montado das linhas verificadas (números em português, unidade, estação, período, "como
  entendi", ressalvas). Não há etapa de LLM para redigir: não há número inventado nem trocado de estação, e custa zero.
- **D-102 Comparação de dois períodos** ("mais quente em janeiro de 2016 ou em janeiro de 2025?") = duas subconsultas de mesma forma,
  combinadas em código; mais de dois períodos, ou comparação de agrupamentos, é `unsupported` dito. Várias estações citadas sem pedir
  agrupamento = um valor por estação, dito. Valor num instante ("às 14h") = a leitura daquele instante (UTC no grafo).
