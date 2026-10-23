# Análise crítica do módulo KGQA sobre o grafo de meteorologia

Base: a arquitetura "Ontology-Grounded Agentic Architecture" (Parente, rev. 13/10/2026) e a fatia atribuída: o trajeto completo para a **consulta em grafo**
(interpretar, validar, consultar o grafo virtual do Ontop, verificar, responder, com BFO e EvoOntology como camada semântica). Escopo da varredura: `kgqa/`,
`pipeline/`, `semantics/`, `eval/`, `ingest/`, `mapping/`, `infra/`, `ontology/`, `data/`, `tests/` (≈7,2 mil linhas de código; 575 testes no início da varredura, 914 ao fim) e os próprios dados.

Cada afirmação marcada **[medido]** foi verificada nesta rodada, no código ou nos dados. As demais são leitura do código ou do documento. A coluna final diz o que foi tratado.

## 0. Veredito

**O que está sólido.** A parte *formal e determinística* da proposta funciona e foi medida: grafo virtual sobre 105 mi de observações com 15/15 consultas de referência iguais
ao oráculo; validação em camadas (L1 a L5) que barrou famílias inteiras de erro silencioso; consulta montada por código onde a forma da resposta é determinada; execução
somente leitura; trilha de auditoria; controle de gasto acumulado.

**O que está fraco, em uma frase.** O que o professor propõe como *contribuição central* (EvoOntology evoluindo uma camada semântica ancorada na BFO) **não tem efeito
mensurável nas respostas hoje**, e a evidência de que o sistema generaliza é mais fraca do que os placares sugerem.

Três fatos que sustentam isso:
1. O prompt mais capaz (`v6`) **não usa a camada semântica**: ela só aparece no `v5`, que nunca foi medido. Não existe laço de evolução, nem trajetórias exportadas, nem proposta para a camada formal.
2. Na única medida em que tudo foi decidido antes de ver o resultado, o `v6` tem a **mesma contagem** do `v4` (15/19 corretas nos dois; 19/24 contra 20/24 no total; McNemar p = 1,00, o que não demonstra equivalência) e erra de forma mais grave em um caso (RG19). O 16/16 do conjunto anterior favorecia o `v6` por construção.
3. Todo conjunto de perguntas foi escrito pela mesma pessoa que escreveu as regras, o oráculo e as consultas de referência, e cada um foi "queimado" depois de usado para corrigir regras.

## 1. Fidelidade à arquitetura do professor

| Seção | Pedido | Estado | Severidade | Tratada agora |
|---|---|---|---|---|
| §6.4 | BFO importada (OWL oficial), uma colocação por classe, mid-level IAO/CCO | só anotação provisória (`met-bfo.ttl`); categorias minhas | **alta** | não: exige decisão da equipe de ontologia (P-07) |
| §6.6 | duas visões (DL completa + QL gerada) e raciocinador (HermiT) | inexistente | alta | não |
| §7.3/§13 | ciclo build, use, evolve, evaluate, publish; agente de evolução; avaliação pareada | só a semente determinística e a porta de validação | **alta** | parcial: exportação de trajetórias e sinais (A-12) |
| §7.4 r.3 | Evidência ligada a PROV-O | Evidência é texto de procedência; sem PROV-O | média | **parcial**: a resposta tem PROV-O (A-11); as Evidências do EvoOntology ganham IRI PROV-O e grafo próprio (Codex C12) |
| §7.4 r.5 | dois caminhos de mudança, com revisão humana na camada formal | inexistente | média | não |
| §8 | o interpretador chama `resolve_semantics`/`browse_semantics` | o pipeline chama de forma determinística (D-28); `v6` nem chama | média | não: limite do cliente de LLM |
| §10/§12 | SQL gerado pelo Ontop na trilha e na resposta | não era capturado [medido: nenhuma ocorrência no código] | média | **sim** (A-04) |
| §12 | verificador pré-execução com dry-run/EXPLAIN | inexistente; só regras próprias | **alta** | **sim** (A-03) |
| §12 | verificador pós-execução (unidades, limites históricos, vazio onde o catálogo promete) | só `result_status` | média | parcial (A-08) |
| §9/§12 | controle de acesso compilado na consulta; catálogo de capacidades | inexistente | baixa para o MVP (fonte única) | não |
| §8 | consulta canônica com rótulo de intenção | JSON próprio sem intenção; decisão aberta do §16 | baixa | não |

## 2. Validade da avaliação

