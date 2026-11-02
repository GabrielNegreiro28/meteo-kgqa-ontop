"""MVP de perguntas em linguagem natural sobre dados meteorológicos (ontologia BFO + Ontop + EvoOntology).

Arquitetura (docs/ARQUITETURA_MVP.md, docs/PLANO_ARQUITETURA_FINAL.md): uma pipeline LINEAR de estágios com contratos tipados, portas e
adaptadores. O LLM entende e NORMALIZA a pergunta, em duas leituras independentes; o código confere o mundo fechado da ontologia, liga cada
valor ao trecho que o justifica, pergunta ao usuário quando há risco, monta o SPARQL e escreve a resposta.

    memória -> 2 leituras -> mundo fechado -> conservação da evidência -> concordância + risco -> [usuário] -> planejador
            -> compilador (+ ResultShape) -> executor -> verificação-pós -> texto + procedência -> trilha -> (em lote) evolução

Pacote único (plano, D11): o que era `pipeline/` e `kgqa/` e o metqa usa mora aqui (índice da ontologia, regras de consulta, compilador,
executor, contrato, LLM, procedência); o resto, com os prompts v1–v8 e o orquestrador antigo, ficou na tag `legado-v8`. Fora daqui, só a
porta do léxico (EvoOntology, `semantics/`) e a da evolução; `tests/test_architecture.py` confere.
"""
