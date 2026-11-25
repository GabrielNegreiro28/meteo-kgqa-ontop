# Arquitetura implementada — contrato 0.4.0

Atualização de 03/11/2026, posterior à revisão `../ANALISE_PROJETO_20261103.md`.
Este documento descreve o estado implementado. `PLANO_ARQUITETURA_FINAL.md` e os relatórios `novo_a/b/c`
são registros históricos; seus placares não validam esta versão.

## Decisões

Preservados Python, PostgreSQL, Ontop, catálogo ontológico, compilador SPARQL, verificadores e EvoOntology.
O módulo continua atendendo uma fonte meteorológica. Não inclui roteador de fontes, documentos, MongoDB ou interface gráfica.

1. O LLM interpreta; código valida, planeja, compila e apresenta. A interpretação precisa de evidência de grandeza,
   estação, período e cálculo, além dos filtros, forma e unidade solicitados. Consultas instantâneas não precisam inventar agregação.
   Ambas as leituras são verificadas. Estações escolhidas devem estar ligadas ao trecho de evidência por identificador ou alias do catálogo.
2. Ausência de evidência ou divergência pede esclarecimento. Selecionar todas as estações ou todo o histórico exige evidência explícita.
   A verificação de trechos reduz erros detectáveis, mas não prova a interpretação de linguagem natural. Continua possível o modelo citar
   um trecho verdadeiro e atribuir-lhe significado inadequado; confirmação e avaliação independente continuam necessárias.
3. Releitura temporal compara a união dos intervalos de datas (janelas contíguas fundidas: "cada mês de 2023" = 2023) e o instante;
   horas e dias da semana são comparados quando a releitura os encontra no trecho (null = o trecho não os carrega). Indisponibilidade do verificador é falha técnica,
   sem execução de consulta. Reparos estruturais permanecem limitados a uma tentativa por leitura.
4. A chave de confirmação é gerada quando `METQA_SECRET` não está definida. Tokens vinculam pergunta, interpretação,
   catálogo, versão do léxico e snapshot declarado. Configure a mesma chave nos processos que precisem compartilhar tokens.
5. Todas as partes são compiláveis antes da primeira execução. Números não finitos são recusados. Precisão decimal e IRIs completos
   são preservados no resultado tipado; o texto arredonda somente na apresentação.
6. Comparações informam todos os máximos empatados entre as partes consultadas. Parte vazia ou resultado truncado impede declarar
   vencedor. Ranking consulta uma linha adicional; empate nessa fronteira indica outros empatados, sem afirmar sua quantidade total.
7. Confirmação do usuário valida a interpretação, não a medição nem a política de limpeza. Exemplos registram esse escopo.
   Avaliação não alimenta a memória de exemplos nem promove automaticamente candidatos. A porta formal e Parent/Candidate são preservados.

## Contrato público

`MetQA.ask`, `capabilities()` e os status existentes foram mantidos.

| Campo | Significado em 0.4.0 |
|---|---|
| `results` | Bindings SPARQL brutos, sem conversão para a unidade solicitada; comparações têm `parts` |
| `units` | Unidades canônicas do resultado bruto da primeira parte; unidades de todas as partes estão em `result_shape` |
| `presentation` | Linhas com valores convertidos, unidades, precisão de exibição e truncamento, por parte; decimais são strings |
| `interpretations` | Todas as partes efetivamente planejadas, com consulta, evidências, hipóteses e indicação de confirmação |
| `interpretation` | Compatibilidade: apenas a primeira parte; novos consumidores devem usar `interpretations` |
| `result_shape` | Papel das colunas, unidades e cobertura observada por estação/grandeza |
| `provenance.versions.snapshot` | Manifesto declarado na configuração, ou `null` quando não configurado |

Exemplo: visibilidade bruta `18166.8` tem unidade `M`; apresentação `18.1668` tem unidade `KiloM`;
o texto exibe `18,17 km`. Nenhum consumidor deve aplicar `units` aos valores de `presentation`.

## Manifesto e cobertura

Após a limpeza e com o DuckDB fechado:

```bash
python -m ingest.manifest --raw ../METEOROLOGIA --database /caminho/met.duckdb --out snapshot.json
export METQA_SNAPSHOT=/caminho/snapshot.json
```

O comando não reprocessa dados: calcula hashes dos CSVs, artefatos de ingestão, catálogo, ontologias, mapeamento e banco limpo.
Extrai início, fim e contagem por estação/grandeza. Alternativamente, `--coverage cobertura.json` usa um perfil revisado fornecido.
O arquivo de saída não é sobrescrito. O carregamento verifica sua integridade; `verify_database` confere a base contra o hash.
Início/fim não comprovam ausência de lacunas: `coverage_complete` permanece falso. Ausência de manifesto não é completude implícita.