| ID | Fragilidade | Evidência | Severidade | Tratada |
|---|---|---|---|---|
| A-01 | **Sem incerteza**: n de 8 a 24, uma execução por condição, sem intervalo de confiança nem teste pareado. O modelo varia entre execuções com o mesmo código | RD07: recusada, depois respondida, depois recusada **[medido]** | **alta** | **sim**: `eval/stats.py` (Wilson, McNemar exato) |
| A-02 | **Cascata de contaminação**: dev, test, fresh, RF e RG foram, nessa ordem, usados para corrigir regras. Não resta conjunto limpo | cada relatório | **alta** | não (precisa de perguntas novas e verba) |
| A-35 | **Viés do autor**: mesma pessoa escreveu regras, oráculo, referências e perguntas. RF favoreceu o v6, RG o desfavoreceu (2 sondas) | `docs/COMPARACAO_*` | alta | mitigado: relatórios passam a dizer o intervalo |
| A-05 | O oráculo parte da mesma camada limpa: não detecta erros de limpeza (assumido no cabeçalho de `oracle_real.py`) | leitura | média | parcial: auditoria dos dados (seção 4) |
| A-06 | O juiz estrito marcou "errada" uma resposta de valores corretos (RF01 do v4: faltava a coluna `year`) | 12 totais e 12 contagens iguais ao oráculo **[medido]** | média | documentado, não alterado: afrouxar o juiz esconderia trocas entre entidades |
| A-07 | O teto **por execução** cortou a rodada do v6 em RG23; o ledger não registra chamadas que falham | `RG24` rodou à parte | baixa | não |
| A-36 | Um só modelo, um só esforço de raciocínio: robustez a troca de modelo desconhecida | `kgqa.env` | média | não |
| A-09 | O diálogo de confirmação **não é usado na avaliação**: premissas ("todas as estações") passam sem o usuário ver | RG19 | média | parcial: a descrição passa a dizer o fuso e o escopo (A-13) |

## 3. Segurança e robustez

