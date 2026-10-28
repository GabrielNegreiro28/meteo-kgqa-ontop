# Entendimento verificado por concordância e pelo usuário (sem gramática de regex)

## Contexto

A medição no `novo_a_20261028` mostrou o limite do caminho atual. O MVP (`metqa/`) entende o tempo e os números com uma gramática
de regex escrita à mão (`pipeline/spans.py`, 24 padrões; `pipeline/reconcile.py`). Em 50 perguntas novas apareceram duas formas que
ela não conhecia:
- "no ano de 2018." (ano antes de pontuação);
- "das 18h às 6h" (intervalo de horas).

Elas derrubaram 8 perguntas. A trava evitou que virassem resposta errada, mas cada forma nova pediria uma regra nova, e o conjunto de
formas de escrever é infinito. O legado (`pipeline/validators.py`, 31 padrões) tem o mesmo problema, e é ele que deixa passar "dia 13 de
março" como março inteiro.

**Objetivo.** Uma arquitetura em que a **correção do entendimento não depende de prever as formas de escrever**. Ela:
- **delega a linguagem ao LLM**, que é bom nisso, inclusive em normalizar datas, horas e unidades;
- **detecta a dúvida por mecanismos genéricos**: concordância entre leituras independentes e verificação contra o mundo fechado da
  ontologia, sem regras por frase;
- **resolve a dúvida com o usuário**: mostra exatamente o que vai consultar e pergunta quando há risco;
- **aprende com os dados**: cada caso de borda confirmado ou corrigido pelo usuário vira um exemplo verificado, não uma regra nova.

Isso é o que o documento do professor prescreve: "o resultado é validado antes do roteamento… se falhar de novo, o sistema faz uma
pergunta de esclarecimento" (§8); "entidades que não se resolvem com confiança viram pergunta, nunca são adivinhadas" (§8);
"correções do usuário" como sinal de evolução (§13).

---

## 1. Princípio: separar o que é aberto do que é fechado

| Natureza | Exemplos | Quem decide | Como se garante |
|---|---|---|---|
| **Aberto** (linguagem: infinitas formas) | "no ano de 2018.", "das 18h às 6h", "verão passado de 2022", gírias, erros de digitação | **LLM** | redundância (duas leituras independentes) + o usuário vê e confirma + memória de exemplos verificados |
| **Fechado** (mundo finito, definido pela ontologia e pelos dados) | grandezas e IRIs, agregações permitidas, unidades e dimensões, estações, cobertura temporal, horas 0–23, datas válidas | **código** | validação determinística contra o Catálogo (número finito de checagens, que não cresce com as perguntas) |

Nenhuma regra do lado fechado olha para a forma de escrever: elas olham para **valores já normalizados**, como "2018-01-01 a 2018-12-31",
"horas {18…23, 0…5}" ou "unit:PERCENT". É isso que tira as regex do caminho da pergunta.

---

## 2. Fluxo de uma pergunta

```
pergunta
  │
  ▼
[1] Recuperar exemplos verificados parecidos (memória)     ── similaridade de texto, sem gramática
  │
  ▼
[2] Duas leituras INDEPENDENTES pelo LLM ──► IR normalizada A e IR normalizada B
  │     (prompts com enquadramentos diferentes; o LLM normaliza datas, horas, unidades e cita a evidência de cada campo)
  ▼
[3] Validação no mundo fechado (Catálogo) ──► defeito estrutural? uma rodada de reparo
  │
  ▼
[4] Concordância: A == B campo a campo (forma canônica)?
  │
  ▼
[5] Política de confirmação (risco)
  │   concordam e risco baixo ─────────────► segue (e mostra "Entendi assim", com convite a corrigir)
  │   discordam / risco alto ──────────────► PERGUNTA ao usuário:
  │        - leituras diferentes  → "Você quis dizer (1) … ou (2) …?" (gerado do diff, determinístico)
  │        - uma leitura arriscada → "Entendi assim: … Está certo?"
  │        usuário confirma / escolhe / corrige em texto livre → nova leitura com a correção → volta a [3]
  │   sem usuário (lote, API) ─────────────► needs_clarification com as paráfrases como alternativas (nunca chuta)
  ▼
[6] Planejar → compilar → executar → verificar → responder   (já existem no metqa/; inalterados)
  ▼
[7] Registrar: interpretação confirmada ou corrigida pelo usuário → exemplo verificado (memória) + trilha para a evolução
```

---

## 3. Componentes

