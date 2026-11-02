# KGQA meteorológico: perguntas em português sobre um grafo de conhecimento (SPARQL)

Fatia do projeto "Ontology-Grounded Agentic Architecture" (Parente, rev. 13/10/2026) que cobre **o trajeto completo para a consulta em grafo**:
pergunta em linguagem natural, interpretação validada, SPARQL montado ou escrito e conferido, execução somente leitura no **grafo virtual do Ontop**
sobre 105 mi de observações reais de 178 aeródromos (2016 a 2025), verificação e resposta com procedência. Fora do escopo desta fatia: roteador,
MongoDB, PDFs e controle de acesso.

> **Leia primeiro `docs/ANALISE_CRITICA.md`**: o que está sólido, o que está fraco e o que foi corrigido. Decisões e pendências: `DECISOES.md`.

## MVP (`metqa/`): a arquitetura proposta (`docs/ARQUITETURA_MVP.md`)

Pipeline com contratos tipados, portas e adaptadores. **O entendimento não depende de gramática de regex**: o LLM entende e NORMALIZA a
pergunta (datas, horas, unidades, cálculo). A dúvida é detectada por mecanismos genéricos: duas leituras independentes que divergem,
evidência fora da pergunta, número ignorado e checagens do mundo fechado da ontologia. Ela é resolvida **com o usuário**: o sistema mostra
exatamente o que vai consultar e pergunta quando há risco. Sem usuário, devolve as opções em vez de adivinhar. Cada confirmação vira um
exemplo verificado que guia as próximas perguntas (`docs/ENTENDIMENTO_VERIFICADO.md`).

```
pergunta ─► memória de exemplos ─► 2 leituras do LLM ─► mundo fechado (Catálogo) ─► concordância + risco ─► [usuário confirma/escolhe/corrige]
         ─► planejador ─► compilador (único caminho para SPARQL) ─► Ontop ─► verificação ─► texto determinístico + "Entendi assim"
         ─► trilha + exemplo verificado (alimentam a evolução)
```
```bash
python -m metqa "Quanto choveu em SBGL no dia 15 de fevereiro de 2024?"     # no terminal, pergunta quando há dúvida (--confirm risk|always|never)
python -m metqa --show-query "Quantas horas com chuva houve em SBCY em 2022?"
python -m metqa --lexicon ontology "..."                                       # sem a camada EvoOntology (ablação)
python -m eval.run_independent --set <conjunto> --prompts metqa --budget 2 --tag _a   # medir (gasta LLM; ledger)
```
O legado abaixo (`python -m kgqa`, prompts v1–v8) continua disponível só para as comparações históricas.

## Como funciona

```
pergunta ──► etapa 1: interpretar (LLM → JSON) ──► regras L2–L4 ──► [diálogo de confirmação, opcional]
                                                                         │
   forma pedida (por ano, por cabeceira, os N maiores…)? ── sim ──► consulta MONTADA POR CÓDIGO (compile_structured)
                                                          └─ não ──► etapa 2: LLM escreve o SPARQL ──► regras L1–L3
                                                                         │
                          checagem prévia PELO MOTOR (Ontop /ontop/reformulate): recusa dialeto inválido e prova consulta vazia
                                                                         │
                  execução somente leitura (Ontop → SQL → PostgreSQL) ──► verificação ──► resposta + ressalvas + procedência (PROV-O)
```

| Camada | Onde | Papel |
|---|---|---|
| Dados | `ingest/`, `data/REGRAS_LIMPEZA.md`, `data/DICIONARIO_DADOS.md` | CSV → pacotes verificados → DuckDB (limpeza e quarentena) → PostgreSQL |
| Grafo virtual | `mapping/`, `ontology/met.ttl` | Ontop expõe o banco como grafo SOSA/OWL-Time/QUDT, sem copiar dados |
| Ontologia formal | `ontology/` (`met.ttl`, `met-structure.ttl`, `met-bfo.ttl`, `met-external.ttl`, `imports/`, `generated/`) | **uma fonte, três visões**: BFO 2020 importada sem alteração e alinhamento por axiomas; visão OWL 2 DL conferida pelo HermiT, visão QL e a visão que o Ontop carrega (`build_views.py`). O alinhamento é **provisório** (`docs/DUVIDAS_ONTOLOGIA.md`) |
| Executor | `kgqa/store.py` | SPARQL somente leitura: política, limite de linhas, tempo, reformulação pelo motor |
| Pipeline | `pipeline/` | interpretação, validadores L1 a L5, compilador, ressalvas, procedência, diálogo |
| Camada semântica | `semantics/` | EvoOntology ligado à ontologia formal: Termos com IRI e categoria BFO, fachada MCP, porta de validação (IRI, BFO, SHACL, raciocinador), trajetórias e o **ciclo de evolução** (`evolve.py`, `run_evolution.py`) |
| Avaliação | `eval/`, `tests/` | 6 conjuntos de perguntas com oráculo independente em pandas, mais um **conjunto independente congelado** (49 perguntas, `eval/run_independent.py`), estatística, ~1070 testes |

Versões do prompt (`--prompts`): `v1` só rótulos · `v2` correções do dev · `v3` ontologia no contexto · `v4` fundamentação na pergunta (L4), dicas, compilador de
reserva · `v5` = v4 + bloco da camada semântica · `v6` = v4 + forma do resultado (`group_by`, `attributes`, `order`) com consulta montada por código · `v7` = v6 + filtros com unidade explícita e consulta montada por código também para agregação simples, contagem com limiar e **dias com condição** (`daily`). **`v7` é o padrão da linha de comando e ainda NÃO foi medido com LLM real.**

