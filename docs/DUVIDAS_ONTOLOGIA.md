# Dúvidas de modelagem para a equipe de ontologia (P-07, P-27)

Estado: o alinhamento com a BFO 2020 é agora **axiomatizado e verificado por raciocinador** (`ontology/met-bfo.ttl`, `ontology/build_views.py`,
`tests/test_ontology_formal.py`), mas **toda colocação abaixo é hipótese minha**, não decisão de especialista. Esta lista é o que precisa de revisão
antes de a ontologia ser tratada como definitiva. Cada item diz o que está hoje, a alternativa e o que mudaria.

## 1. Qualidades, grandezas e portadores
- **Hoje:** cada grandeza observável (`met:AirTemperature`…) continua um *indivíduo* de `sosa:ObservableProperty`, e a classe `sosa:ObservableProperty` é
  conteúdo de informação (uma *referência* ao tipo de grandeza). A qualidade BFO que cada uma mede é uma **classe** (`met:AirTemperatureQuality ⊑ quality`),
  ligada por `met:denotesQuality` (anotação, sem lógica). O grafo não instancia qualidades, e não há `inheresIn`.
- **Dúvida:** a SOSA fala do tipo genérico de grandeza; a BFO fala de qualidades *particulares* de um portador. Vale modelar a qualidade particular (uma por
  estação, instante e grandeza)? Custaria uma entidade extra por observação (centenas de milhões) sem ganho para as perguntas atuais.
- **Casos que provavelmente NÃO são qualidade do ar:** precipitação e duração (processo ou porção de água; em BFO talvez *process profile*), vento e rajada
  (movimento do ar), visibilidade (disposição do ar de transmitir luz), QNH (valor reduzido ao nível do mar, não uma qualidade medida na estação),
  temperatura da pista (portador é a pista, não o ar).

## 2. O que é `met:Site`
- **Hoje:** `met:Site ⊑ material entity`, com o comentário de que é a **porção de atmosfera** junto à estação. Mudei de `site` (região imaterial).
- **Por quê:** qualidades inerem em entidades materiais; um `site` é só uma localização.
- **Dúvida:** o rótulo "local observado" ficou enganoso. Renomear (para "porção de ar") mexe no grafo (`:site/{sigla}`) e no mapeamento. Ou manter `Site` como
  localização e criar a porção de ar como entidade nova?

## 3. Observação como processo
- **Hoje:** `sosa:Observation ⊑ process`; `sosa:madeBySensor` e `sosa:hasFeatureOfInterest` são subpropriedades de *has participant*; `sosa:phenomenonTime` de
  *occupies temporal region*.
- **Dúvida:** a BFO-OBDA/WF4 exige participante, e isto atende. Mas uma observação "instantânea" é um processo de duração zero? (`time:Instant` está como região
  temporal 0D e `time:Interval` como 1D.) É a leitura mais comum, mas há quem trate medição como evento (*process boundary*).

## 4. Boletim e previsão como conteúdo de informação
- **Hoje:** `met:WeatherReport` e `met:Forecast` ⊑ information content entity (IAO_0000030).
- **Dúvida (herdada do alinhamento antigo):** a previsão é *sobre* o quê, se a qualidade futura ainda não existe? E o boletim também é a *coleção* das observações
  de um instante (mereologia), não só conteúdo.

## 5. Valor medido
- **Hoje:** `qudt:QuantityValue ⊑ measurement datum` (IAO_0000109). Falta a relação *is about* da WF5 (o valor é sobre a qualidade).
- **Dúvida:** modelar `isAbout` para a classe de qualidade (punning) ou deixar sem a relação até haver qualidades particulares (item 1).

## 6. Classes externas colocadas por mim
`sosa:Sensor`, `sosa:Platform` ⊑ material entity; `sosa:FeatureOfInterest` ⊑ continuant (restringe a SOSA: aqui todo objeto de interesse é continuante);
`sosa:Result`, `qudt:Unit`, `skos:Concept`, `skos:ConceptScheme`, `met:AggregationFunction` ⊑ information content entity. A BFO é "para o domínio", então a colocação de
classes de SOSA/QUDT/SKOS é escolha de aplicação; a equipe pode preferir não afirmá-las.

## 7. Limites formais conhecidos (não são dúvida, são fato verificado)
- `xsd:date` **não está no mapa de datatypes do OWL 2**. Para o perfil DL ele é declarado como datatype; o perfil **QL não o admite**, então `met:localDate rdfs:range
  xsd:date` fica fora da visão QL. A checagem do tipo da data vem do SHACL.
- O **domínio alternativo** (`met:localDate` em observação *e* em boletim) é `owl:unionOf` na visão completa e **não existe na visão QL** (união de domínio não é QL).
  Ficam: a união na visão DL (HermiT confere), a regra da pipeline (`met:alsoDomain`) e o teste de conformância com o grafo real.
- **Domínios e imagens** estão na visão QL completa, mas **não** na visão que o Ontop carrega (`build_ontop`): medido no grafo real, `?s a sosa:Sensor` virava união
  sobre as 105 mi de observações e estourava 60 s. Eles só adicionam tipos que o mapeamento já emite.
- O HermiT lê cada arquivo OWL sozinho: propriedade não declarada **no mesmo arquivo** vira anotação e é ignorada. A amostra do grafo real é conferida num arquivo único
  com a ontologia, e há um controle negativo (o defeito antigo do domínio) que tem de falhar.

## 8. Fora de escopo desta rodada
Ciclo de evolução do EvoOntology com colocação BFO obrigatória e checagem de consistência de classes novas (§7.3, §7.4), CCO, e a ontologia oficial da equipe (substituiria
`met.ttl`). A porta de validação do EvoOntology (`semantics/gate.py`) ainda confere a categoria contra `met:bfoCategory`; ligá-la ao raciocinador é o passo seguinte.