### 3.1 IR normalizada (`metqa/understanding/schema.py`)

O LLM devolve a consulta canônica **já normalizada**, num esquema JSON estrito e validado por código:

```json
{"status": "ok" | "needs_clarification" | "unsupported",
 "measure": "met:Precipitation",
 "stations": ["st:SBGL"],
 "time": {"ranges": [{"start": "2024-02-15", "end": "2024-02-15"}],     // 1 faixa; 2 = comparação de períodos
          "local_hours": [0,1,2,3,4,5] | null,                          // conjunto: atravessa a meia-noite sem caso especial
          "weekdays": [5,6] | null, "instant": "2021-03-10T15:00:00-03:00" | null},
 "calc": {"aggregation": "sum", "count_of": "readings|hours|days|reports" | null,
          "daily": {"agg": "max", "op": ">", "value": 35, "unit": "unit:DEG_C"} | null},
 "conditions": [{"op": "<", "value": 40, "unit": "unit:PERCENT"}],
 "shape": {"group_by": [], "order": null, "attributes": []},
 "evidence": {"measure": "choveu", "time": "no dia 15 de fevereiro de 2024", "calc": "quanto", "conditions.0": "abaixo de 40%"},
 "assumptions": ["sem estação na pergunta: todas"], "alternatives": [], "reason": ""}
```

- Converte para a `CanonicalQuery` que já existe (`metqa/domain/types.py`). `TimeScope.hours` passa a ser conjunto de horas e
  `scope` passa a aceitar até 2 faixas.
- **Sai do caminho:** `pipeline/spans.py` e `pipeline/reconcile.py`. Continuam no repositório para o legado e para comparações.

### 3.2 Validação no mundo fechado (`metqa/verification/pre.py`, ampliada)

Só checagens sobre **valores**, todas finitas e definidas pelo Catálogo:
- esquema e tipos;
- IRI da grandeza e das estações existem;
- agregação admitida;
- dimensões e atributos da grandeza;
- `count_of` coerente com a agregação;
- datas válidas e `start ≤ end`;
- horas em 0–23 e dias da semana em 0–6;
- cobertura temporal e grandeza com dados;
- **análise dimensional**: a unidade de cada condição é conversível para a unidade canônica da grandeza (tabela do Catálogo). "40 %"
  numa grandeza em °C é defeito estrutural, sem regex.

Falha estrutural vira uma rodada de reparo com a mensagem. Se persistir, vira esclarecimento. Reaproveita as regras L2/L3 de
`pipeline/validators.py` (`_schema`, `_structure_rules`) e `vocab.convert_filter_value`.

### 3.3 Duas leituras independentes e concordância (`metqa/understanding/crosscheck.py`)

