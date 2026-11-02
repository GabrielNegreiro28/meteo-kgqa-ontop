# KGQA meteorológico: perguntas em português sobre um grafo de conhecimento (SPARQL)

Fatia do projeto "Ontology-Grounded Agentic Architecture" (Parente, rev. 13/10/2026) que cobre o trajeto completo para a consulta em grafo:
pergunta em linguagem natural, entendimento conferido, SPARQL montado por código, execução somente leitura no grafo virtual do Ontop sobre
105 mi de observações reais de 178 aeródromos (2016 a 2025), verificação e resposta com procedência. Fora do escopo desta fatia: roteador,
MongoDB, PDFs e controle de acesso (o módulo expõe `capabilities()` para o roteador decidir o que mandar para cá).

Plano e decisões da versão final: `docs/PLANO_ARQUITETURA_FINAL.md`. Decisões e pendências anteriores: `DECISOES.md`, `docs/ANALISE_CRITICA.md`.

## O módulo (`metqa/`)

Um só caminho de execução, com contratos tipados, portas e adaptadores. O LLM entende e normaliza a pergunta (datas, horas, unidades,
cálculo) em duas leituras independentes, em paralelo. O código confere o resto, sem gramática de regex:
- o mundo fechado da ontologia (grandeza, estação, unidade por análise dimensional, agregação admitida, cobertura);
- a conservação da evidência: todo número do trecho citado tem de estar no valor normalizado ("dia 3" não vira o mês inteiro), e o trecho de
  tempo é relido sozinho numa chamada curta;
- a concordância entre as leituras e a política de risco: com sinal forte, pergunta ao usuário; sem usuário, devolve as opções com um token
  de confirmação assinado, nunca adivinha.

O SPARQL sai só do compilador, que declara o papel de cada coluna (`ResultShape`); status e texto leem esse papel. Cada confirmação vira um
exemplo verificado, versionado com a camada semântica.

```
pergunta ─► memória de exemplos ─► 2 leituras do LLM ─► mundo fechado ─► conservação da evidência ─► concordância + risco ─► [usuário]
         ─► planejador (1 a 4 partes) ─► compilador (+ ResultShape) ─► Ontop ─► verificação ─► texto + "Entendi assim" + procedência
         ─► trilha completa + exemplo verificado ─► (em lote) evolução EvoOntology
```
```bash
python -m metqa "Quanto choveu em SBGL no dia 15 de fevereiro de 2024?"     # pergunta quando há dúvida (--confirm risk|always|never)
python -m metqa --show-query "Quantas horas com chuva houve em SBCY em 2022?"
python -m metqa --json "..."                                                    # resposta completa no contrato 0.3.0
python -m metqa --lexicon ontology "..."                                        # sem a camada EvoOntology (ablação)
```
Como biblioteca: `MetQA.ask(pergunta, user=None, confirmed=None, confirmation=None)` devolve a resposta (contrato 0.3.0, com `result_shape`)
e a trilha; `MetQA.capabilities()` diz grandezas, cobertura, formas de pergunta e limites. Cada pergunta custa centavos de LLM, limitados por
`--budget` e pelo teto do ledger. A chave vai em `OPENAI_API_KEY` no `kgqa.env`, fora do repositório.

| Camada | Onde | Papel |
|---|---|---|
| Dados | `ingest/`, `data/REGRAS_LIMPEZA.md`, `data/DICIONARIO_DADOS.md` | CSV → pacotes verificados → DuckDB (limpeza e quarentena) → PostgreSQL |
| Catálogo de grandezas | `ontology/catalog.py` | a única tabela de grandezas, unidades, fatores e faixas físicas, lida da ontologia; ingestão, mapeamento, SHACL e o módulo saem dela |
| Grafo virtual | `mapping/`, `ontology/met.ttl` | Ontop expõe o banco como grafo SOSA/OWL-Time/QUDT, com dia, hora e dia da semana locais |
| Ontologia formal | `ontology/` | uma fonte, três visões: BFO 2020 importada sem alteração e alinhamento por axiomas, visão OWL 2 DL conferida pelo HermiT, visão QL e a que o Ontop carrega. O alinhamento e as grandezas de nuvem são provisórios (`docs/DUVIDAS_ONTOLOGIA.md`) |
| Módulo | `metqa/` | entendimento, planejamento, compilação, execução, verificação, apresentação, diálogo, LLM e ledger |
| Camada semântica | `semantics/` | EvoOntology ligado à ontologia formal: Termos com IRI e categoria BFO, porta de validação, trajetórias e o ciclo de evolução |
| Avaliação | `eval/`, `tests/` | conjuntos congelados com oráculo independente em pandas (`freeze_set → validate_set → run_independent → adjudicate → stats`) |

