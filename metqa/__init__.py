"""MVP de perguntas em linguagem natural sobre dados meteorológicos (ontologia BFO + Ontop + EvoOntology).

Arquitetura (docs/ARQUITETURA_MVP.md): uma pipeline LINEAR de estágios com contratos tipados, portas e adaptadores, e o LLM cercado por
código. O LLM só escolhe sentidos de um cardápio fechado e cita o trecho da pergunta que justifica cada escolha; tempo, números, unidades
e SPARQL são produzidos por código.

    leitor -> intérprete -> conciliação + verificação-pré -> planejador -> compilador -> executor -> verificação-pós -> apresentação -> trilha

Migração estranguladora: o pacote reaproveita, por importação, os módulos já provados de `pipeline/`, `kgqa/` e `semantics/`; o
orquestrador legado (`pipeline/orchestrator.py`, prompts v1–v8) continua existindo só para as comparações históricas.
"""