## Perguntar (linha de comando)

```bash
python -m kgqa "Qual a temperatura média de SBGL em fevereiro de 2021?"     # precisa do Ontop no ar e do kgqa.env (chave fora do repositório)
python -m kgqa --show-query "Em SBLO, quantas horas de 2020 acumularam pelo menos 10 mm de chuva?"
python -m kgqa --interactive < perguntas.txt        # várias perguntas; --json devolve a resposta completa (contrato 0.2.1)
```
Mostra como entendeu a pergunta e pede confirmação quando houve suposição, responde com ressalvas e procedência, e recusa (`unsupported`) o que os dados não têm.
Cada pergunta custa centavos de LLM, limitados por `--budget` e pelo teto do ledger.

## Instalar e rodar

**Desenvolvimento (Windows ou Linux, sem o grafo real)**: roda ~920 testes; os que precisam do Ontop são pulados.
```bash
python -m venv .venv && .venv/Scripts/activate        # Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
```

**Grafo real (WSL/Linux, sem `sudo`)**: instala JDK 17, Ontop 5.5.0, driver JDBC e Python 3.12 (versões e SHA-256 fixados em `infra/setup_wsl.sh`).
```bash
bash infra/setup_wsl.sh && source ~/metdata/env.sh
PACK=<pasta com os .npz> bash infra/rebuild.sh        # ~28 min: carga, limpeza, PostgreSQL, chaves, Ontop
bash infra/verify.sh                                   # sobe o que estiver parado e roda a suíte inteira contra o grafo real
```
Os `.npz` saem de `ingest/pack.py` sobre os CSV (`python ingest/pack.py <csv> <saida.npz>`). Os dados reais nunca vão ao git (`.gitignore`).
O endpoint do Ontop **não tem autenticação**: o script o prende ao loopback (`SERVER_ADDRESS=127.0.0.1`); não mude isso.

**Medir com o LLM real** (gasta dinheiro; o teto acumulado fica em `eval/reports/spend_ledger.jsonl`, e passar dele exige `--authorize-usd`):
```bash
python -m eval.run_llm_pipeline --suite real_gen --prompts v6 --budget 0.8 --tag _x          # suítes: synthetic heldout fresh real real_fresh real_gen
python -m eval.stats eval/reports/llm_run_v4_real_gen_v4.json eval/reports/llm_run_v6_real_gen_v6.json,eval/reports/llm_run_v6_real_gen_v6_rg24.json   # IC e McNemar; vírgula = arquivos da MESMA condição (RG24 rodou à parte); perguntas diferentes entre condições dão erro
```
A chave vai em `OPENAI_API_KEY` no `kgqa.env` (fora do repositório). Nada é gasto por `pytest`.

**Verificação formal da ontologia e ciclo de evolução** (não gastam LLM):
```bash
bash ontology/imports/fetch.sh                        # instala o ROBOT (HermiT e validador de perfis OWL 2) em ~/tools/onto
python -m ontology.build_views                        # regera ontology/generated/ (um teste confere que está em dia)
python -m semantics.build --rebuild                   # refaz a camada semântica se a ontologia mudou
python -m semantics.run_evolution --seed-gold --require-reasoner --sample-graph     # minera, avalia Parent x Candidate, aceita ou rejeita (numa cópia)
```

## O que a medição mostra (e o que não mostra)

MVP (`metqa`) no conjunto independente novo_b_100_20261028_validado (100 perguntas, rodada única, 2026-10-31): 86/100 corretas
[IC95% 78–91%], 1 resposta errada entregue, 13 abstenções, US$ 0,032 e 9,5 s por pergunta (`docs/RESULTADOS_MVP_novo_b_100_20261028.md`).
O plano da versão final, que ataca as abstenções e os defeitos achados, está em `docs/PLANO_ARQUITETURA_FINAL.md`.

Medições antigas do legado:

Mesmo modelo, grafo real, uma execução por condição. **Com n tão pequeno, quase nenhuma diferença sai do ruído** (`eval/stats.py`):

| Conjunto | `v4` | `v6` | McNemar exato |
|---|---:|---:|---:|
| RF (16, escrito já conhecendo o v6) | 12/16 [IC95% 51–90%] | 16/16 [81–100%] | p = 0,12 |
| RG (24, com 2 sondas contra o v6) | 20/24 [64–93%] | 19/24 [60–91%] | p = 1,00 |

A única medida feita antes de se ver o resultado (split test do `v4`, 12 perguntas reais) deu **7/12 só pelo status** (RT12 teve o status certo com número errado); pela métrica das tabelas acima (status certo e valor certo) são **6/12**, e as duas frações não são comparáveis com as de RF/RG sem dizer qual é qual. Todos os conjuntos foram usados para corrigir regras, então
nenhum resta limpo. Detalhes: `docs/COMPARACAO_*.md`, `docs/ANALISE_CRITICA.md`.

## Mapa de documentos

`docs/ANALISE_CRITICA.md` (análise e plano) · `DECISOES.md` (cada decisão com motivo e como reverter) · `docs/REVISAO_CRITICA.md`, `ESTUDO_SEGURANCA_PIPELINE.md`
(rodadas anteriores) · `docs/EQUIVALENCIA_LOCALDATE.md` (equivalência medida) · `data/DICIONARIO_DADOS.md`, `data/REGRAS_LIMPEZA.md`.
