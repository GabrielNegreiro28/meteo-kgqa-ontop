# Resultados da injeção de falhas

Gerado por `python -m eval.safety_experiment` (determinístico, sem LLM, sobre o grafo sintético).
Base: 9 consultas de referência corretas × 23 operadores de falha; **128 mutantes** aplicáveis. Verdade de cada mutante: executado e comparado ao oráculo independente.

Legenda do desfecho sem validação: **perigosa** (escrita/rede chegaria ao armazenamento), **sintaxe** (erro explícito), **errada em silêncio** (executa e devolve valor diferente do oráculo), **vazia** (executa e devolve 'sem registros', exposta honestamente), **equivalente** (mesmo resultado do oráculo).

## 0. Controle: consultas corretas barradas indevidamente

9/9 consultas de referência passam sem nenhum achado.

## 1. Mutantes de consulta (etapa 2): primeira camada que barra

| Falha injetada | n | L1 | L2 | L3 | passou | do que passou: errada em silêncio / vazia / equivalente |
|---|---:|---:|---:|---:|---:|---|
| IRI de propriedade inventado | 9 | 0 | 9 | 0 | 0 | 0 / 0 / 0 |
| IRI de classe inventado | 9 | 0 | 9 | 0 | 0 | 0 / 0 / 0 |
| propriedade válida, mas errada | 9 | 0 | 2 | 7 | 0 | 0 / 0 / 0 |
| estação inexistente | 4 | 0 | 4 | 0 | 0 | 0 / 0 / 0 |
| estação válida, mas errada | 4 | 0 | 0 | 4 | 0 | 0 / 0 / 0 |
| rótulo de estação inventado | 1 | 0 | 1 | 0 | 0 | 0 / 0 / 0 |
| rótulo de estação válido, mas de outra estação | 1 | 0 | 0 | 1 | 0 | 0 / 0 / 0 |
| operador de fronteira trocado (> por >=) | 6 | 0 | 0 | 6 | 0 | 0 / 0 / 0 |
| período deslocado em 1 dia | 5 | 0 | 0 | 5 | 0 | 0 / 0 / 0 |
| filtro omitido | 6 | 0 | 0 | 5 | 1 | 0 / 0 / 1 |
| filtro extra não pedido | 9 | 0 | 0 | 9 | 0 | 0 / 0 / 0 |
| agregação errada (AVG/MAX/SUM) | 8 | 0 | 0 | 8 | 0 | 0 / 0 / 0 |
| contagem ?n omitida | 8 | 0 | 0 | 8 | 0 | 0 / 0 / 0 |
| previsão vaza para observação | 1 | 0 | 0 | 1 | 0 | 0 / 0 / 0 |
| tipa por superclasse sem inferência (sosa:Observation) | 7 | 0 | 7 | 0 | 0 | 0 / 0 / 0 |
| intervalo (precipitação) consultado como instante | 2 | 0 | 2 | 0 | 0 | 0 / 0 / 0 |
| fim do intervalo estrito (< em vez de <=) | 2 | 0 | 0 | 2 | 0 | 0 / 0 / 0 |
| relação sem dados no grafo (met:inReport) | 8 | 0 | 8 | 0 | 0 | 0 / 0 / 0 |
| função fora do SPARQL 1.1 (xsd:date) | 1 | 0 | 1 | 0 | 0 | 0 / 0 / 0 |
| unidade comparada com texto | 1 | 0 | 1 | 0 | 0 | 0 / 0 / 0 |
| escrita (DELETE) | 9 | 9 | 0 | 0 | 0 | 0 / 0 / 0 |
| SERVICE (rede externa) | 9 | 9 | 0 | 0 | 0 | 0 / 0 / 0 |
| saída cortada (consulta truncada) | 9 | 9 | 0 | 0 | 0 | 0 / 0 / 0 |

## 2. Ablação das camadas

Mutantes que chegariam ao usuário/armazenamento conforme as camadas ligadas.

| Configuração | perigosa chega ao armazenamento | errada em silêncio | vazia (exposta como sem registros) | barrada com resultado coincidente |
|---|---:|---:|---:|---:|
| sem validação | 18 | 36 | 45 | 0 |
| L1 sintaxe+política | 0 | 36 | 45 | 0 |
| L1+L2 vocabulário | 0 | 36 | 6 | 5 |
| L1+L2+L3 conformidade | 0 | 0 | 0 | 19 |

### Falhas silenciosas que NENHUMA camada barrou (risco residual)

- (nenhuma neste conjunto de mutantes)

