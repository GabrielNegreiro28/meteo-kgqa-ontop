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
- P-16 Fuso: dados parecem estar em UTC−3 fixo para todas as estações, com artefato nas datas de início do
  horário de verão (2016-10-16, 2017-10-15, 2018-11-04). D-04 continua válida se confirmado.
- P-17 Unidades a confirmar: visibilidade e altura de nuvem em dezenas de metros; vento em kt; direção em dezenas de graus.
- P-18 Falta cadastro de estações (nome, local, coordenadas): necessário para perguntas como "em Manaus".

## Após o incremento 2 (15/10/2026)
- P-19 O Ontop avisa que `rdfs:range xsd:boolean` está fora do OWL 2 QL (ignorado). Resto da ontologia dentro do perfil.
- P-20 Exportar o mapeamento para R2RML (`ontop mapping to-r2rml`), formato pedido pela arquitetura do professor.
- P-21 Pasta `METEOROLOGIA\_transferencia` no OneDrive do Gabriel (~480 MB de cópias compactadas): pode ser apagada.
- P-22 Próximo passo do módulo: interpretação + recuperação de contexto (léxico de rótulos, fragmento da T-Box)
  e gerador com LLM, avaliado com `eval/questions_real.yaml` (dev/test separados).
