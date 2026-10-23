# Ontologias importadas (fixadas)

Conforme o documento da arquitetura (§6.4): a BFO é reutilizada **sem alteração**, e dos módulos da IAO só entra o que se usa, em
versão fixa. Os arquivos abaixo são o que o teste `tests/test_ontology_formal.py` confere por SHA-256; trocar qualquer um exige
registrar a nova versão aqui e rodar a verificação formal de novo.

| Arquivo | Origem | Versão | SHA-256 |
|---|---|---|---|
| `bfo-core.owl` | https://raw.githubusercontent.com/BFO-ontology/BFO-2020/master/21838-2/owl/bfo-core.owl (BFO 2020, ISO/IEC 21838-2; baixado da branch `master`, sem tag: o SHA é a fixação) | `http://purl.obolibrary.org/obo/bfo/2020/bfo-core.owl` | `b65c817a7a25501499d287981aea972f2ce33146dcfb855915a459f6a051718d` |
| `iao-module.owl` | módulo extraído de `http://purl.obolibrary.org/obo/iao.owl` com `robot extract --method BOT` a partir dos termos de `iao-terms.txt` (information content entity, measurement datum) | IAO `2026-03-30` (`iao.owl` completo, SHA `c27ff2964a2ad8165bc365698b628aae95108411384aa4450e6e1b1e82bf0f41`) | `175e87335d5e9fd946a55623fe37b17464fb8907dc302079ea30a6ef48d5e7b7` |
| `iao-terms.txt` | termos pedidos na extração | — | `b49e842efaba56b6f01397bee93328bb1317c8b77be59f1f668d86be00422201` |

Ferramenta de verificação (não faz parte do repositório; instalada por `ontology/imports/fetch.sh`):

| Ferramenta | Origem | SHA-256 |
|---|---|---|
| ROBOT 1.9.7 (`robot.jar`, inclui HermiT e o validador de perfis OWL 2) | https://github.com/ontodev/robot/releases/download/v1.9.7/robot.jar | `91890c2e83d0f092dd08731376f154b36610544cfbe8685337a1bf7244ccaa2d` |

Licenças: BFO e IAO são CC BY 4.0; ROBOT é BSD-3. A atribuição está nos próprios arquivos.
