# Arquitetura final do módulo de consulta ao grafo (metqa)

## Contexto

A arquitetura do MVP (`docs/ARQUITETURA_MVP.md`, pacote `metqa/`) foi medida em 2026-10-31 nas 100 perguntas do `novo_b` (commit 3b09a69):
- 85/100 com o comportamento certo, 14 abstenções e 1 resposta indevida (E131);
- nenhum número errado por defeito de consulta, e as 7 divergências numéricas vieram de limpeza ou definição;
- custo de US$ 0,032 por pergunta, 9,5 s por pergunta.

A revisão e a rodada mostraram o que falta para a versão final:
1. O risco central não foi fechado. A checagem de evidência confirma que o trecho está na pergunta, mas não que o valor saiu dele: "dia 3 de março" pode virar o mês inteiro nas duas leituras e passar.
2. Metade das abstenções é evitável:
   - 6 são alarmes falsos de confirmação (evidência citada com aspas ou paráfrase, divergência de status);
   - 3 são comparações recusadas;
   - 3 são base de nuvem, que está no grafo mas não é grandeza;
   - 1 é o limite de 6000 caracteres no filtro de dias da semana.
3. Há defeitos de apresentação e de status reproduzidos:
   - comparação de dias usa o `n`;
   - "diferença de 10 °C" numa contagem;
   - "5 m" no lugar de 5 km;
   - ano saindo como "2.016";
   - dois atributos com o mesmo valor;
   - contagem 0 com status `no_results`.
   A causa comum é que o texto e o verificador adivinham o papel de cada coluna pelo nome.
4. O `metqa` ainda depende do legado (`pipeline/`, `kgqa/`, `semantics/`):
   - 31 dos 49 arquivos de teste só exercitam o legado;
   - o conhecimento do domínio está espalhado em cerca de 9 lugares.
5. A EvoOntology está no caminho, mas a evolução só aprende sinônimos. Ela também não lê bem as trilhas do `metqa`, e a avaliação não guarda trilha.

Objetivo: levar o módulo ao estado final da proposta (`gabriel-2026-arquitetura-inicial.pdf`) sobre a fonte real, com:
- um único caminho de execução, sem o legado;
- correção do entendimento conferida por mecanismos genéricos, sem gramática de regex;
- contrato pronto para o roteador do sistema do professor.

O plano serve para guiar a implementação, em fases com critério de aceite.

## Princípios que se mantêm

- O LLM faz a linguagem e normaliza. O código confere o mundo fechado (ontologia, catálogo, unidades, cobertura).
- O SPARQL só sai do compilador, e o texto da resposta só sai de código.
- Falhar fechado: toda parada tem `Status` e motivo.
- Portas e adaptadores: LLM, fonte SPARQL, léxico, canal do usuário, memória e trilha.
- Dependências em uma direção só: `app → understanding/planning/execution/verification/presentation → knowledge → domain`.

## Visão do fluxo final

```
pergunta
 → memória de exemplos verificados (versionada com a camada)
 → 2 leituras do LLM, em paralelo
 → esquema
 → verificação no mundo fechado
 → conservação da evidência (NOVO)
 → concordância + política de risco → [usuário | opções devolvidas]
 → planejador (N partes de mesma forma)
 → compilador → ResultShape (NOVO)
 → executor (regras + motor + Ontop)
 → verificador-pós guiado pelo ResultShape
 → texto determinístico + "Entendi assim" + ressalvas + PROV-O
 → trilha completa (sempre, também na avaliação) + exemplo verificado
 → (em lote) evolução EvoOntology
```

## Decisões de arquitetura (o que muda)

### D1. Conservação da evidência: liga o valor ao trecho
Fecha o risco de as duas leituras errarem juntas. São dois mecanismos genéricos, sem regra por frase.

a) Números conservados por campo (determinístico). Todo número citado na evidência de um campo precisa aparecer no valor normalizado desse campo. Exemplos:
- tempo: dia, mês ou ano das datas, horas, instante;
- condições: o valor do limiar;
- forma do resultado: o limite do ranking.

Assim, "dia 3 de março de 2021" com a janela 2021-03-01..2021-03-31 viola a regra (3 não está em nenhum dos extremos da janela) e gera um sinal forte. Isso generaliza o tokenizador de números que já existe em `metqa/dialogue/policy.py:48`, que hoje só confere se o número foi citado.

b) Releitura isolada do trecho (LLM, barata e opcional por configuração). Só o trecho de tempo é renormalizado numa chamada curta, sem a pergunta e sem os exemplos, e o resultado tem de bater com `time` das leituras. O contexto diferente reduz a correlação de erros.

Ligado por padrão:
- (a) sempre;
- (b) só quando a janela tem mais de um dia ou o trecho tem palavra de calendário.

