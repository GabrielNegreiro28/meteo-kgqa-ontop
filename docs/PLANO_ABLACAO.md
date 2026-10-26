# Plano de ablação e de medição (precisa de verba; NADA aqui foi executado)

Tudo o que não gasta LLM já está implementado e testado. O que falta para dizer "isto acerta tanto" e "a camada semântica ajuda" exige chamar o LLM.
Este arquivo diz o que medir, em que condições e quanto custa, para a decisão de gasto ser informada. Custo por pergunta com o modelo atual: ~US$ 0,035
(medido: 48 perguntas = US$ 1,75 na avaliação independente, prompt `v4`). Saldo do ledger no momento: ~US$ 0,06 de teto US$ 18,55.

## O que cada medição responde

| # | Pergunta | Condições (mesmo modelo, mesmas perguntas, mesma temperatura) | Conjunto | Custo estimado |
|---|---|---|---|---|
| A1 | O `v7` corrigiu as falhas da avaliação independente? | `v4` (já medido) × `v7` | **conjunto NOVO** de 30–50 perguntas (o independente de 49 já foi visto) | US$ 1,0 a 1,8 |
| A2 | A forma por código (v6/v7) ajuda ou só troca o erro de lugar? | `v4` × `v6` × `v7` | o mesmo conjunto novo | + US$ 2,0 a 3,5 |
| A3 | A camada semântica ajuda? | `v4` × `v5` (camada v1) × `v5` (camada evoluída) | o mesmo conjunto novo | + US$ 2,0 a 3,5 |
| A4 | BFO, EvoOntology e compilador separados | `v4` / `v4`+camada / `v7` / `v7`+camada | o mesmo conjunto novo | + US$ 2,0 a 3,5 |
| A5 | Repetibilidade | cada condição 3 vezes (variância do próprio modelo) | subconjunto de 20 | × 3 do custo da condição |

Ordem sugerida: **A1 primeiro** (é o que o MVP precisa), A3 depois (é a contribuição do documento), A5 se houver verba. Cada condição roda com
`python -m eval.run_independent`-like sobre o conjunto novo (ver abaixo) e a comparação sai de `python -m eval.stats` (IC e McNemar exato).

## Como rodar quando houver autorização

1. Gerar o conjunto novo: `docs/PROMPT_GPT_PERGUNTAS.md` com **outro gerador**, ou, melhor, 10 a 20 perguntas reais de usuários da área (pedir ao professor).
   Congelar com hash antes de qualquer execução: `python -m eval.freeze_set perguntas.yaml --name novo_a --source "quem gerou"` (recusa pergunta já vista em conjunto anterior, grava `eval/frozen/<name>/` com sha256; sem custo).
2. Autorizar a verba no ledger (`--authorize-usd`, `--authorized-by`, `--reason`), **um valor por medição**.
3. `python -m eval.run_independent --prompts v7 --tag _a` (e `--prompts v4`, `v5`…); uma execução por condição, sem ajustar regra nem prompt depois.
4. Julgamento humano de cada divergência (erro do sistema, erro da referência, diferença de limpeza) antes de qualquer taxa de acerto.

## O que já é medido sem verba (e o que NÃO significa)

- **Compilador × pandas** (`tests/test_compiler_differential.py`): 56 especificações sorteadas, todas iguais. Prova o compilador, não o LLM.
- **Reconhecimento de grandeza pela camada** (`semantics/resolution.py`): Jaccard entre as grandezas que a camada reconhece e as da consulta de referência. No estado atual, a
  validação congelada dá 0,864 (camada `ontology_v1`) e 0,932 com o sinônimo "choveu" (candidato aceito numa cópia). **É uma medida de reconhecimento de sinônimos, não de
  resposta correta**: um Candidate que reconhece melhor pode não mudar a resposta final. Por isso A3 existe.