| ID | Fragilidade | Evidência | Severidade | Tratada |
|---|---|---|---|---|
| A-10 | **O endpoint do Ontop escutava em todas as interfaces**, sem autenticação, contra o que o script e a documentação diziam | `ss -ltn`: `*:8080`; o PostgreSQL estava certo (`127.0.0.1:5433`) **[medido]** | **alta** | **sim**: `SERVER_ADDRESS=127.0.0.1` (verificado: o IP do WSL é recusado) |
| A-03 | **Lacuna sistêmica rdflib × Ontop**: o validador usa o `rdflib`, que é mais permissivo que o motor. Três incidentes (`BIND`, `GROUP BY`, relação ao contrário), tratados regra por regra | HTTP 400/500 e falsas ausências **[medido]** | **alta** | **sim**: checagem prévia pelo próprio motor (`/ontop/reformulate`) |
| A-03b | "Vazia por construção" era detectada por regras minhas. **O motor já diz isso**: reformulação `EMPTY` | `st:SBBE met:reportOf ?r` volta `EMPTY` **[medido]** | alta | **sim** (junto de A-03) |
| A-14 | O modo `--dev` do Ontop expõe `/ontop/restart` e o actuator, sem autenticação (só no loopback) | rotas respondem **[medido]** | baixa | documentado; loopback |
| A-15 | A camada semântica é **gravável por um agente** e entra em prompt. A porta só confere IRI, categoria BFO, agregações e unidade; texto livre passa | `semantics/gate.py` | média | limite documentado; texto já passa por `textsafe` |
| A-16 | `\\` vira `\` nos scripts de edição deste ambiente: gerou TAB literal em regex e padrões que nunca casavam | corrigido duas vezes | baixa | processo: edições com barras só pela ferramenta de arquivo |

## 4. Correção semântica e dados (nada disto aparece em teste de código)

| ID | Fragilidade | Evidência | Severidade | Tratada |
|---|---|---|---|---|
| A-17 | **Visibilidade é 80% censurada**: 79,8% das leituras brutas valem 2000 (dam), que vira 20.000 m = "20 km ou mais". Média e máximo enganam, e a ressalva só estava nas notas da ontologia, não na resposta | 6.889.876 de 8.638.728 **[medido]** | **alta** | **sim**: ressalva determinística na resposta (A-08) |
| A-18 | **Cobertura desigual e códigos lixo**: 19 de 178 estações com menos de 5.000 leituras em 10 anos (mín. 11); 14 siglas fora do formato ICAO (`XXXX`, `SBMI1/2/3`, `SIMK1/2/3`, `SDAM1/2/3`). Ranking por média sem piso de amostra premia estações quase sem dado (RG15 trouxe `SBPW`, n=149) | **[medido]** | **alta** | **parcial**: aviso relativo à mediana mais piso absoluto de 30 leituras (Codex C10); a limpeza dos códigos fica para o dono dos dados |
| A-19 | **"n" conta leituras, não boletins**: 32,3% das leituras de vento são extras (vários sensores/cabeceiras); 4,7% na temperatura. Médias mudam pouco (máx. 0,117 °C na temperatura, 0,54 na umidade, a afirmação de "efeito pequeno" **se confirma**), mas contagens inflam | **[medido]** | média | **sim**: a resposta passa a dizer "leituras" |
| A-20 | **Fuso**: todas as estações são tratadas em UTC−3 (P-16, hipótese). O Brasil tem UTC−2 a UTC−5. "O dia 19/01" de Manaus é o dia em horário de Brasília, não o dia local da estação | R1 de `REGRAS_LIMPEZA.md` | média | **sim**: a descrição diz "dias em UTC−3 (Brasília)"; a hipótese continua a confirmar |
| A-21 | Sem teste cruzado entre variáveis: 3.180 de 9,7 mi pares com ponto de orvalho > temperatura + 0,5 °C (fisicamente impossível) | **[medido]** | baixa | não (exige rebuild de 28 min e decisão) |
| A-22 | Unidade da visibilidade (dam→m) e da altura de nuvem não confirmadas com o dono dos dados (P-17). A moda de 80% em 2000 sustenta a hipótese, não a prova | **[medido]** | média | não: pendência com o professor |

## 5. Qualidade da interpretação

| ID | Fragilidade | Evidência | Severidade | Tratada |
|---|---|---|---|---|
| A-23 | As regras de linguagem (L4) são **listas de padrões em português**, escritas a partir de poucos exemplos. Recall e precisão nunca foram medidos em variações de frase | `GROUP_CUES`, `SINGULAR_RANK`... | **alta** | **sim**: suíte de robustez com variações geradas |
| A-24 | `unresolved_places` depende de maiúscula: "curitiba" minúsculo passa | leitura | média | **sim** |
| A-25 | O esquema ainda não expressa: filtro categórico (gênero de nuvem), HAVING ("dias com mais de 50 mm"), comparação ("qual teve mais"), duas grandezas, períodos como "no verão" | RT04, RG09 | média | não |
| A-26 | Erros de digitação não são tratados ("temperatua") | leitura | baixa | não |

## 6. Camada semântica (EvoOntology + BFO)

| ID | Fragilidade | Severidade | Tratada |
|---|---|---|---|
| A-27 | O `v6` não usa a camada; o `v5` nunca foi medido; a v0 é gerada da própria ontologia e não acrescenta nada além dela até a evolução produzir sinônimos | **alta** | não: exige verba e o laço de evolução |
| A-12 | Sem trajetórias: o log da pipeline não vira registro do EvoOntology, então o ciclo de evolução não tem insumo | alta | **sim** (exportador de trajetórias com os sinais do §13) |
| A-28 | As lacunas de sinônimo medidas ("choveu" em 7 perguntas) nunca foram preenchidas, de propósito, para não contaminar a avaliação | média | não |

## 7. Engenharia e reprodutibilidade

| ID | Fragilidade | Evidência | Severidade | Tratada |
|---|---|---|---|---|
| A-29 | **Quase todo o trabalho está fora do git**: 54 alterações pendentes; `pipeline/`, `semantics/`, `tests/` e vários `eval/` são arquivos não rastreados; 3 commits | `git status` **[medido]** | **alta** | recomendação (commit é decisão sua) |
| A-30 | Sem `.gitattributes`: os `.sh` voltam com CRLF e quebram no WSL; precisei de `tr -d '\r'` dezenas de vezes | **[medido]** | média | **sim** |
| A-31 | Dois Pythons (3.13 no Windows, 3.12 no WSL) deram resultados diferentes (profundidade de JSON); só o WSL roda os testes reais (34 pulados no Windows) | histórico | média | parcial: marcadores e script único de verificação |
| A-32 | `infra/ontop.sh stop` matava só o script, não o processo Java filho | corrigido | baixa | feito |
| A-33 | O README descreve só os incrementos 1 e 2; ninguém consegue montar o ambiente a partir dele; o `env.sh` do WSL só existe fora do repositório | leitura | média | **sim** |
| A-34 | Downloads (uv, JDK, Ontop, driver) sem conferência de checksum; dependência do EvoOntology fixada por commit sem hash | `DECISOES.md` D-32 | baixa | documentado |

## 8. Plano desta rodada e resultado

Implementado, com teste e sem gastar verba de LLM (decisões D-59 a D-66 em `DECISOES.md`): **A-03/A-03b** (checagem prévia pelo motor), **A-04** (SQL capturado), **A-11** (PROV-O),
**A-12** (trajetórias), **A-01** (estatística), **A-08/A-13/A-17/A-18/A-19/A-20** (ressalvas determinísticas na resposta e fuso na descrição), **A-23/A-24** (robustez das regras
de linguagem), **A-10/A-30/A-32/A-33/A-34** (segurança, infraestrutura, documentação, checksums). Suítes ao fim: **914 testes no WSL (0 pulados)**; 866 passam e 48 são pulados no Windows
(precisam do grafo real).

Fica de fora o que exige decisão sua, da equipe de ontologia ou verba nova: A-02 (conjunto limpo de perguntas), A-05, A-21 (teste cruzado orvalho × temperatura, exige rebuild),
A-22 (unidades, com o professor), A-25 (filtro categórico, HAVING, comparação), A-27 (medir o `v5` e fechar o laço de evolução), A-29 (**commit**: 67 entradas pendentes no git),
limpeza das siglas lixo (A-18, dono dos dados) e a importação real da BFO com DL/QL e HermiT.

**Limites desta rodada.** Nenhuma correção foi remedida com o LLM real (saldo ≈ US$ 0,40). O que está provado é que as regras e o motor barram os casos conhecidos; não, que o LLM
passa a acertar mais. O `v6` continua sem ser recomendado como padrão (mesma contagem do `v4` na generalização, sem prova de equivalência).

## 9. Revisão independente (Codex, 23/10/2026) e o que foi feito

Relatório: `docs/AVALIACAO_CODEX.md` (C01–C20). Eu reproduzi C01, C02, C03, C04, C08, C09, C15, C16, C18 e C20 antes de corrigir. O relatório mostrou o que esta
análise não viu: **a parte "formal e determinística" não estava sólida**, havia respostas erradas que atravessavam validadores e motor. A-23/A-24 (regras de
linguagem) e A-18 (amostra pequena) estavam marcadas como resolvidas e não estavam; foram reabertas e tratadas em D-68 e D-71.

| ID | Achado | Estado | Onde |
|---|---|---|---|
| C01 | OR/NOT/OPTIONAL no FILTER e `AVG(?v*0)` passavam | **corrigido** | `FILTER_NOT_CONJUNCTIVE`, `AGGREGATE_ARGUMENT` (D-67) |
| C02 | mês, ano parcial, limiar e parte do dia omitidos | **corrigido** (4 regras L4) | D-68 |
| C03 | `ASK` verdadeiro virava "não há registros" | **corrigido** | D-69 |
| C04 | número com unidade errada ("20,4 K") aceito | **corrigido** | `WRONG_UNIT` (D-69) |
| C05 | BFO real / DL→QL / evolução governada | **aberto** (decisão da equipe de ontologia) | P-07 |
| C06 | generalização não demonstrada, viés | **aberto**; redação de "empate" corrigida | D-74 |
| C07 | trabalho fora do git | **aberto** (decisão do Gabriel) | P-43 |
| C08 | `localDate` contradizia o boletim | **corrigido** | `met:alsoDomain` (D-70) |
| C09 | Q2 juntava leituras espaçadas | **corrigido; rebuild feito, sem mudança nos dados** (as 9 linhas eram consecutivas) | D-72 |
| C10 | alerta de amostra cego a top-1/top-2 | **corrigido** | piso de 30 (D-71) |
| C11 | fuso e escala apresentados como fato | **parcial** (o texto diz "hipótese"); a confirmação segue com o professor | D-71 |
| C12 | Evidência sem vínculo PROV-O | **corrigido na geração**; a v0 já publicada em `.evoontology/` não foi regravada | D-73 |
| C13 | SQL da consulta sem LIMIT; sem identidade de dados e mapeamento | **corrigido** | D-73 |
| C14 | checagem do motor opcional e silenciosa | **corrigido**: aviso e modo estrito `require_engine` | D-75 |
| C15 | comando do README descartava RG24 | **corrigido** | D-74 |
| C16 | teto de gasto checado depois do gasto | **corrigido**: reserva sob trava | D-76 |
| C17 | SHACL só do sintético | **corrigido** (8 unidades, inteiros, faixas) | D-77 |
| C18 | `cap_rows` com comentário após LIMIT | **corrigido** | D-77 |
| C19 | testes de infra fracos | **corrigido** (SHA de 64 hex, teste de comportamento do `stop`, conferência de artefatos existentes) | D-77 |
| C20 | 7/12 era só status (6/12 pela outra métrica) | **corrigido na redação** | README, D-74 |

**Limite desta rodada.** Nada disto foi remedido com o LLM real. As regras novas barram o que foi reproduzido, mas podem barrar perguntas boas (falso positivo):
a varredura nas perguntas e interpretações de referência não achou nenhum, o que não prova que não exista.