Ablação prevista para medir o efeito.

Arquivos:
- novo `metqa/understanding/evidence.py`;
- chamada em `metqa/app/pipeline.py::_understand`;
- sinais em `metqa/dialogue/policy.py::assess`.

### D2. Evidência tolerante na forma, rígida no conteúdo
Corrige os alarmes falsos de E87, E94 e E141.
- A comparação de trecho ignora aspas, pontuação, caixa e acento, e aceita contenção por tokens com ordem preservada.
- A evidência da grandeza (`measure`) é conferida pelo léxico, não pelo texto literal: basta que o `Lexicon.lookup` resolva algum trecho da pergunta para o IRI escolhido. Assim "duração da chuva" é aceita via sinônimo.
- Divergência de `status` em que uma leitura é `ok` e a outra falhou por erro de LLM não é divergência: segue com a leitura válida e anota fraqueza.

### D3. ResultShape: o compilador declara o papel de cada coluna
`compile_query` passa a devolver `CompiledQuery(sparql, shape)`, em que `shape` diz:
- a coluna do valor e a do `n`;
- a semântica do `n` (leituras, dias com dados, instantes);
- a coluna da contagem quando o valor é contagem;
- as chaves de grupo e seus tipos (ano, mês, dia, estação, atributo);
- as colunas de atributo, a unidade do valor e se o valor é medida ou contagem.

Quem consome:
- `verify_post`: o status vem do shape. `n` = 0 é `no_results`; contagem 0 com dados é `answered`; SUM coalescido com `n` = 0 é `no_results`.
- `render`: escolhe o número e a unidade pelo shape:
  - contagem não tem unidade;
  - ano é inteiro, sem separador de milhar;
  - atributos saem um por coluna;
  - o limiar sai na unidade do usuário;
  - a comparação usa a coluna de valor.
- `eval.run_independent`: grava o shape.

Isso substitui `kgqa/verify.py::result_status`, que adivinha pelo nome da variável.

Arquivos:
- `metqa/domain/types.py` (novos `CompiledQuery` e `ResultShape`);
- `metqa/planning/compiler.py`;
- `metqa/verification/post.py`;
- `metqa/presentation/render.py`;
- `metqa/dialogue/paraphrase.py`.

### D4. Tempo local no grafo, não no compilador
O mapeamento OBDA ganha `met:localHour` e `met:localWeekday`, calculados no PostgreSQL a partir de `t_local`, e é regerado por `mapping/build_mapping.py`.
- O compilador filtra direto: `FILTER(?wd IN (5,6))` e `FILTER(?h IN (...))`.
- Isso elimina a lista de datas (o defeito do limite de 6000 caracteres, E149) e a conversão UTC+3 em `pipeline/compiler.py:153-171`.
- Contar horas distintas passa a usar `(?d, ?h)` locais.

Sem recarga de dados: basta regerar o OBDA e reiniciar o Ontop. A equivalência com a forma atual é medida como em `eval/equivalencia_localdate.py`.

### D5. Planejador de N partes de mesma forma
A comparação passa a aceitar:
- de 2 a 4 períodos para uma estação, ou de 2 a 4 estações para um período, com qualquer agregação simples ou contagem (inclusive `daily`);
- "a mesma série em dois anos" normalizada para uma série agrupada (por exemplo `group_by year` com filtro de mês), quando a forma pedida é "o mês X em cada ano".

A combinação em código usa a coluna de valor do ResultShape e dá a diferença na unidade certa.

Antes de desenhar a normalização, mede-se a causa real de E111, E113 e E114: elas são rodadas de novo com a trilha gravada (D9), sem mudar regra, só para diagnóstico.

Arquivos: `metqa/planning/planner.py`, `metqa/presentation/render.py::_compare`.

### D6. Catálogo de Domínio como fonte única (dados, mapeamento, ontologia, MVP)
- Uma tabela única de grandezas gerada da ontologia (`ontology/met.ttl` + `met-structure.ttl`) com:
  - IRI, coluna e tabela de origem;
  - unidade canônica, símbolo e dimensão;
  - fatores de conversão, faixa física, agregações, atributos e forma do tempo.
- Passam a consumi-la:
  - `ingest/constraints.py`, `ingest/export_pg.py` e `ingest/transform.py` (faixas);
  - `mapping/build_mapping.py`;
  - `ontology/shapes.ttl` (gerado);
  - `metqa/knowledge/catalog.py`.
- Divergências que desaparecem:
  - KiloM e OKTA sem símbolo;
  - faixas de QNH e temperatura diferentes entre a ingestão e o SHACL;
  - `UNIT_FACTORS` só com km→m.