O legado (prompts v1–v8, SPARQL escrito pelo LLM, fundamentação por regex) está na tag `legado-v8`.

## Instalar e rodar

Desenvolvimento (Windows ou Linux, sem o grafo real): os testes que precisam do Ontop são pulados.
```bash
python -m venv .venv && .venv/Scripts/activate        # Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
```

Grafo real (WSL/Linux, sem `sudo`): instala JDK 17, Ontop 5.5.0, driver JDBC e Python 3.12 (versões e SHA-256 fixados em `infra/setup_wsl.sh`).
```bash
bash infra/setup_wsl.sh && source ~/metdata/env.sh
PACK=<pasta com os .npz> bash infra/rebuild.sh        # ~28 min: carga, limpeza, PostgreSQL, chaves, Ontop
bash infra/verify.sh                                   # sobe o que estiver parado e roda a suíte inteira contra o grafo real
```
Os `.npz` saem de `ingest/pack.py` sobre os CSV. Os dados reais nunca vão ao git. O endpoint do Ontop não tem autenticação: o script o
prende ao loopback (`SERVER_ADDRESS=127.0.0.1`); não mude isso. Num banco já carregado antes das colunas de hora local:
`python ingest/export_pg.py --local-time` e `python ingest/finalize_pg.py` (sensores das grandezas de nuvem).

Medir com o LLM real (gasta dinheiro; o teto acumulado fica em `eval/reports/spend_ledger.jsonl`, e passar dele exige `--authorize-usd`,
`--authorized-by` e `--reason`):
```bash
python -m eval.freeze_set <perguntas.yaml> --name <conjunto> --source "..."       # congela antes de rodar
python -m eval.validate_set <conjunto>                                            # oráculos pandas, sem LLM
python -m eval.run_independent --set <conjunto> --prompts metqa --budget 4 --tag _1    # também metqa-1r, metqa-formal, metqa-noconserv
python -m eval.adjudicate <conjunto> metqa=metqa_1                                  # placar com os vereditos de docs/julgamento_<conjunto>_veredictos.yaml
```
Cada execução grava a trilha completa de cada pergunta (`..._trace.jsonl`) e a trajetória de medição, que a evolução nunca minera.

Ontologia, catálogo e evolução (não gastam LLM, exceto `--adapter metqa`):
```bash
python -m ontology.catalog                            # regera ontology/shapes.ttl do catálogo (um teste confere)
python mapping/build_mapping.py > mapping/met.obda    # regera o mapeamento do catálogo (idem)
python -m ontology.build_views                        # regera ontology/generated/
python -m semantics.build --rebuild                   # refaz a camada semântica se a ontologia mudou
python -m semantics.run_evolution --seed-gold --require-reasoner --sample-graph     # avaliação barata (reconhecimento da grandeza)
python -m semantics.run_evolution --adapter metqa --set <conjunto> --budget 2        # avaliação com o módulo inteiro (gasta LLM)
```

## O que a medição mostra (e o que não mostra)

Conjunto independente novo_b_100_20261028_validado (100 perguntas, rodada única, 2026-10-31, antes do plano final): 86/100 corretas
[IC95% 78–91%], 1 resposta errada entregue, 13 abstenções, US$ 0,032 e 9,5 s por pergunta (`docs/RESULTADOS_MVP_novo_b_100_20261028.md`).
As abstenções e os defeitos achados ali são os que o plano final corrigiu; a medição da versão final está em `docs/RESULTADOS_FINAL_novo_c.md`.

Os vereditos são julgamento do Claude conferido na base limpa, sem revisão humana: o placar é reproduzível, não um gabarito independente.

## Mapa de documentos

`docs/PLANO_ARQUITETURA_FINAL.md` (o plano) · `DECISOES.md` (cada decisão com motivo e como reverter) · `docs/DUVIDAS_ONTOLOGIA.md` (para a
equipe de ontologia) · `docs/EQUIVALENCIA_LOCALDATE.md` e `eval/equivalencia_hora_local.py` (equivalências medidas) ·
`data/DICIONARIO_DADOS.md`, `data/REGRAS_LIMPEZA.md`.