- **Leitura A:** prompt direto ("devolva a IR"). **Leitura B:** prompt com outro enquadramento ("primeiro reescreva a pergunta numa frase
  canônica completa; depois a IR"), com o exemplo e a ordem do cardápio variados.
- Comparação **estrutural** depois da canonicalização (listas ordenadas, unidades convertidas para a canônica, datas como intervalo): o
  resultado é um `diff` por campo (`time.ranges`, `calc.aggregation`, `conditions`…).
- **Concordar não prova acerto**, porque erros correlacionados existem. Por isso o usuário sempre vê a paráfrase e pode corrigir depois
  (3.5). Mas **discordar prova dúvida**, sem nenhuma regra sobre a frase. É o detector genérico que substitui as regex.
- **Custo:** uma chamada a mais por pergunta (~US$ 0,01). O MVP atual custa ~US$ 0,012 por pergunta, e o v7 ~US$ 0,022.
- Configurável: `readings=1` desliga, para medir a contribuição da concordância (ablação).

### 3.4 Política de confirmação (`metqa/dialogue/policy.py`)

Risco calculado **a partir da IR e das leituras, não da frase**:

| Sinal | Por quê |
|---|---|
| as duas leituras divergem em algum campo | dúvida real de interpretação |
| campo sem evidência citada, ou evidência que não está na pergunta (comparação literal de substring) | decisão sem base no texto |
| número da pergunta não usado em nenhum campo | uma restrição pode ter caído |
| valores assumidos por padrão (sem estação = todas; sem período = todo o histórico) | o usuário pode não ter querido isso |
| nenhum exemplo verificado parecido na memória | forma ainda não vista |

O número sem uso vem de um tokenizador único (`\d+([.,]\d+)?`). Não é gramática: ele não tenta entender o número, só garante que nenhum
foi ignorado.

Modos (`Settings.confirm`):
- `risk` (padrão): pergunta quando há sinal.
- `always`: pergunta sempre.
- `never`: sem usuário. Com risco, devolve `needs_clarification` com as paráfrases, nunca chuta.

### 3.5 Paráfrase e diálogo (`metqa/dialogue/`)

- **Paráfrase determinística da IR** (`paraphrase.py`): o que o usuário lê é exatamente o que vai ser consultado. Por exemplo: "Soma da
  precipitação em SBGL em 15/02/2024 (dia inteiro, horário de Brasília)". Reaproveita `TimeScope.describe` e os textos de
  `metqa/presentation/render.py`.
- **Pergunta por diff** (`question.py`): com leituras diferentes, mostra só o que difere ("(1) só o dia 15/02/2024 ou (2) fevereiro de
  2024 inteiro?").
- **Canal do usuário** (porta `UserChannel`):
  - `TerminalChannel` na linha de comando;
  - `ScriptedChannel` nos testes (reaproveita `pipeline/dialogue.py::ScriptedUser`);
  - `NoChannel` na API e no lote: devolve `needs_clarification` com `details = {paraphrases, options, interpretation_id}`. O cliente
    reenvia com a opção escolhida e a IR confirmada é executada sem nova chamada ao LLM.
- **Resposta do usuário:** "sim", "não", "cancelar" e o número da opção pelo classificador existente (`pipeline/dialogue.py::
  classify_reply`, conjunto fechado de palavras). Texto livre é **correção**: nova leitura do LLM com a IR anterior e a correção
  (padrão já testado no `eval/run_dialogue_experiment.py`: 10/10 cenários), limitada a 3 voltas.
- **Correção depois da resposta:** toda resposta termina com "Entendi assim: …; se não for isso, diga o que corrigir". A correção reabre o
  ciclo pela mesma porta.

### 3.6 Memória de exemplos verificados (`metqa/knowledge/exemplars.py`)

- **O que guarda:** (pergunta, IR confirmada, quem verificou: `user` | `oracle`, data, versão do Catálogo), no workspace do EvoOntology
  como Evidência (§7.2: "evidência de uso correto"). Só entra o que foi **confirmado pelo usuário** ou **conferido contra um oráculo**,
  nunca a saída não verificada do LLM.
- **Recuperação:** similaridade de texto (TF-IDF de n-gramas de caracteres, cosseno), top-3 como exemplos no prompt das duas leituras. É
  determinística e não tem gramática.
- **Efeito:** um caso de borda corrigido uma vez ("das 18h às 6h") volta como exemplo nas perguntas parecidas, **sem código novo**.
  "Existe exemplo parecido" também baixa o risco da política.
- **Governança:** o conjunto de exemplos é conteúdo da camada evolutiva. Entra no ciclo existente (`semantics/evolve.py`: Candidate →
  porta → avaliação pareada → publicar), e exemplos ruins são removíveis e versionados.

### 3.7 O que não muda

Catálogo, léxico (`metqa/knowledge/`), planejador, compilador, executor, verificação pós, apresentação, procedência, ledger, contrato
0.2.1 e a camada formal (BFO, Ontop, SHACL, HermiT) seguem como no MVP. Ajustes:
- **Compilador:** passa a aceitar o **conjunto** de horas locais. `pipeline/compiler.py::day_filters` hoje recebe `[h0, h1)`, e a mudança
  é pequena.
- **Comparação:** passa a vir de `time.ranges` com 2 faixas.

---

## 4. Arquivos

| Novo ou alterado | Arquivo | Papel |
|---|---|---|
| novo | `metqa/understanding/prompts.py` | prompts das leituras A e B (IR normalizada, cardápio, exemplos) |
| novo | `metqa/understanding/schema.py` | validação do JSON e conversão IR → `CanonicalQuery` |
| novo | `metqa/understanding/crosscheck.py` | duas leituras, canonicalização, diff |
| novo | `metqa/dialogue/{policy,paraphrase,question,channel}.py` | risco, paráfrase, pergunta por diff, portas do usuário |
| novo | `metqa/knowledge/exemplars.py` | memória de exemplos verificados (gravação, recuperação, versão) |
| alterado | `metqa/understanding/interpreter.py` | uma leitura = uma chamada, parametrizada pelo enquadramento |
| alterado | `metqa/app/pipeline.py` | estágios [1]–[5] e [7] no lugar de leitor + conciliação |
| alterado | `metqa/domain/types.py` | `TimeScope.hours` como conjunto; até 2 faixas |
| alterado | `metqa/verification/pre.py` | checagens de valores (datas, horas, dimensões) |
| alterado | `metqa/app/{settings,cli}.py` | `confirm`, `readings`, `exemplars`; diálogo no terminal |
| alterado | `eval/run_independent.py`, `eval/run_dialogue_experiment.py` | modos autônomo e com usuário simulado |
| fora do caminho | `pipeline/spans.py`, `pipeline/reconcile.py` | legado (comparação histórica) |

---

## 5. Como medir (honesto sobre o que cada modo mede)

1. **Modo autônomo (`confirm=never`)** num conjunto **novo** (50 perguntas da outra IA, como antes):
   - respostas erradas entregues;
   - acerto adjudicado;
   - **taxa de pergunta ao usuário**, o custo da segurança. Meta: no máximo 30% das respondíveis;
   - custo.

   Comparar com o MVP atual (regex) e o v7 no mesmo conjunto.
2. **Ablações:** `readings=1` × `2` (contribuição da concordância) e exemplos ligados × desligados.
3. **Com usuário simulado:** um LLM-usuário recebe a pergunta e as premissas declaradas do oráculo (`assumptions`) e responde "sim" ou
   corrige. Mede voltas até convergir e o acerto final. É simulação, e isso é dito.
4. **Sessão real curta com você (10 perguntas):** usabilidade da pergunta de confirmação, que nenhuma métrica automática mede.

Ordem de custo: itens 1 e 2, cerca de US$ 2–3. Item 3, cerca de US$ 1.

---

## 6. Riscos

- **Erros correlacionados:** as duas leituras podem errar igual. Mitigação: enquadramentos diferentes, a paráfrase sempre mostrada,
  correção depois da resposta e a memória. Com outro modelo disponível, a leitura B pode usar outro modelo.
- **Perguntar demais irrita:** a taxa de pergunta é medida e a política é ajustável. Os exemplos verificados reduzem a taxa com o uso.
- **Sem usuário (lote, API),** risco alto vira esclarecimento, nunca palpite. A taxa aparece na medição.
- **O LLM normalizando datas pode errar a aritmética** (fim de mês, ano bissexto). A validação de valores pega datas inválidas. Datas
  válidas mas erradas são exatamente o que a concordância e o usuário pegam.

---

## 7. Verificação

- **Testes sem rede:**
  - LLM roteirizado com leituras que concordam → segue;
  - leituras que divergem → pergunta por diff;
  - usuário roteirizado confirma, escolhe opção e corrige em texto;
  - `NoChannel` → `needs_clarification` com opções e reexecução pela IR confirmada;
  - validação dimensional;
  - horas atravessando a meia-noite;
  - memória (só exemplos verificados entram; recuperação; efeito no risco).
- **Grafo real, LLM roteirizado:** os 11 casos de `tests/test_v8_real.py` e os 10 de `tests/test_metqa_real.py` reescritos como IR
  normalizada. Mais "das 18h às 6h" e "no ano de 2018." contra pandas.
- **Sem regex de linguagem no caminho:** um teste garante que `metqa/` não importa `pipeline.spans` nem `pipeline.reconcile`.
- Suíte completa verde. Depois, a medição da seção 5 num conjunto novo.

---

## 8. Estado da implementação (2026-10-28)

- **Implementado em `metqa/`:**
  - `understanding/` com `prompts.py`, `interpreter.py`, `schema.py` e `crosscheck.py`;
  - `dialogue/` com `policy.py`, `paraphrase.py` e `channel.py`;
  - `knowledge/exemplars.py`;
  - `app/pipeline.py` reescrito;
  - `verification/pre.py` com análise dimensional;
  - horas como conjunto no compilador.
- **Fora do caminho do `metqa`:** `pipeline/spans.py` e `pipeline/reconcile.py`. Um teste garante isso.
- **Testes:**
  - `tests/test_metqa.py`: 20 testes sem rede (concordância, divergência, escolha, correção, cancelamento, confirmação pela API, sinais
    fortes, análise dimensional, horas atravessando a meia-noite, comparação, instante, memória, léxico, ausência de gramática);
  - `tests/test_metqa_real.py`: 10 testes no grafo real, inclusive os dois casos de borda da medição de 2026-10-28, sem regra para eles;
  - suíte completa: 1056 testes passaram.
- **Falta:** medir com o LLM real num conjunto **novo** (seção 5).