O manifesto declara a carga ligada ao endpoint. O operador precisa garantir que o PostgreSQL servido pelo Ontop foi exportado desse
mesmo snapshot e permaneça congelado durante o estudo; o endpoint atual não fornece um hash verificável do banco remoto.
Deduplicação e descarte de picos continuam hipóteses sujeitas à revisão meteorológica. O fuso (antes UTC−3 fixo) e as unidades foram
conferidos contra METAR em 25/11/2026 (`data/VERIFICACAO_PREMISSAS.md`, D-115).

## Avaliação independente

O comparador preserva colunas, linhas, identificadores e multiplicidade. Referência ausente é erro de avaliação; referência vazia
é diferente. Inteiros são exatos; demais números usam tolerância absoluta `0.01` ou relativa `0.001`, a maior delas.
Textos e identificadores são exatos. Não extrai números de siglas ou datas para tentar encaixar esquemas diferentes.

`eval.adjudicate` usa comparação estrita por padrão. `--historical` permite inspecionar exceções de adjudicação antigas;
não é uma validação científica nova. Os relatórios anteriores não foram sobrescritos.

Há dois caminhos de validação independentes:

- Ingestão: âncoras de dados brutos, reconciliação, quarentena e política de limpeza nos testes existentes.
- Consulta: SQL escrito e revisado independentemente do compilador sobre o snapshot limpo. `eval.clean_reference`
  executa somente um SELECT por parte, em DuckDB somente leitura e sem acesso externo, e conserva tipos e nomes das colunas.

Exemplo mínimo de `referencias.json`:

```json
{"cases": [{"id": "X", "expected_status": "answered", "parts": [{"label": "",
  "sql": "SELECT avg(value) AS value, count(*) AS n FROM clean.obs_air_temp WHERE sigla='SBGL' AND local_date=DATE '2020-01-01'",
  "units": {"value": "http://qudt.org/vocab/unit/DEG_C"}}]}]}
```

```bash
python -m eval.clean_reference --database /caminho/met.duckdb --snapshot snapshot.json --spec referencias.json --out referencias_congeladas.json
```

As colunas da referência determinam a projeção explicitamente; a ordem dos bindings não determina a correspondência.
Para estações, use IRIs completos na referência. Rótulos das partes devem corresponder aos rótulos públicos, e unidades devem ser canônicas.
A ausência de resultado pode ser uma tabela vazia ou um agregado com base zero: o revisor deve registrar o status e as linhas esperados.

## Estudo preparado, ainda não executado

`eval.study` prepara ou executa 120 perguntas inéditas: 80 respondíveis, 20 ambíguas e 20 fora das capacidades.
O JSON de entrada contém `reviewed_by` e `questions` (campos `id`, `question`, `expected_behavior`).
Referências e política meteorológica precisam ser revisadas antes de congelar esse material. Perguntas usadas para desenvolvimento
não devem entrar no teste final. Há verificação de duplicatas e das perguntas já presentes nos conjuntos de `eval/`.

```bash
python -m eval.study --questions estudo_revisado.json --references referencias_congeladas.json --snapshot snapshot.json --out eval/reports/estudo_planejado
```

Sem `--run`, somente grava agenda e hashes, sem iniciar cliente LLM. Para executar, use outro diretório de saída e acrescente
`--run --budget VALOR_AUTORIZADO`. O estudo compartilha o cliente e o controle de gasto entre as condições e interrompe ao esgotar o orçamento.
O orçamento estimado é verificado antes das chamadas; chamadas já em andamento podem terminar depois de atingir o teto.

As cinco condições são completa, uma leitura, sem conservação/releitura, léxico formal e sem rótulos BFO no contexto.
São três repetições, com condições intercaladas por pergunta e ordem pseudoaleatória reproduzível. Não há aprendizagem durante o estudo.
O contexto semântico do EvoOntology agora chega ao intérprete; a ablação BFO remove somente o campo de categoria,
preservando definições, dados, unidades e restrições de domínio. Não remove a modelagem BFO do banco nem a validação formal de publicação.
Portanto, mede a contribuição desse contexto para as perguntas, não a contribuição de toda a ontologia.

São gravados resposta completa, trilha, versões, status, custo e latência por execução. O resumo apresenta métricas por comportamento
e por repetição, intervalo de Wilson e McNemar pareado. Repetições não são somadas como perguntas independentes.
Rodadas incompletas nunca passam nos critérios: 120 casos, nenhum erro entregue, todos os casos de comportamento corretos,
ao menos 72/80 respondíveis corretos e limite superior de Wilson para erro abaixo de 4%.

## Verificação e operação

```bash
python -m pytest -q --tb=short -rs
```

Testes locais cobrem regressões dos quatro defeitos originais, contrato, decimais, evidência, confirmação, manifesto,
referências limpas e planejamento do estudo. Testes com `needs_ontop`, `needs_duck` e `needs_robot` precisam do ambiente WSL.
O relatório de execução desta entrega está em `VALIDACAO_0_4.md`.

Para voltar à implementação anterior, restaure código e artefatos semânticos compatíveis do commit `ed29037` em outro checkout.
Não sobrescreva dados brutos, referências congeladas ou relatórios para simular resultados da versão anterior.