- Novas grandezas da camada de nuvens:
  - `met:CloudBaseHeight` (m), observável por camada, com o atributo `met:cloudGenus`;
  - `met:CloudOktas` (oitavos).

  Isso cobre E55, E81 e E93. Como muda a ontologia formal, entra como proposta para a equipe de ontologia, no mesmo fluxo de `proposals/pending.json`. O alinhamento BFO continua provisório.
- Teste de fonte única: nenhuma tabela de grandeza, unidade ou faixa fora do catálogo (busca no código).

### D7. Diálogo e memória corretos
- "Sim" diante de uma escolha entre opções: responde pedindo o número, sem chamar o LLM de novo (`metqa/app/pipeline.py:193`).
- Respostas que repetem a mesma correção não geram nova rodada.
- `confirmed` pela API passa a exigir um token de confirmação: o hash das opções devolvidas, da pergunta e da versão do catálogo. Sem isso, um cliente poderia gravar qualquer interpretação como "verificada".
- A memória de exemplos fica versionada com a camada:
  - ela fica em `.evoontology/versions/<v>/exemplars.jsonl`, com a impressão digital da ontologia;
  - um exemplo pode ser substituído por correção posterior (`superseded_by`);
  - removê-lo é auditável;
  - a busca ignora exemplos de outra versão do catálogo.

### D8. Leituras em paralelo e custo
- As duas leituras rodam em paralelo, com um pool de 2 threads.
- `ResilientLLM` e `LedgerLLM` ganham um lock em `spent_usd` e no disjuntor (hoje não são seguros entre threads, segundo o mapeamento).
- Meta: latência de cerca de 5 s por pergunta.
- Custo:
  - o cardápio é enxugado (só as grandezas candidatas, mais um resumo das outras) e é medido;
  - meta de custo menor ou igual ao do v7 (US$ 0,022 por pergunta), com a releitura de D1(b) incluída.

### D9. Trilha completa sempre, e evolução que lê o metqa
- O `metqa` emite os eventos que `semantics/trajectories.py` entende: `end` (com a versão da ontologia), `execute` e `interpretation.properties` como IRI completo. Também passam a ser registrados `crosscheck`, `evidence` e `exemplar_recorded`.
- `eval/run_independent.py` grava a trilha de cada pergunta (JSONL ao lado do relatório, em `eval/reports/`) e a trajetória com `split="eval"`, que nunca é minerada.
- A evolução ganha dois sinais novos:
  - correções do usuário e escolhas entre opções, que viram candidatos a sinônimo e a exemplo;
  - palavras sem cobertura em perguntas que terminaram em esclarecimento.
- O ciclo continua só com sinônimos automáticos. Mudança de relação, restrição ou grandeza vira proposta para revisão humana, como hoje.
- A avaliação pareada da evolução ganha o modo "metqa inteiro" num conjunto congelado (com custo e teto do ledger), além do modo barato atual (`semantics/resolution.py`).

### D10. Contrato para o roteador
- API de biblioteca: `MetQA.ask(question, user=None, confirmation=None) -> QueryResponse` (contrato 0.2.1, mais `result_shape` e `confirmation_token`, o que eleva a versão para 0.3.0).
- `MetQA.capabilities() -> dict`:
  - grandezas com dados, unidades e cobertura;
  - formas de pergunta suportadas;
  - limites (partes, linhas, tempo).

  É o que o roteador do sistema do professor consulta para decidir se manda a pergunta para este módulo.
- Linha de comando continua (`python -m metqa`). Servidor HTTP fica fora do escopo e pode ser uma camada fina depois.

### D11. Fim do legado
O `metqa/` passa a conter o que usa:

| Novo módulo | Origem |
|---|---|
| `metqa/knowledge/index.py` | `vocab.OntologyIndex` e conversões |
| `metqa/verification/rules.py` | Só a parte de `validators.py` que roda com `question=None` e `validate_query`, com `query_facts` |
| `metqa/planning/compiler.py` | `compile_structured` |
| `metqa/verification/caveats.py` | `caveats.py` |
| `metqa/llm/` | `llm.py`, `ledger.py`, `openai_client.py` |
| `metqa/presentation/provenance.py` | `provenance.py` |
| `metqa/execution/store.py` | `kgqa/store.py` |
| `metqa/domain/contract.py` | `kgqa/contract.py` |
| `metqa/util/text.py` | `textsafe.py` |

- `pipeline/` (v1–v8), `kgqa/__main__.py` e os 31 testes só de legado ficam na tag `legado-v8` e saem da árvore.
- Antes de remover, os testes que cobrem código mantido (`test_compiler_differential`, `test_ontop_dialect`, `test_localdate`, `test_openai_client`) são portados.
- `semantics/` fica como pacote de evolução. `facade.py` deixa de importar de `build.py`, ou `build.py` fica.
- `eval/` mantém só a cadeia `freeze_set → validate_set → run_independent → judgment_sheet → adjudicate → stats`. Os oráculos por suíte e `run_llm_pipeline` saem com o legado.

