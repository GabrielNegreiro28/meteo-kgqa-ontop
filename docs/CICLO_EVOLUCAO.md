# Ciclo de evolução do EvoOntology (documento da arquitetura, §7.3 e §7.4)

Estado: **implementado e testado sem LLM**; o "agente de evolução" e o avaliador padrão são **determinísticos**. Isto é uma escolha de implementação, dita aqui para não ser
confundida com o agente (LLM) que o documento descreve: um LLM pode ocupar o lugar do minerador sem mudar a porta, a avaliação nem a publicação.

## As etapas e onde estão

| Etapa do documento | O que existe | Onde |
|---|---|---|
| Build (v0, depois refeita quando a ontologia muda) | Termos com IRI e categoria BFO copiados da ontologia; `--rebuild` grava a próxima versão se a ativa ficou defasada (teste confere) | `semantics/build.py` |
| Use (trajetórias) | `record_trajectory` grava sinais do §13 (reparos, achados, abstenções, palavras sem cobertura); `seed_from_gold` gera trajetórias de **semente** do gabarito para exercitar o ciclo sem LLM (rotuladas `gold_seed`) | `semantics/trajectories.py`, `semantics/seed.py` |
| Evolve (atribuir a uma camada e remendar) | `mine`: palavra sem cobertura que leva sempre à mesma grandeza em >= 2 trajetórias confiáveis → **sinônimo (conteúdo)**. Achados do verificador recorrentes → **proposta** (ferramenta ou formal), não remendo | `semantics/evolve.py` |
| Porta de validação (§7.4 regra 4) | IRI existe, categoria BFO igual à da ontologia, sem IRI disputado, agregações e unidade coerentes, unidade aceita pelo SHACL, **raciocinador (HermiT) sobre os axiomas das Relações do Candidate**, com amostra do grafo real | `semantics/gate.py` |
| Evaluate (Parent × Candidate, mesmas condições) | `ResolutionAdapter`: mesmo avaliador, mesmos casos; escore = Jaccard entre as grandezas reconhecidas e as da consulta de referência; validação congelada **disjunta** da construção + checagem de regressão | `semantics/resolution.py` |
| Publish or reject | `EvolutionSession` (núcleo): orçamento de rodadas congelado, só Accept publica e ativa; rejeição registra e a próxima rodada parte do Parent | `evoontology` (núcleo) |
| Duas vias de mudança (§7.4 regra 5) | conteúdo muda sozinho após a avaliação; o que alteraria a camada formal vira `proposals/pending.json` para revisão humana (§13) | `semantics/evolve.py::write_proposals` |

## O que a avaliação mede e o que não mede

Mede **reconhecimento da grandeza** a partir da pergunta (sinônimos). **Não** mede se a resposta final melhora: isso exige o LLM (`docs/PLANO_ABLACAO.md`, A3). Um Candidate pode melhorar o
reconhecimento e não mudar a resposta. A aceitação exige melhora ESTRITA na validação, nenhuma pergunta que o Parent acertava piorando, e a porta limpa.

## Resultado de uma execução real (numa cópia do workspace, 2026-10-23)

`python -m semantics.run_evolution --parent ontology_v1 --seed-gold --require-reasoner --sample-graph`: 35 trajetórias de semente, 1 hipótese ("choveu" → precipitação), porta limpa
(raciocinador sobre os axiomas + amostra de 33 indivíduos do grafo real), validação 0,864 → 0,932, sem regressão: **aceito** como `ontology_v2` **na cópia**. Não foi publicado no workspace
do repositório (publicar é decisão do responsável: `--in-place`). As trajetórias de semente vêm do gabarito, não de uso real: servem para exercitar e medir o ciclo.

## Limites conhecidos

- O minerador só propõe sinônimos de **uma palavra** e de uma grandeza; ele já descarta palavras que a pipeline interpreta por regra, fragmentos de nomes e palavras que aparecem em perguntas de
  outra grandeza. Isso é heurística: o que passa por ela ainda pode ser fraco, e é a avaliação que decide.
- Candidatos que mexem em Restrições ou Relações são avaliados pela porta (axiomas) mas ainda não há minerador que os proponha.
- A avaliação por LLM juiz (protocolo `llm_judge` do núcleo) não está ligada: exige LLM.
