# Validação da implementação 0.4.0

Executada em 03/11/2026, na retomada da implementação iniciada após `ed29037`.

| Execução | Resultado |
|---|---|
| Windows, `.venv/Scripts/python.exe -m pytest -q --tb=short -rs` | **326 passed, 102 skipped**, 111,88 s |
| WSL Ubuntu, `test_real_pipeline`, `test_compiler_differential`, `test_ontology_formal`, `test_semantics` | **127 passed**, 385,37 s |
| WSL Ubuntu, `test_metqa_real`, `test_ontop_dialect`, `test_infra` | **41 passed**, 15,72 s |
| Regressões finais de contrato, manifesto, estudo, entendimento, apresentação e novo_c | **65 passed**, 3,82 s |

Os testes pulados no Windows dependem da base DuckDB local, endpoint Ontop, ferramentas Linux ou ROBOT/Java.
Essas integrações foram exercitadas separadamente no WSL nos grupos acima. O teste específico de comportamento
do DuckDB em `test_backend_quirks.py` permaneceu pulado no Windows e não integrou a rodada WSL desta entrega.
Os totais de Windows e WSL não devem ser somados como testes distintos.

O WSL usou os dados existentes em `/home/gabriel/metdata`, com DuckDB 1.5.6, PostgreSQL, Ontop e ROBOT/HermiT.
Os serviços estavam desligados, foram iniciados temporariamente para testar e desligados após cada rodada.
Não foi refeita a ingestão dos CSVs nem alterada a política meteorológica.

As regressões incluem:

- estações e valores trocados, multiplicidade e referência ausente versus vazia;
- dados brutos em metros e apresentação em quilômetros, sem metadados contraditórios;
- confirmação sem variável de chave, invalidada quando muda o snapshot;
- evidência obrigatória nas duas leituras e falha técnica da releitura temporal;
- decimais exatos e IRIs completos; rejeição de números não finitos;
- interpretações por parte em planos divididos por estação;
- proibição de declarar vencedor com resultado truncado;
- extração de cobertura com os mesmos IRIs do catálogo e detecção de manifesto/base alterados;
- referência SQL sobre base limpa, validação de unidades e recusa de SQL de escrita;
- agenda pareada, três repetições, ablação do contexto BFO e rejeição de rodadas incompletas.

`git diff --check` passou. As interfaces `--help` de manifesto, referência limpa e estudo foram executadas.
Os resultados 87/100 publicados anteriormente não foram recalculados nem substituídos por estes testes.

## Dependências externas à implementação

Nenhuma chamada paga de LLM foi realizada. O estudo final de 120 perguntas está implementado como ferramenta,
mas não foi executado e seu conjunto novo ainda precisa ser preparado e revisado com as referências.
Não há alegação de ganho de acurácia, cumprimento das metas experimentais ou aprovação das hipóteses meteorológicas.
Veja [arquitetura e instruções](ARQUITETURA_0_4.md).