### Barrados apesar de o resultado coincidir com o oráculo

A consulta diverge da interpretação (logo, barrar está certo), mas por coincidência dos dados o resultado seria igual.
- `D03` — filtro extra não pedido: FILTER_UNEXPECTED
- `D04` — filtro extra não pedido: FILTER_UNEXPECTED
- `T03` — operador de fronteira trocado (> por >=): PERIOD_MISMATCH
- `T03` — período deslocado em 1 dia: PERIOD_MISMATCH
- `T03` — contagem ?n omitida: MISSING_COUNT
- `T04` — filtro extra não pedido: FILTER_UNEXPECTED
- `T06` — filtro omitido: PERIOD_MISMATCH
- `T07` — filtro extra não pedido: FILTER_UNEXPECTED
- `T07` — agregação errada (AVG/MAX/SUM): AGGREGATION_MISMATCH
- `T07` — contagem ?n omitida: MISSING_COUNT
- `T08` — IRI de propriedade inventado: UNKNOWN_IRI, PROPERTY_MISMATCH
- `T08` — IRI de classe inventado: UNKNOWN_IRI, CLASS_WITHOUT_DIRECT_INSTANCES
- `T08` — estação inexistente: UNKNOWN_IRI, ENTITY_MISMATCH
- `T08` — filtro extra não pedido: FILTER_UNEXPECTED
- `T08` — agregação errada (AVG/MAX/SUM): AGGREGATION_MISMATCH
- `T08` — tipa por superclasse sem inferência (sosa:Observation): CLASS_WITHOUT_DIRECT_INSTANCES
- `T08` — relação sem dados no grafo (met:inReport): RELATION_WITHOUT_DATA
- `T11` — filtro omitido: PERIOD_MISMATCH
- `T11` — filtro extra não pedido: FILTER_UNEXPECTED

## 3. Mutantes de texto (etapa 3): checagem de números (L5)

| Falha injetada no texto | n | detectadas | taxa |
|---|---:|---:|---:|
| dígito do valor alterado | 16 | 16 | 100% |
| número inventado (não está nos resultados) | 17 | 17 | 100% |
| valores trocados entre entidades | 6 | 6 | 100% |
| unidade omitida | 14 | 14 | 100% |
| truncamento não informado | 8 | 8 | 100% |
| 'sem dados' apresentado como zero | 1 | 1 | 100% |
| linha dos resultados omitida da resposta | 6 | 6 | 100% |
| 'não há registros' onde há dados | 16 | 16 | 100% |

## 3b. Interpretação corrompida de modo coerente (etapa 1): fundamentação na pergunta (L4)

A consulta seguiria a interpretação errada, então L3 (consulta = interpretação) não vê nada; sem L4 a taxa de detecção é **0%** (limite documentado na versão anterior). Aqui a interpretação é conferida contra o texto da pergunta.

| Falha injetada na interpretação | n | barradas por L4 | taxa |
|---|---:|---:|---:|
| estação citada na pergunta omitida | 5 | 5 | 100% |
| estação não citada acrescentada | 9 | 9 | 100% |
| agregação trocada | 8 | 7 | 88% |
| agregação omitida | 8 | 5 | 62% |
| período deslocado em 1 dia | 5 | 4 | 80% |
| período omitido | 5 | 4 | 80% |
| período inventado | 4 | 3 | 75% |
| valor do filtro alterado | 2 | 2 | 100% |
| grandeza trocada | 9 | 8 | 89% |
| **total** | **55** | **47** | **85%** |

Não barradas (equivalentes legítimos ou lacuna das regras):

- `D05` — agregação trocada
- `D05` — agregação omitida
- `D05` — grandeza trocada
- `T03` — agregação omitida
- `T04` — agregação omitida
- `T07` — período inventado
- `T11` — período deslocado em 1 dia
- `T11` — período omitido

## 4. Detalhe por mutante

