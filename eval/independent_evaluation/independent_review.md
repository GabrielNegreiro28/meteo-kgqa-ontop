# Conjunto de avaliação independente

Foram geradas exatamente 50 perguntas. O arquivo bruto foi preservado sem edição e salvo em `eval/questions_independent_raw.yaml` antes da execução dos oracles. Após revisão e validação, foram retidas 49 perguntas. Não houve reposição de perguntas removidas.

## Proveniência e separação

A geração ocorreu em agente com contexto novo (`fork_turns=none`), recebendo somente o prompt do usuário, a lista agregada de estações de `pressao.csv`, o diretório dos CSV originais e instruções para salvar o YAML. O gerador não recebeu regras do pipeline, DECISOES.md, conjuntos anteriores ou a auditoria deste chat. A listagem foi calculada em blocos, com o mesmo min/max/count do comando solicitado, para limitar memória. Foram encontrados 178 identificadores.

Houve uma interrupção por limite de uso durante a geração. O mesmo agente retomou seu próprio script e concluiu o arquivo; não recebeu resultados da validação nem feedback para corrigir perguntas ou oracles. A preferência por um modelo diferente do pipeline não foi comprovada. Independência de contexto não equivale a independência de modelo. O revisor conhece a auditoria anterior, mas as decisões de inclusão foram baseadas no prompt, nos CSV e na execução dos oracles, sem medir o pipeline.

## Validação

Os 40 oracles foram executados com os códigos preservados, em processos Python separados, com limite de 120 segundos por execução. Os seis primeiros foram concluídos sequencialmente; a execução seguinte foi interrompida para retomar os restantes com até três processos simultâneos. Resultados concluídos foram preservados. Isolamento de processo não constitui sandbox de segurança: antes da execução, foram inspecionados imports e operações dos códigos. O wrapper restringiu `pd.read_csv` aos seis arquivos originais e às colunas permitidas.

Resultado das execuções: {'ok': 40, 'not_applicable': 10}. Os dez casos não respondíveis não possuem oracle. Foram verificados formato YAML, IDs E01–E50, distribuição, perguntas textualmente distintas, sintaxe Python, lista não vazia de tuplas e ausência de células nulas/não finitas. Uma checagem adicional de cobertura dos dados detecta recortes sem observações, que uma contagem poderia transformar incorretamente em zero.

Os hashes SHA256 dos seis CSV, versões de Python/pandas/PyYAML e tamanhos dos arquivos estão em `source_manifest.json`. Os resultados calculados e tempos por pergunta estão em `independent_validation.json`; a cobertura está em `input_coverage.json`. Nenhum código, pergunta ou rótulo do arquivo bruto foi corrigido após a geração.

## Remoções

- **E20**: Não há nenhuma linha de nuvem.csv para SBPA entre 2024-07-01 inclusive e 2024-08-01 exclusivo. O oracle de contagem devolve zero mesmo quando não existem observações; isso não estabelece uma resposta meteorológica observada. Exclusão por ausência de dados, sem editar pergunta, expected_behavior ou código.

## Distribuição

| Categoria | Bruto | Congelado |
|---|---:|---:|
| simples | 12 | 12 |
| condicao | 8 | 7 |
| serie_ranking | 8 | 8 |
| comparacao | 4 | 4 |
| impossivel | 6 | 6 |
| ambigua | 4 | 4 |
| informal | 4 | 4 |
| tempo | 4 | 4 |

## Congelamento

- SHA256 bruto: `b750e75fc8f1c2314894dac6721369d85f993b7ff716bfb7bde695737e15abae`
- SHA256 congelado: `0d05a4a32f2197352a750d04af8bad72410c582519bbf9429662af5664d2691b`
- Nenhuma execução do pipeline foi realizada nesta tarefa, inclusive antes do congelamento.
- `independent_manifest.json` registra os hashes dos artefatos. Os blocos YAML das perguntas retidas são preservados byte a byte; somente os blocos removidos são omitidos.

## Uso e limites

Os oracles são referências geradas, não uma verdade infalível. As suposições incluem limites físicos, consolidação de duplicatas, escolha de cabeceiras/camadas, uso de hora cheia para certas contagens e chuvas, e tratamento do teto de visibilidade. Essas escolhas devem acompanhar a interpretação dos resultados. O conjunto não comprova completude temporal nem foi calibrado contra as respostas do sistema.

Na medição futura, toda divergência entre pipeline e oracle deve ir a julgamento humano, classificando erro do pipeline, erro do oracle ou diferença de limpeza/interpretação. Não ajuste o conjunto congelado a partir dos resultados do pipeline; qualquer revisão deve formar nova versão com novo hash.

Para reproduzir a execução, copie o conteúdo deste pacote para uma pasta de trabalho e execute `python validate_independent.py`, mantendo os CSV nos caminhos registrados. Para repetir a checagem de cobertura, execute `python check_coverage.py`. O validador cria arquivos de progresso e resultados na pasta de execução; os arquivos entregues são o registro desta rodada.