## Fases de implementação

Cada fase termina com `pytest` verde no Windows e a suíte do grafo real verde no WSL (`bash infra/verify.sh`).

Fase 0, arrumação (sem custo):
- commitar `eval/frozen/novo_b_100_20261028_validado` e os relatórios de resultado em `docs/`;
- registrar os vereditos do `novo_b` em `docs/julgamento_novo_b_..._veredictos.yaml` e rodar `eval.adjudicate`;
- tirar `API Key.txt` do alcance do repositório da Área de Trabalho;
- dar push;
- atualizar o README com o estado medido.

Fase 1, ResultShape e defeitos de texto e status (D3), sem LLM:
- cada defeito reproduzido vira teste antes da correção: comparação de dias, unidade da diferença, km, ano, dois atributos, contagem 0, SUM vazio, cobertura parcial (ressalva quando a janela passa da cobertura);
- teste no grafo real para cada um com LLM roteirizado (padrão de `tests/test_metqa_real.py`).

Fase 2, tempo local no grafo (D4):
- `met:localHour` e `met:localWeekday` no OBDA;
- novo compilador de partes do dia e dias da semana;
- equivalência medida contra a forma atual;
- o caso E149 passa no grafo real.

Fase 3, entendimento (D1, D2, D7, D8):
- conservação da evidência;
- evidência tolerante;
- correções do diálogo e token de confirmação;
- leituras em paralelo com locks;
- testes sem custo:
  - "dia 3 → mês" vira sinal forte;
  - E87, E94 e E141, reescritas com o LLM roteirizado, deixam de pedir confirmação;
  - "sim" numa escolha não chama o LLM.

Fase 4, catálogo como fonte única e nuvens (D6):
- tabela única;
- ingestão, mapeamento e SHACL gerados a partir dela;
- grandezas de nuvem atrás de decisão do professor;
- conformância (`ontology/conformance.py`) e HermiT verdes.

Fase 5, planejador de N partes (D5), depois do diagnóstico de E111, E113 e E114 com trilha.

Fase 6, trilha e evolução (D9) e contrato (D10):
- `capabilities()`;
- contrato 0.3.0;
- `run_evolution` com o metqa inteiro.

Fase 7, fim do legado (D11):
- mover módulos, portar testes, tag `legado-v8`, remover;
- teste de que `metqa/` não importa `pipeline`, `kgqa` nem `semantics` (exceto pela porta do léxico e da evolução).

Fase 8, medição final:
- conjunto novo `novo_c` (100 a 120 perguntas, outro gerador, congelado e commitado antes de rodar);
- condições:
  - `metqa` final;
  - ablações: 1 leitura, sem conservação de evidência, léxico formal;
  - o v7 de referência, rodado antes da Fase 7 a partir da tag;
- adjudicação com revisão humana;
- McNemar;
- custo autorizado no ledger (ordem de US$ 8 a 12 para as 5 condições).

## Critério de aceite da arquitetura final (Fase 8)

- Erros entregues: 0 por defeito de tempo, unidade, filtro, contagem ou apresentação. Taxa de erro entregue com IC95% superior abaixo de 4%.
- Abstenções nas respondíveis: no máximo 8%, e todas com motivo.
- Toda pergunta não respondível: recusada ou esclarecida, nunca respondida.
- Custo por pergunta: no máximo o do v7. Latência mediana: no máximo 6 s.
- Dependências: `metqa/` sem dependência do legado; um só lugar define grandezas, unidades e faixas.

## Verificação ponta a ponta

- Sem custo, em toda fase:
  - `.venv/Scripts/python.exe -m pytest -q` no Windows;
  - no WSL: `wsl.exe -d Ubuntu -e bash -lc 'source ~/metdata/env.sh; cd <repo>; bash infra/verify.sh'` (o Ontop só responde dentro do WSL).
- Sondas com LLM roteirizado e linhas falsas, como as da revisão (scripts no scratchpad), viram testes permanentes em `tests/test_metqa_shapes.py` e `tests/test_metqa_understanding.py`.
- Com custo, só na Fase 8: `python -m eval.run_independent --set novo_c_... --prompts metqa --tag _1` (e as ablações) no WSL, seguido de `eval.judgment_sheet`, `eval.adjudicate` e `eval.stats`.

## Decisões que dependem do professor (marcadas, não bloqueiam as Fases 0–3)

- Grandezas de nuvem na ontologia formal (D6).
- Política de leituras duplicadas: média por instante ou todas as leituras (E60 e E102 dependem disso). A resposta passa a declarar a política em uso.
- Descarte de picos isolados (Q3/Q5), que muda rankings (E105, E99).
- Fuso UTC−3 fixo para todas as estações (D-85).