| Caso | Falha | Códigos | Verdade sem validação |
|---|---|---|---|
| D03 | IRI de propriedade inventado | UNKNOWN_IRI, PROPERTY_MISMATCH | surfaced_empty |
| D03 | IRI de classe inventado | UNKNOWN_IRI, CLASS_WITHOUT_DIRECT_INSTANCES | surfaced_empty |
| D03 | propriedade válida, mas errada | PROPERTY_MISMATCH | surfaced_empty |
| D03 | operador de fronteira trocado (> por >=) | FILTER_OPERATOR_MISMATCH, FILTER_UNEXPECTED | silent_wrong |
| D03 | filtro omitido | FILTER_MISSING | silent_wrong |
| D03 | filtro extra não pedido | FILTER_UNEXPECTED | harmless |
| D03 | tipa por superclasse sem inferência (sosa:Observation) | CLASS_WITHOUT_DIRECT_INSTANCES | surfaced_empty |
| D03 | unidade comparada com texto | RESOURCE_COMPARED_TO_STRING | surfaced_empty |
| D03 | escrita (DELETE) | POLICY_VIOLATION | dangerous |
| D03 | SERVICE (rede externa) | POLICY_VIOLATION | dangerous |
| D03 | saída cortada (consulta truncada) | SYNTAX_ERROR | blocked_syntax |
| D04 | IRI de propriedade inventado | UNKNOWN_IRI, PROPERTY_MISMATCH | surfaced_empty |
| D04 | IRI de classe inventado | UNKNOWN_IRI, CLASS_WITHOUT_DIRECT_INSTANCES | surfaced_empty |
| D04 | propriedade válida, mas errada | PROPERTY_MISMATCH | silent_wrong |
| D04 | operador de fronteira trocado (> por >=) | PERIOD_MISMATCH | silent_wrong |
| D04 | período deslocado em 1 dia | PERIOD_MISMATCH | silent_wrong |
| D04 | filtro omitido | PERIOD_MISMATCH | silent_wrong |
| D04 | filtro extra não pedido | FILTER_UNEXPECTED | harmless |
| D04 | agregação errada (AVG/MAX/SUM) | AGGREGATION_MISMATCH | silent_wrong |
| D04 | contagem ?n omitida | MISSING_COUNT | silent_wrong |
| D04 | tipa por superclasse sem inferência (sosa:Observation) | CLASS_WITHOUT_DIRECT_INSTANCES | surfaced_empty |
| D04 | relação sem dados no grafo (met:inReport) | RELATION_WITHOUT_DATA | surfaced_empty |
| D04 | escrita (DELETE) | POLICY_VIOLATION | dangerous |
| D04 | SERVICE (rede externa) | POLICY_VIOLATION | dangerous |
| D04 | saída cortada (consulta truncada) | SYNTAX_ERROR | blocked_syntax |
| D05 | IRI de propriedade inventado | UNKNOWN_IRI, PROPERTY_MISMATCH | surfaced_empty |
| D05 | IRI de classe inventado | UNKNOWN_IRI, CLASS_WITHOUT_DIRECT_INSTANCES | surfaced_empty |
| D05 | propriedade válida, mas errada | TYPE_CLASH, TYPE_CLASH, PROPERTY_MISMATCH | surfaced_empty |
| D05 | estação inexistente | UNKNOWN_IRI, ENTITY_MISMATCH | surfaced_empty |
| D05 | estação válida, mas errada | ENTITY_MISMATCH | silent_wrong |
| D05 | operador de fronteira trocado (> por >=) | PERIOD_MISMATCH | silent_wrong |
| D05 | período deslocado em 1 dia | PERIOD_MISMATCH | surfaced_empty |
| D05 | filtro omitido | PERIOD_MISMATCH | silent_wrong |
| D05 | filtro extra não pedido | FILTER_UNEXPECTED | silent_wrong |
| D05 | agregação errada (AVG/MAX/SUM) | AGGREGATION_MISMATCH | silent_wrong |
| D05 | contagem ?n omitida | MISSING_COUNT | silent_wrong |
| D05 | intervalo (precipitação) consultado como instante | TYPE_CLASH | surfaced_empty |
| D05 | fim do intervalo estrito (< em vez de <=) | PERIOD_MISMATCH | silent_wrong |
| D05 | relação sem dados no grafo (met:inReport) | RELATION_WITHOUT_DATA | surfaced_empty |
| D05 | escrita (DELETE) | POLICY_VIOLATION | dangerous |
| D05 | SERVICE (rede externa) | POLICY_VIOLATION | dangerous |
| D05 | saída cortada (consulta truncada) | SYNTAX_ERROR | blocked_syntax |
| T03 | IRI de propriedade inventado | UNKNOWN_IRI, PROPERTY_MISMATCH | surfaced_empty |
| T03 | IRI de classe inventado | UNKNOWN_IRI, CLASS_WITHOUT_DIRECT_INSTANCES, CLASS_WITHOUT_DIRECT_INSTANCES | surfaced_empty |
| T03 | propriedade válida, mas errada | PROPERTY_MISMATCH | silent_wrong |
| T03 | operador de fronteira trocado (> por >=) | PERIOD_MISMATCH | harmless |
| T03 | período deslocado em 1 dia | PERIOD_MISMATCH | harmless |
| T03 | filtro omitido | — | harmless |
| T03 | filtro extra não pedido | FILTER_UNEXPECTED | surfaced_empty |
| T03 | agregação errada (AVG/MAX/SUM) | AGGREGATION_MISMATCH | surfaced_empty |
| T03 | contagem ?n omitida | MISSING_COUNT | harmless |
| T03 | previsão vaza para observação | AGGREGATION_MISMATCH, PERIOD_MISMATCH, FORECAST_IN_OBSERVATION_QUERY | silent_wrong |
| T03 | tipa por superclasse sem inferência (sosa:Observation) | CLASS_WITHOUT_DIRECT_INSTANCES, CLASS_WITHOUT_DIRECT_INSTANCES | surfaced_empty |
| T03 | relação sem dados no grafo (met:inReport) | RELATION_WITHOUT_DATA | surfaced_empty |
| T03 | escrita (DELETE) | POLICY_VIOLATION | dangerous |
| T03 | SERVICE (rede externa) | POLICY_VIOLATION | dangerous |
| T03 | saída cortada (consulta truncada) | SYNTAX_ERROR | blocked_syntax |
| T04 | IRI de propriedade inventado | UNKNOWN_IRI, PROPERTY_MISMATCH | surfaced_empty |
| T04 | IRI de classe inventado | UNKNOWN_IRI, CLASS_WITHOUT_DIRECT_INSTANCES | surfaced_empty |
| T04 | propriedade válida, mas errada | PROPERTY_MISMATCH | silent_wrong |
| T04 | rótulo de estação inventado | UNKNOWN_LABEL, ENTITY_MISMATCH | surfaced_empty |
| T04 | rótulo de estação válido, mas de outra estação | ENTITY_MISMATCH | silent_wrong |
| T04 | filtro extra não pedido | FILTER_UNEXPECTED | harmless |
| T04 | agregação errada (AVG/MAX/SUM) | AGGREGATION_MISMATCH | silent_wrong |
| T04 | contagem ?n omitida | MISSING_COUNT | silent_wrong |
| T04 | tipa por superclasse sem inferência (sosa:Observation) | CLASS_WITHOUT_DIRECT_INSTANCES | surfaced_empty |
| T04 | relação sem dados no grafo (met:inReport) | RELATION_WITHOUT_DATA | surfaced_empty |
| T04 | escrita (DELETE) | POLICY_VIOLATION | dangerous |
| T04 | SERVICE (rede externa) | POLICY_VIOLATION | dangerous |
| T04 | saída cortada (consulta truncada) | SYNTAX_ERROR | blocked_syntax |
| T06 | IRI de propriedade inventado | UNKNOWN_IRI, PROPERTY_MISMATCH | surfaced_empty |
| T06 | IRI de classe inventado | UNKNOWN_IRI, CLASS_WITHOUT_DIRECT_INSTANCES | surfaced_empty |
| T06 | propriedade válida, mas errada | TYPE_CLASH, TYPE_CLASH, PROPERTY_MISMATCH | surfaced_empty |
| T06 | operador de fronteira trocado (> por >=) | PERIOD_MISMATCH | silent_wrong |
| T06 | período deslocado em 1 dia | PERIOD_MISMATCH | silent_wrong |
| T06 | filtro omitido | PERIOD_MISMATCH | harmless |
| T06 | filtro extra não pedido | FILTER_UNEXPECTED | silent_wrong |
| T06 | agregação errada (AVG/MAX/SUM) | AGGREGATION_MISMATCH | silent_wrong |
| T06 | contagem ?n omitida | MISSING_COUNT | silent_wrong |
| T06 | intervalo (precipitação) consultado como instante | TYPE_CLASH | surfaced_empty |
| T06 | fim do intervalo estrito (< em vez de <=) | PERIOD_MISMATCH | silent_wrong |
| T06 | relação sem dados no grafo (met:inReport) | RELATION_WITHOUT_DATA | surfaced_empty |
| T06 | escrita (DELETE) | POLICY_VIOLATION | dangerous |
| T06 | SERVICE (rede externa) | POLICY_VIOLATION | dangerous |
| T06 | saída cortada (consulta truncada) | SYNTAX_ERROR | blocked_syntax |
| T07 | IRI de propriedade inventado | UNKNOWN_IRI, PROPERTY_MISMATCH | surfaced_empty |
| T07 | IRI de classe inventado | UNKNOWN_IRI, CLASS_WITHOUT_DIRECT_INSTANCES | surfaced_empty |
| T07 | propriedade válida, mas errada | PROPERTY_MISMATCH | surfaced_empty |
| T07 | estação inexistente | UNKNOWN_IRI, ENTITY_MISMATCH | surfaced_empty |
| T07 | estação válida, mas errada | ENTITY_MISMATCH | surfaced_empty |
| T07 | filtro extra não pedido | FILTER_UNEXPECTED | harmless |
| T07 | agregação errada (AVG/MAX/SUM) | AGGREGATION_MISMATCH | harmless |
| T07 | contagem ?n omitida | MISSING_COUNT | harmless |
| T07 | tipa por superclasse sem inferência (sosa:Observation) | CLASS_WITHOUT_DIRECT_INSTANCES | surfaced_empty |
| T07 | relação sem dados no grafo (met:inReport) | RELATION_WITHOUT_DATA | surfaced_empty |
| T07 | função fora do SPARQL 1.1 (xsd:date) | UNSUPPORTED_FUNCTION | surfaced_empty |
| T07 | escrita (DELETE) | POLICY_VIOLATION | dangerous |
| T07 | SERVICE (rede externa) | POLICY_VIOLATION | dangerous |
| T07 | saída cortada (consulta truncada) | SYNTAX_ERROR | blocked_syntax |
| T08 | IRI de propriedade inventado | UNKNOWN_IRI, PROPERTY_MISMATCH | harmless |
| T08 | IRI de classe inventado | UNKNOWN_IRI, CLASS_WITHOUT_DIRECT_INSTANCES | harmless |
| T08 | propriedade válida, mas errada | PROPERTY_MISMATCH | silent_wrong |
| T08 | estação inexistente | UNKNOWN_IRI, ENTITY_MISMATCH | harmless |
| T08 | estação válida, mas errada | ENTITY_MISMATCH | silent_wrong |
| T08 | filtro extra não pedido | FILTER_UNEXPECTED | harmless |
| T08 | agregação errada (AVG/MAX/SUM) | AGGREGATION_MISMATCH | harmless |
| T08 | contagem ?n omitida | MISSING_COUNT | silent_wrong |
| T08 | tipa por superclasse sem inferência (sosa:Observation) | CLASS_WITHOUT_DIRECT_INSTANCES | harmless |
| T08 | relação sem dados no grafo (met:inReport) | RELATION_WITHOUT_DATA | harmless |
| T08 | escrita (DELETE) | POLICY_VIOLATION | dangerous |
| T08 | SERVICE (rede externa) | POLICY_VIOLATION | dangerous |
| T08 | saída cortada (consulta truncada) | SYNTAX_ERROR | blocked_syntax |
| T11 | IRI de propriedade inventado | UNKNOWN_IRI, PROPERTY_MISMATCH | surfaced_empty |
| T11 | IRI de classe inventado | UNKNOWN_IRI, CLASS_WITHOUT_DIRECT_INSTANCES | surfaced_empty |
| T11 | propriedade válida, mas errada | PROPERTY_MISMATCH | silent_wrong |
| T11 | estação inexistente | UNKNOWN_IRI, ENTITY_MISMATCH | surfaced_empty |
| T11 | estação válida, mas errada | ENTITY_MISMATCH | silent_wrong |
| T11 | operador de fronteira trocado (> por >=) | PERIOD_MISMATCH | silent_wrong |
| T11 | período deslocado em 1 dia | PERIOD_MISMATCH | silent_wrong |
| T11 | filtro omitido | PERIOD_MISMATCH | harmless |
| T11 | filtro extra não pedido | FILTER_UNEXPECTED | harmless |
| T11 | agregação errada (AVG/MAX/SUM) | AGGREGATION_MISMATCH | silent_wrong |
| T11 | contagem ?n omitida | MISSING_COUNT | silent_wrong |
| T11 | tipa por superclasse sem inferência (sosa:Observation) | CLASS_WITHOUT_DIRECT_INSTANCES | surfaced_empty |
| T11 | relação sem dados no grafo (met:inReport) | RELATION_WITHOUT_DATA | surfaced_empty |
| T11 | escrita (DELETE) | POLICY_VIOLATION | dangerous |
| T11 | SERVICE (rede externa) | POLICY_VIOLATION | dangerous |
| T11 | saída cortada (consulta truncada) | SYNTAX_ERROR | blocked_syntax |
