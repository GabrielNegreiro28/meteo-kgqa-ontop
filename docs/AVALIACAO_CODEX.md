# Avaliação independente do módulo KGQA meteorológico

Data: 23/10/2026. Revisor: Codex. Objeto: árvore de trabalho local de `meteo-kgqa-ontop`, incluindo arquivos não rastreados. Referência: **Ontology-Grounded Agentic Architecture for Natural-Language Data Access**, revisão de 13/10/2026, de José M. Parente de Oliveira.

## Veredito

1. O grafo virtual e as consultas de referência têm evidência operacional: **914 testes passaram no WSL**, incluindo a comparação real de 15 consultas com o oráculo.
2. Isso **não torna sólida a validação semântica de ponta a ponta**: reproduzi respostas erradas que atravessam os validadores e o Ontop.
3. Trocar a conjunção temporal por disjunção amplia o período; multiplicar o valor por zero dentro de AVG produz uma média falsa aceita.
4. `ASK=true` vira “não há registros”; um resultado em Celsius pode ser apresentado como Kelvin sem diagnóstico público.
5. A BFO é uma anotação provisória, e o ciclo de evolução governada do EvoOntology não está implementado nesta integração.
6. Os placares RF/RG são reconstituíveis, mas não demonstram generalização, equivalência entre versões nem benefício de BFO/EvoOntology.
7. Ressalvas mitigam a apresentação; não confirmam unidades, fuso, cobertura ou correção da limpeza.
8. Primeiro eu fecharia os caminhos de resposta silenciosamente errada, antes de gastar com nova comparação de prompts.

## Escopo, pressupostos e método

Ambiguidades relevantes, resolvidas sem interromper a revisão:

- **Fidelidade à arquitetura completa ou à fatia?** Avalio a fatia de consulta em grafo. Roteador, MongoDB e extração de PDFs ficam fora; catálogo e autorização ficam registrados como requisitos de integração, sem penalizar a ausência do roteador.
- **Implementação atual ou versão dos placares?** Avalio o código atual; os placares são evidência histórica das versões executadas, não das correções posteriores D-53–D-66.
- **“Funciona” significa passar exemplos ou preservar o significado?** Para correção, exige preservar restrições e unidades e distinguir falso, vazio e erro. Para benefício científico, exige comparação que isole a contribuição e controle contaminação.

**[verificado]** significa trecho exato lido ou comportamento executado; não significa ocorrência espontânea com LLM real. **[inferido]** identifica uma consequência ou risco ainda não demonstrado no ambiente. **[não verificado]** identifica ausência de confirmação. P/M/G são esforços relativos de correção, não estimativas de prazo. Severidade considera dano silencioso, alcance e objetivo científico. Não encontrei evidência suficiente para classificar qualquer achado como **crítico**.

Li primeiro a autoanálise, decisões e README; depois os relatórios comparativos e de equivalência, o DOCX e os caminhos relevantes de código, ontologias, mapeamento, ingestão, infraestrutura e testes. A inspeção foi orientada por risco, não uma prova exaustiva de todos os caminhos. `pandoc` não foi localizado no Windows nem pelo `command -v pandoc` no WSL; extraí `word/document.xml` com `zipfile`/ElementTree para uma pasta temporária externa. Usei o texto das seções do DOCX como fonte de verdade. Não inspecionei visualmente suas figuras.

Não fiz chamadas de LLM, alterações de código, alterações de índice ou operações de commit. Não abri arquivos de credenciais, CSVs/NPZ brutos, conteúdo da `.venv` ou trajetórias existentes. A suíte autorizada usou seus próprios dados artificiais, agregados e consultas; o executável da `.venv` foi usado conforme o comando solicitado. Os scripts adicionais ficaram fora do repositório. O Ontop já estava ativo: nenhum serviço novo precisou ser iniciado.

## Tabela de achados

| ID | Severidade (crítica/alta/média/baixa) | Área (A–H) | Achado | Evidência (arquivo:linha ou comando+saída) | Confiança ([verificado]/[inferido]) | Correção sugerida | Esforço (P/M/G) |
|---|---|---|---|---|---|---|---|
| C01 | alta | B, F, H | L3 confere presença de operadores/IRIs, mas perde a semântica da expressão. Aceita OR no período e AVG sobre valor adulterado. | `pipeline/query_facts.py:178`, `:210`, `:212`; `pipeline/validators.py:675`, `:730`. Reprodução R1: todas sem achados; no grafo real, média correta 20,414726 / n=9473; OR 20,025176 / n=130585; AVG×0 = 0 / n=9473; todas `answered`. | [verificado] | Compilar também as formas simples; restringir a geração livre a uma álgebra suportada e verificar operadores, escopos e argumentos dos agregados. | G |
| C02 | alta | B, F, H | L4 aceita interpretações que omitem restrições explícitas: janeiro vira ano inteiro; ano inteiro vira janeiro; limiar “acima de 30” desaparece. | `pipeline/validators.py:254` só percorre filtros presentes; `:298` verifica apenas os anos das bordas. R2: `month_omission`, `year_partial`, `filter_omission` retornam `[]`. | [verificado] | Extrair e reconciliar restrições da pergunta nos dois sentidos; quando não houver representação ou reconhecimento seguro, esclarecer/recusar. | G |
| C03 | alta | B, F | ASK verdadeiro é classificado como ausência de registros, produzindo resposta factual oposta à execução. | `kgqa/store.py:36`, `:324`; `kgqa/verify.py:19`; `pipeline/orchestrator.py:455`, `:478`. R1: `boolean=True`, status `no_results`, texto “Não há registros”. | [verificado] | Tratar resultados booleanos antes de SELECT; falso deve ser “Não”, não ausência. Se ASK ficar fora do contrato, recusá-lo explicitamente antes de executar. | P |
| C04 | alta | B, E, F | Unidade errada no texto é aceita; o juiz dos placares não avalia a fidelidade do texto final. | `pipeline/grounding.py:215–218` só gera warning; `pipeline/orchestrator.py:490` descarta warnings; `eval/run_llm_pipeline.py:72–74` julga `r.results`. R1: “20.4147 K.” para resultado DEG_C, `answered`, diagnósticos `[]`. | [verificado] | Vincular cada valor redigido à coluna/unidade; bloquear incompatibilidade ou renderizar deterministicamente. Avaliar texto e tabela separadamente. | M |
| C05 | alta | A, C, H | A contribuição central ainda é infraestrutura preparatória: sem importação BFO/DL→QL/raciocinador, sem ciclo local governado Parent/Candidate; v6 ignora a camada. | DOCX §§6.4, 6.6, 7.3, 13; `ontology/met-bfo.ttl:10–24`; `pipeline/vocab.py:97–108`; `pipeline/prompts.py:145–146`; `semantics/build.py:158–167`; `semantics/ground.py:105–107`. Busca descrita em R3. | [verificado] | Implementar um recorte vertical com alinhamento revisado, gate obrigatório e avaliação de versões congeladas; medir ablações separando BFO, EvoOntology e compilador. | G |
| C06 | alta | E, H | Generalização e equivalência não foram estabelecidas. ICs não removem viés de autoria/seleção nem o uso posterior de todos os conjuntos para corrigir regras. | `docs/ANALISE_CRITICA.md:20–21`, `:43–45`, `:113–114`; `docs/COMPARACAO_GENERALIZACAO_V6_V4.md:38–49`; `eval/stats.py:78–79`. R4 confirma números, não as interpretações fortes. | [verificado] | Descrever igualdade de contagens observadas; reservar conjunto externo e congelado, repetir execuções e definir previamente métricas e margem de equivalência, se essa for a hipótese. | G |
| C07 | alta | G | A árvore auditada não é reproduzível por checkout do estado versionado: componentes centrais permanecem não rastreados. | `git --no-optional-locks -c core.fsmonitor=false status --short --untracked-files=normal`: 67 entradas, incluindo `?? pipeline/`, `?? semantics/`, `?? docs/`, novos testes e scripts. `.gitignore:13` exclui relatórios. | [verificado] | Preparar snapshot revisado de código, dependências e evidências sanitizadas, com manifesto de hashes; versionar apenas mediante decisão do responsável. | M |
| C08 | média | B, C | A camada estrutural contradiz o mapeamento de boletins: `localDate` implica Observation, mas WeatherReport é incompatível com Observation. Consulta válida recebe TYPE_CLASH. | `ontology/met-structure.ttl:38`, `:54`; `mapping/met.obda:22`; `pipeline/validators.py:564–608`. R1: consulta de data do boletim recusada pelo validador e aceita pelo Ontop, que devolveu `2016-01-01`. | [verificado] | Remover o domínio global excessivo ou separar propriedades; testar axiomas contra todos os sujeitos produzidos pelos mapeamentos. | M |
| C09 | média | D, F | Q2 chama observações espaçadas de “boletins horários consecutivos”: LAG/LEAD compara valores sem conferir a distância temporal. | `ingest/transform.py:207–216`; `data/REGRAS_LIMPEZA.md:30`. SQL exato, em DuckDB em memória: 25 mm em 01/01/2019, 01/06/2019 e 01/01/2020 marca as três como `stuck`. | [verificado] | Exigir intervalos contíguos de uma hora, decidir tratamento de múltiplas leituras e auditar a quarentena Q2 antes de reprocessar. | M |
| C10 | média | D, H | Aviso de amostra pequena falha justamente em top-1/top-2 e quando todos os grupos têm pouca cobertura; compara somente a mediana dos resultados selecionados. | `pipeline/caveats.py:19–20`, `:43–55`; `tests/test_caveats.py:53–55`. Sonda: n=[1], [1,10000] e [1,1,1] sem alerta; [1,10000,10000] alerta. | [verificado] | Usar cobertura esperada para o período/estação, piso explícito ou diagnóstico de insuficiência; preservar denominador da população antes do LIMIT. | M |
| C11 | média | D, H | Fuso e escala física provisórios viram valores canônicos; o texto final não comunica claramente a incerteza de P-16/P-17. Censura não se resolve com aviso. | `data/DICIONARIO_DADOS.md:38–45`, `:56`, `:64`; `ingest/transform.py:32`, `:48`, `:151`; `ontology/met-structure.ttl:136`. A hipótese vira “20 km ou mais” sem indicação de escala não confirmada. | [verificado] | Propagar status de hipótese e confirmar metadados com o fornecedor; distinguir estatísticas de valores registrados de estatísticas físicas sob censura. | M |
| C12 | média | A, H | Gerar PROV-O para a resposta não cumpriu §7.4 r.3: Evidence do EvoOntology continua como texto sem referência PROV-O. | `semantics/build.py:98–100` versus `pipeline/provenance.py:23–73`. `build_records()` produziu 42 Evidence com `source`, `query`, `validation_method`, `timestamp`, `result`; nenhuma ligação a registro PROV-O. | [verificado] | Criar IRIs de evidência e vínculos aos artefatos/atividades correspondentes, resolvíveis a partir do Term. | M |
| C13 | média | A, B, G | A procedência captura a reformulação da consulta anterior ao LIMIT do executor, não necessariamente o SQL da consulta enviada; faltam identidades de dados, mapeamento e limpeza. Falhas de PROV são silenciadas. | `pipeline/orchestrator.py:67`, `:136–146`, `:242`, `:444`; `kgqa/store.py:302`; `pipeline/vocab.py:106–108` só inclui dois TTL no fingerprint. | [verificado] | Persistir consulta efetivamente enviada, reformulação correspondente e hashes/versões de dados, mapeamento, limpeza, código e BFO; sinalizar procedência incompleta. | M |
| C14 | média | A, B | A checagem do motor é opcional e não substitui verificação de significado ou de resultados. Indisponibilidade permite executar. | `pipeline/orchestrator.py:60–81`; `tests/test_engine_check.py:94–104`; D-60. R1 passa pelo motor com significado errado; `kgqa/verify.py:11–27` só classifica vazio/contagem. | [verificado] | Tornar explícito o nível de verificação e a política de degradação; para modo estrito, exigir reformulação e verificações pós-execução pertinentes. | M |
| C15 | média | E, G | O comando estatístico do README não reproduz a tabela RG: ignora silenciosamente RG24 pela interseção dos IDs. | `README.md:57`; `eval/stats.py:55–67`. R4: arquivos principais têm 24 e 23 IDs → 19/23 e 18/23; incorporar `_rg24.json` restaura 20/24 e 19/24. | [verificado] | Consolidar a rodada com checagem de duplicatas/versões e exigir igualdade dos IDs ou relatório explícito das exclusões. | P |
| C16 | média | B, G, H | Ledger é um freio após o gasto, não um teto rígido. Não reserva custo da próxima chamada nem faz leitura/reserva/escrita atômica. | `pipeline/ledger.py:57–62`. Cliente falso, arquivo temporário: 0,39 gastos, teto 0,40, chamada de 0,05 aceita → 0,44. Corrida entre processos é consequência inferida; não foi exercitada. | [verificado] | Reservar custo máximo antes da chamada e reconciliar consumo; usar lock/transação entre processos; registrar falhas potencialmente cobradas. | M |
| C17 | média | F, C | Parte das alegações excede o que os testes provam: templates de linguagem não medem generalização; SHACL cobre o sintético e rejeitaria unidades válidas do real. | `tests/test_linguistic_robustness.py:47–56`, `:98–101`; `tests/test_data.py:43–53`; `ontology/shapes.ttl:13–15` aceita só decimal e DEG_C/PERCENT/MilliM; mapeamento inclui M/KN/HectoPA e valores integer. | [verificado] | Separar regressão, propriedades e avaliação externa; atualizar shapes e testar amostras representativas de cada tipo mapeado, sem materializar o grafo inteiro. | M |
| C20 | média | E, H | O 7/12 do split test é acerto de status, não a mesma métrica de acerto dos placares RF/RG. Pela métrica `succeeded`, são 6/12. | `docs/RESULTADOS_LLM_REAL_v4_real_test_r1.md`, seção Todas; `eval/reports/llm_run_v4_real_test_r1.json`, registros RT03/06/07/08/09/11/12. RT12 tem status correto e `result_match=false`; somas: 7 status corretos, 5 tabelas corretas, 6 comportamentos corretos. | [verificado] | Identificar a métrica junto de cada fração e usar denominadores comparáveis; manter separados status, resultado e texto. | P |
| C18 | baixa | B | `cap_rows` transforma consulta válida com comentário depois de LIMIT em consulta com dois LIMITs. | `kgqa/store.py:213–229`. `SELECT ?s WHERE { ?s ?p ?o } LIMIT 2 # comment` → nova linha `LIMIT 11`; `check_policy` retorna SyntaxError. | [verificado] | Alterar limite pela árvore sintática ou serializador seguro, preservando comentários e subconsultas. | P |
| C19 | baixa | G, F | README melhorou, mas instalação limpa/idempotência não estão demonstradas; testes de setup conferem strings, não instalação ou integridade dos binários existentes. | `infra/setup_wsl.sh:42–71` pula binários presentes; `tests/test_infra.py:40–46` aceita até variável de checksum vazia; `:50–52` só verifica existência de `pkill -f`. | [verificado] | Testar instalação em prefixo isolado e segunda execução; verificar versão/hash também de artefatos reutilizados e limitar stop ao processo gerenciado. | M |

## Fidelidade ao documento do professor

| Referência | Avaliação da fatia atual |
|---|---|
| §6.4 BFO | **Não cumprida como ontologia formal.** Há categorias anotadas, explicitamente provisórias; não há importação oficial nem parentes BFO/IAO/CCO assertados para realizar o alinhamento exigido. O próprio `met-bfo.ttl:60–63` reconhece a diferença entre grandeza genérica SOSA e qualidade particular BFO. Isso é uma questão ontológica real, não resolvida copiando o identificador `quality`. |
| §6.6 DL/QL e raciocinador | **Não cumprida.** Separar `met.ttl` de `met-structure.ttl` manualmente não equivale a gerar uma visão QL de uma fonte DL verificada. Existe SHACL, mas o teste é do sintético; não representa a cobertura do grafo real. |
| §§7.3/13 evolução | **Parcial, sem o ciclo.** Há semente, fachada, gate e conversor de trajetórias. Não há na integração local o processo que gera candidato, compara Parent/Candidate em condições congeladas e só então publica. A existência dessas funções não demonstra melhoria nem promoção segura. |
| §7.4 r.1/r.2 | **Parcial.** IRIs e categorias são transportados; o gate os compara. Entretanto, `GroundedLayer._bind` em `semantics/facade.py:36–42` marca `bound` pela presença dos campos, sem ali validar sua verdade. A busca por `validate_candidate` encontra definição e testes, não sua imposição no caminho local de publicação/carregamento. |
| §7.4 r.3 Evidência/PROV-O | **Não cumprida para os Evidence.** O PROV-O da resposta é uma implementação distinta. C12 não é falta de serialização Turtle: é falta do vínculo requerido. |
| §7.4 r.4/r.5 | **Parcial.** Gate verifica subconjunto de restrições (agregações/unidade); não verifica contradições gerais com OWL/SHACL. Não há fluxo local completo de promoção e revisão da camada formal. Não inspecionei o código instalado do núcleo EvoOntology, portanto não atribuo ao núcleo externo uma ausência que verifiquei só na integração. |
| §8 MCP e interpretação | **Fachada implementada; uso agêntico divergente.** `mcp_server.py` fornece stdio e os testes de protocolo passaram. A pipeline v5 consulta n-gramas deterministicamente, conforme D-28; v6 não consulta. `ground.py:107` só retém `observable_property`; as grandezas da semente carregam `quality`, o que não exercita desambiguação entre processo, objeto e conteúdo. |
| §§9–11 | Router, múltiplas fontes e documentos ficam fora do recorte. Ausência de autorização compilada limita a integração futura; loopback e usuário de leitura não são autorização por usuário. O formato nativo OBDA não é, por si, erro de consulta: o ponto decisivo é o mapeamento executável e sua correspondência com a ontologia. |
| §12 pré-execução | **Parcial.** Há regras e reformulação real. O texto específico de dry-run/EXPLAIN no DOCX trata de SQL fallback escrito por LLM; esta fatia não tem esse fallback. Não exigiria EXPLAIN literal como fim em si. Exigiria preservação das restrições, que C01/C02 refutam. |
| §12 pós-execução e síntese | **Insuficiente.** `result_status` não valida limites históricos nem compatibilidade física; `derive_units` atribui unidades esperadas, não demonstra compatibilidade do resultado ou da redação. C03/C04 são falhas executadas. |
| §16 decisões abertas | **JSON intermediário é defensável.** O documento admite linguagem intermediária mais leve compilada para SPARQL; não classifico essa escolha como contradição. Faltam intenção explícita e representação segura de certas restrições. Maturidade do EvoOntology e sobreajuste permanecem riscos efetivos. |

**Efeito real de BFO/EvoOntology:** a camada estrutural de domínio afeta consultas e validações; isso não é evidência de benefício da BFO. O gate e o bloco de v5 usam categorias BFO, mas v6 não usa o bloco; não há experimento real que isole esse benefício. Testes de sinônimo adicionado em camada temporária (`tests/test_semantic_pipeline.py:99–106`) mostram um mecanismo funcional de aconselhamento, portanto seria excessivo dizer que EvoOntology “não faz nada”. O que falta é efeito medido em respostas reais e governança efetiva da evolução.

## Evidências reproduzíveis

### R1 — Consultas erradas atravessam o fluxo completo

Usei um teste externo ao repositório, em Python 3.12.15 no WSL, com `ScriptedLLM`; nenhuma API ou chave é usada. O índice foi carregado dos TTL e do OBDA, com SBGR como entidade conhecida. O backend foi o Ontop já ativo. O teste abaixo pode ser salvo como `test_codex_repro.py` em uma pasta temporária fora do repositório e executado, na raiz do projeto, com `PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -s -p no:cacheprovider /caminho/temporario/test_codex_repro.py`, após o `source ~/metdata/env.sh` autorizado.

As asserções documentam **a presença dos defeitos**, não o comportamento desejado. Depois da correção, devem ser invertidas ou substituídas por testes de aceitação.

```python
import sys, json
from pathlib import Path
ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from pipeline.validators import PipelineInterpretation as I, validate_query
from pipeline.vocab import OntologyIndex, STATION_NS
from pipeline.compiler import compile_query
from pipeline.orchestrator import run_pipeline
from pipeline.llm import ScriptedLLM
from kgqa.store import OntopBackend, PREFIXES

def test_reproducoes():
    idx = OntologyIndex.load(with_data=False).with_profile_from_obda(
        ROOT / "mapping/met.obda")
    idx.entities = {STATION_NS + "SBGR": ["SBGR"]}
    idx.properties_with_data = set(idx.properties)
    backend = OntopBackend()
    period = dict(start="2019-01-01", end="2019-12-31",
                  tz="-03:00", inclusive_end=True)
    plan = dict(properties=["met:AirTemperature"],
                entities=[dict(text="SBGR", iri="st:SBGR")],
                period=period, aggregation="avg", filters=[],
                record_kind="observation")
    question = "Qual a temperatura média de SBGR em 2019?"
    query = compile_query(I(**plan), idx, question)

    def run(p, q, text=question, answer="Falha proposital na redação"):
        llm = ScriptedLLM({
            "interpret": [json.dumps(dict(status="ok", **p))],
            "generate": [json.dumps(dict(sparql=q))],
            "answer": [answer]})
        return run_pipeline(text, llm, backend, idx,
                            prompts_version="v6", timeout_s=60).response

    for name, q in [
        ("correta", query),
        ("periodo_OR", query.replace(" && ", " || ")),
        ("media_zero", query.replace("AVG(?v)", "AVG(?v * 0)"))]:
        assert not validate_query(q, I(**plan), idx)[1]
        r = run(plan, q)
        print(name, r.status.value, r.results, r.answer_text)
        assert r.status.value == "answered"

    ask = """ASK { st:SBGR sosa:hosts ?s .
      ?o a met:InstantaneousObservation ; sosa:madeBySensor ?s ;
         sosa:observedProperty met:AirTemperature . }"""
    p = dict(plan, period=None, aggregation=None)
    r = run(p, ask, "Há leituras de temperatura do ar em SBGR?")
    print("ASK", r.results, r.status.value, r.answer_text)
    assert r.results["boolean"] is True
    assert r.status.value == "no_results"

    r = run(plan, query, answer="A temperatura média foi 20.4147 K.")
    print("unidade", r.status.value, r.answer_text,
          [d.code for d in r.diagnostics])
    assert "20.4147 K." in r.answer_text

    q = """SELECT ?d WHERE { ?r a met:WeatherReport ;
      met:reportOf st:SBGR ; met:localDate ?d } LIMIT 1"""
    print("boletim", [f.diag.code for f in validate_query(q, None, idx)[1]],
          backend.select(PREFIXES + q).results)
```

Saída observada no teste externo equivalente:

```text
correta:    answered  value=20.4147260635490341   n=9473
periodo_OR: answered  value=20.0251759390435349   n=130585
media_zero: answered  value=0.00000000000000000000 n=9473
ASK: boolean=True; no_results; "Não há registros para os critérios da pergunta na fonte consultada."
unidade: answered; "A temperatura média foi 20.4147 K."; diagnostics=[]
boletim: ['TYPE_CLASH']; Ontop ok=True, d=2016-01-01
1 passed in 1.84s
```

O ramo testado usa v6 **sem campos estruturados**, portanto segue a geração livre. Não atribuo a adulteração de AVG ao compilador `compile_structured`. A verificação do motor esteve disponível e não impediu essas respostas. O fallback textual copiou fielmente o resultado errado nos casos OR/AVG×0; não é a origem do erro.

Uma segunda reprodução em grafo artificial de duas observações (20 °C em 2019, 40 °C em 2020) deu 20/n=1 na consulta correta, 30/n=2 com OR e 0/n=1 com AVG×0. Isso confirma a causa sem depender dos valores reais ou de um oráculo do autor. Pela semântica SPARQL, ASK retorna um booleano e operadores/expressões fazem parte do significado da consulta; a checagem de presença de termos não preserva esse significado. [SPARQL 1.1](https://www.w3.org/TR/sparql11-query/)

### R2 — Restrições omitidas na interpretação

Com `idx` e `plan` de R1, execute antes de fechar o teste:

```python
from pipeline.validators import validate_interpretation
cases = [
    ("janeiro omitido", "Qual a temperatura média de SBGR em janeiro de 2019?", plan),
    ("ano reduzido", "Qual a temperatura média de SBGR em 2019?",
     dict(plan, period=dict(period, end="2019-01-31"))),
    ("limiar omitido", "Qual a temperatura média de SBGR acima de 30 graus em 2019?", plan),
    ("recorte diurno omitido", "Qual a temperatura média de SBGR durante o dia em 2019?", plan),
    ("lugar omitido", "Qual a temperatura média em piracicaba em 2019?",
     dict(plan, entities=[]))]
for name, question, p in cases:
    print(name, [f.diag.code for f in
                 validate_interpretation(I(**p), idx, question, (), True)])
```

**[verificado]** Todos retornaram `[]`. O caso “durante o dia” pode exigir esclarecimento sobre o intervalo; não autoriza silenciosamente todo o dia. `piracicaba` mostra o limite de uma lista de topônimos, sem pretender medir sua taxa de erro. O reconhecimento de cidades inexistentes no cadastro deve ser tratado como cobertura desconhecida, não como problema encerrado pela lista de 80 nomes.

**[não verificado]** Frequência com que o LLM real produz essas interpretações. O teste prova que a barreira determinística não as rejeita, não que ocorrerão em toda pergunta. Diálogo confirmado poderia mitigar parte do problema; é opcional e não foi usado nos placares.

### R3 — Ausência dos mecanismos centrais na integração

Busca somente nos arquivos de código/ontologia do projeto:

```powershell
rg -n 'validate_candidate|publish_ontology|evolve|evaluate|hermit|owl:imports|BFO_' semantics pipeline ontology infra tests -g '*.py' -g '*.ttl' -g '*.sh'
```

**[verificado]** `validate_candidate` aparece na definição e em testes; o ponto local de publicação encontrado é `semantics/build.py:167`, que publica v0 sem chamá-lo. As ocorrências de BFO são anotações e código de transporte/comparação de categorias. Os arquivos carregados por `OntologyIndex.load` são `met.ttl` e `met-structure.ttl`; `infra/ontop.sh:16–25` entrega `met.ttl` ao Ontop. Não há ali importação BFO, geração DL→QL ou chamada a raciocinador. `prompts.py:145–146` habilita `semantic=True` em v5 e `structured=True`, sem `semantic=True`, em v6.

O núcleo externo do EvoOntology possui operações delegadas pelo servidor (`semantics/mcp_server.py:42`); não o examinei na `.venv`. Portanto, o achado é sobre a **integração governada ausente neste projeto**, não sobre funcionalidades inexistentes na biblioteca externa. Também não simulei publicação não autorizada: seria uma mudança de estado fora desta revisão.

### R4 — Reconstituição dos placares

Recalculei diretamente dos JSON históricos, sem executar os runners e sem alterar seus relatórios:

| Conjunto e métrica | v4 | v6 | Só v4 / só v6 | McNemar exato bilateral |
|---|---|---|---|---|
| RF, 16 perguntas | 12/16; Wilson 50,50–89,82% | 16/16; Wilson 80,64–100% | 0 / 4 | 0,125 |
| RG, arquivos principais apenas | 19/23 | 18/23 | 4 / 3 | 1,00 |
| RG, incorporando RG24 separado | 20/24; Wilson 64,15–93,32% | 19/24; Wilson 59,53–90,76% | 4 / 3 | 1,00 |
| Split test histórico v4, somente status | 7/12; Wilson 31,95–80,67% | não medido nesta comparação | — | — |
| Split test histórico v4, `succeeded` | 6/12 | não medido nesta comparação | — | — |

Para reproduzir RG completo em um script temporário, executado com a raiz do projeto em `sys.path`:

```python
from pathlib import Path
from eval.stats import load, compare
p = Path("eval/reports")
a = load(p / "llm_run_v4_real_gen_v4.json")
b = load(p / "llm_run_v6_real_gen_v6.json")
c = load(p / "llm_run_v6_real_gen_v6_rg24.json")
assert not (set(b) & set(c))
b.update(c)
assert set(a) == set(b) and len(a) == 24
print(compare({"v4": a, "v6": b}))
```

**[verificado]** As fórmulas de Wilson e do McNemar exato em `eval/stats.py:21–37` estão corretas para esses valores e definições. A tabela do README está correta **se** RG24 for incorporado; o comando ali apresentado não faz a incorporação. O 15/19 em ambos considera apenas respondíveis corretas; o 20/24 versus 19/24 inclui comportamento esperado nas recusas. Não são contagens contraditórias.

**[verificado]** As três primeiras linhas da tabela usam `succeeded`. Já o **7/12 do split é somente status**, conforme seu relatório e JSON. RT12 respondeu com status esperado, mas resultado julgado errado; os cinco resultados corretos são RT03, RT06, RT07, RT08 e RT09, e RT11 acrescenta um esclarecimento correto. Logo são 6/12 pela métrica conjunta, ou 5/10 perguntas respondíveis com resultado correto (cinco das seis efetivamente respondidas). O 7/12 não deve ser apresentado como se fosse diretamente comparável ao 12/16 ou 20/24. Não alterei o julgamento histórico de RT12.

**[inferido, interpretação estatística]** Esses intervalos são cálculos condicionais ao desenho, não uma garantia de cobertura de perguntas reais. Perguntas escolhidas pelo autor, muitas próximas entre si e utilizadas para ajustar o sistema, não constituem amostra independente da distribuição de uso. Uma rodada por pergunta não separa variação entre perguntas de variação de execução do modelo. p=1 não demonstra equivalência; p=0,125 também não demonstra ausência de benefício. “Nenhum teste consegue separar” em `stats.py:79` é forte demais: o limite de seis discordâncias é uma propriedade do McNemar exato bilateral a 5% quando todas favorecem um lado, não de qualquer teste ou desenho.

O caso RF01 é descrito como diferença de formato com valores corretos. O placar estrito mistura conformidade de formato e acerto numérico. Seria melhor publicar ambos com critérios prévios. Não recomputei manualmente os 12 valores de RF01; essa caracterização específica continua apoiada na análise histórica, não numa nova conferência minha. A métrica `harmful` também o contabiliza como dano silencioso: não deve ser lida automaticamente como “número meteorológico errado”.

## Dados, modelagem e limites do oráculo

**[verificado]** O caminho pandas/DuckDB é independente de SPARQL/Ontop/PostgreSQL, mas compartilha a camada limpa (`eval/oracle_real.py:3–11`, `:31–41`). Ele detecta divergências de exportação, mapeamento e cálculo; não confirma a hipótese física de unidade nem o fuso da fonte. A igualdade de `localDate` e data-hora sob a mesma transformação não valida a transformação original.

`docs/EQUIVALENCIA_LOCALDATE.md:5–9` registra 256 comparações iguais, 88 vazias. Isso é evidência histórica de equivalência nas amostras; as 168 não vazias não provam todos os períodos, estações ou correção civil dos fusos. Não reexecutei o script integral de equivalência, que grava relatórios. A suíte atual exercitou os testes de `localDate` e os casos reais que contém.

**[verificado]** Q2 pode excluir leituras espaçadas: executei o SQL literal de `quality_control` sobre três linhas artificiais em DuckDB em memória; todas apareceram em `stuck`. Não consultei a quarentena real para afirmar quantas exclusões foram indevidas. Q1a também é uma heurística por repetição do mesmo valor ao longo da estação, sem janela temporal (`transform.py:197–201`); seu falso positivo em chuva real é **[inferido]**, não demonstrado aqui.

**[verificado]** O esquema SOSA separa observação, propriedade, sensor e resultado; o mapeamento distingue instante e intervalo e transporta unidade/origem. São escolhas compatíveis com o papel geral dessas entidades em SOSA, mas a consistência local precisa ser testada: `localDate` já fornece um contraexemplo. A disjunção Platform/FeatureOfInterest do projeto deve ser entendida como restrição desse modelo, não uma regra universal de SOSA. [SOSA/SSN](https://www.w3.org/TR/vocab-ssn/)

**[não verificado]** Não refiz as auditorias de 79,8% de visibilidade no teto, 19 estações com poucas leituras, 14 códigos suspeitos, 32,3% de leituras extras de vento e 3.180 pares orvalho/temperatura. Li esses números na autoanálise; não os promovo a medições independentes. Tampouco confirmei sua origem física com o fornecedor. “Efeito pequeno” medido em algumas médias não demonstra pequeno efeito em extremos, rankings, contagens ou subperíodos.

## Testes e o que eles realmente demonstram

| Ambiente | Comando e condições | Resultado observado |
|---|---|---|
| Windows, Python 3.13.3, tentativa inicial | `PYTHONDONTWRITEBYTECODE=1`; `.venv\Scripts\python -m pytest -q -p no:cacheprovider` | **826 passaram, 48 pulados, 40 erros de setup**, 167,92 s. Pasta temporária padrão inacessível no sandbox. |
| Windows, Python 3.13.3, repetição | Mesmo comando, acrescentando `--tb=short --basetemp=C:\Users\Gabriel\Documents\Codex\2026-10-23\files-pasted-by-the-user-markdown\work\pytest-win-audit` | **866 passaram, 48 pulados, 0 falhas**, 188,70 s. |
| WSL Ubuntu, Python 3.12.15 | `source ~/metdata/env.sh`; `export PYTHONDONTWRITEBYTECODE=1`; `bash infra/verify.sh` | **914 passaram, 0 pulados, 0 falhas**, 308,35 s. Endpoint e reformulação disponíveis. |
| Teste adicional externo WSL, Python 3.12.15 | `"$PY" -m pytest -q -s -p no:cacheprovider <temporário>/test_audit_real.py` | **1 passou**, 1,84 s na versão final: suas asserções confirmam os contraexemplos de R1. |
| Sondas adicionais Windows, Python 3.13.3 | Scripts temporários `probes.py` e `metrics_and_data.py`, com raiz em `sys.path` | Reproduziram R2, estatísticas, Q2, avisos de amostra e ultrapassagem do ledger; são scripts de diagnóstico, não uma segunda contagem de testes da suíte. |

Mensagem da primeira tentativa, comum aos 40 erros:

```text
OSError: could not create numbered dir with prefix pytest- in
C:\Users\Gabriel\AppData\Local\Packages\sandbox.{de657ed7-de1d-4af6-bb16-a91dbecc3f41}\AC\Temp\pytest-of-Gabriel
after 10 tries
826 passed, 48 skipped, 40 errors in 167.92s (0:02:47)
```

O erro desapareceu mudando somente `basetemp`; não o classifico como defeito do repositório ou incompatibilidade Python 3.13. O WSL foi inicialmente bloqueado pelo sandbox e depois executado com a escalada técnica autorizada. Git no sandbox também retornou `fatal: this operation must be run in a work tree`; fora dele, a consulta somente leitura funcionou. Nenhuma dessas mensagens prova corrupção do repositório.

Antes de chamar `verify.sh`, confirmei que Ontop respondia 200: se estivesse parado, o script chamaria `ontop.sh`, que reescreve `mapping/met.obda` na linha 12, incompatível com a restrição de escrita desta revisão. Essa reescrita não foi necessária.

**Cobertura com valor:** testes reais comparam 15 consultas ao oráculo (`test_real_pipeline.py:97–101`), testam formas compiladas contra pandas (`test_structured.py:221–248`, `:289–299`), e checam o motor real e loopback. Não são todos mocks ou tautologias. Os casos de `UNION_WITH_AGGREGATE`, inversão de relação, datas e sintaxe cobrem falhas concretas.

**Asserções limitadas ou próximas da implementação:**

- `test_setup_script_pins_every_version_and_has_a_place_for_each_checksum` verifica que há atribuições e aspas; não exige 64 dígitos hexadecimais nem verifica downloads.
- `test_stop_also_kills_the_java_child` verifica que o texto contém `pkill -f`; não comprova que o processo certo morre e outros sobrevivem.
- `test_secrets_stay_out_of_version_control` verifica padrões no `.gitignore`; não examina o índice ou o histórico e não prova ausência de segredo já rastreado. Não fiz varredura de conteúdo sensível para compensá-lo.
- As 238 variações linguísticas combinam templates próximos das expressões regulares. São regressões úteis; não estimam precisão/recall em perguntas externas. Em `test_linguistic_robustness.py:153–161`, “durante o dia” passa por um teste que só pergunta se houve diagnóstico de agrupamento, não se o recorte diurno foi preservado.
- `test_no_impossible_values_left` testa três máximos agregados; seu nome não implica validação de todas as impossibilidades físicas.
- A reconciliação de `test_every_raw_value_is_accounted_for:75–81` calcula “dentro da faixa” como ausência na quarentena; a primeira igualdade é, em boa parte, uma partição contábil. A segunda igualdade verifica cardinalidade entre trios/limpo/quarentena e tem valor, mas não valida o motivo físico da quarentena.

Nenhum dos contraexemplos novos foi impedido pelos testes existentes, embora toda a suíte tenha passado. Isso justifica testes de mutação semântica, não apenas aumentar o número de paráfrases conhecidas.

## Discordo da autoanálise

1. **“A parte formal e determinística está sólida” (`:11–13`) é amplo demais.** C01–C04 são falhas determinísticas reproduzidas. Eu restringiria a conclusão às consultas e propriedades efetivamente testadas, ao transporte e ao bloqueio de classes conhecidas de erro.
2. **A-11 como resolvido (`:30`, `:104`) está incorreto para o requisito citado.** O PROV-O da resposta não liga os Evidence do EvoOntology a PROV-O. C12 aponta os dois caminhos distintos. PROV-O permite representar entidade, atividade e agente; sua presença não valida automaticamente a completude da proveniência exigida. [PROV-O](https://www.w3.org/TR/prov-o/)
3. **A-18 como resolvido (`:68`) superestima a ressalva.** O top-1/top-2 não recebe alerta; amostras igualmente minúsculas também não. O ranking continua ordenando médias sem piso de cobertura.
4. **A-23/A-24 como resolvidos (`:78–79`) confunde regressão com cobertura.** As sondas de janeiro, limiar e cidade minúscula não listada passam sem achados. A lista corrige casos específicos, não resolve a interpretação geográfica.
5. **A-01/A-35 “tratado/mitigado” por intervalos (`:43–45`) mistura problemas distintos.** Wilson e McNemar tratam incerteza sob pressupostos; não tratam viés de autoria, seleção, contaminação ou variabilidade entre rodadas. “A generalização real fica entre os dois” no relatório RG (`:48`) não tem fundamento como limite estatístico.
6. **“Empata” (`:20`, `:114`) só é defensável como igualdade de contagem das 19 respondíveis naquela rodada.** Não é equivalência de desempenho. Manter v4 como decisão conservadora é possível; apresentá-lo como demonstradamente equivalente ou superior não é.
7. **A-20/A-22 merecem separar transformação da fonte e significado do dia consultado.** Não aplicaria automaticamente fusos locais por estação: o dicionário diz que a fonte pode já estar em Brasília fixo. Isso precisa ser confirmado. A ressalva de UTC−3 não confirma a origem do timestamp, e a censura em 20 km permanece condicionada à escala presumida.
8. **Ausência de EXPLAIN não era, isoladamente, desvio alto da fatia.** O DOCX §12 o exige no SQL fallback escrito por LLM; aqui há SPARQL/Ontop. A lacuna importante é verificação semântica e pós-execução, que reformulação não resolve.
9. **O texto mistura estado anterior e atual das trajetórias (`:19` versus `:88`).** O exportador existe e foi testado; não inspecionei trajetórias existentes e não afirmo que houve exportação de uma rodada real. “Exportador implementado; uso real não verificado” é a conclusão sustentada.
10. **Faltou distinguir as métricas do split e das comparações.** O 7/12 repetido no README e nos comparativos é status correto; pela métrica de comportamento certo usada em RF/RG, dá 6/12. Não é evidência de falsificação do placar, mas de apresentação ambígua que permite uma leitura mais favorável do que o JSON sustenta.

Concordo com as ressalvas sobre contaminação, falta de medição pós-correções, alinhamento BFO provisório e contribuição central ainda não demonstrada. Discordar da autoanálise não exige negar seus achados já sustentados.

## Faltou na autoanálise

- Perda de escopo lógico ao transformar a álgebra SPARQL em conjuntos/listas de fatos; o motor aceita consultas semanticamente erradas.
- Ausência de reconciliação de restrições omitidas entre pergunta e interpretação, além das listas de linguagem já discutidas.
- Tratamento incorreto de ASK e aceitação de unidade incompatível no texto.
- Separação entre acurácia da tabela e fidelidade da resposta final na avaliação.
- Contradição entre domínio de `localDate` e boletins produzidos pelo próprio OBDA.
- Q2 sem condição temporal de consecutividade e necessidade de testar a limpeza com dados artificiais adversariais.
- Divergência entre SQL da reformulação e consulta limitada enviada; procedência sem identidade do snapshot dos dados e do mapeamento.
- Exclusão silenciosa de RG24 na estatística reproduzida pelo comando documentado.
- Uso de 7/12 de status no split ao lado de frações que exigem também resultado correto.
- Ultrapassagem do ledger numa chamada e ausência de reserva atômica para concorrência.
- Gate local não imposto no carregamento/publicação; diferença entre “tem campo BFO” e “passou validação BFO”. A exploração das operações delegadas do núcleo continua **[não verificada]**.
- Shapes SHACL do sintético que não cobrem as unidades/tipos introduzidos nos dados reais.

## O que NÃO consegui verificar

- **Origem física dos dados e auditoria completa de limpeza:** não abri CSVs/NPZ brutos nem rodei reconstrução. Não confirmei P-16/P-17, os percentuais da autoanálise ou os códigos de estação com o fornecedor.
- **Comportamento atual do LLM real:** nenhuma chamada foi autorizada/feita. Não medi taxa dos defeitos novos, melhoria após reparo, variação por modelo ou benefício da camada v5.
- **Ciclo real de evolução e conteúdo das trajetórias:** não acessei `.evoontology/trajectories/`; a biblioteca instalada na `.venv` também ficou fora da inspeção. Não executei publicação, promoção ou evolução.
- **Instalação do zero e rebuild:** não baixei dependências, não recriei bancos nem parei serviços. A suíte confirma o ambiente existente, não a suficiência do README em máquina limpa.
- **Histórico de segredos e exatidão do faturamento:** não li credenciais nem conferi cobrança do provedor. O teste de ledger foi artificial e não gastou dinheiro.
- **Snapshot imutável das medições antigas:** relatórios existem localmente, mas os componentes não rastreados e a ausência de um manifesto por rodada impedem provar que cada placar corresponde exatamente à árvore atual.
- **Cancelamento server-side sob timeout, concorrência real, carga e exposição externa completa:** a configuração e o teste de loopback foram verificados; não fiz carga, ataques ou mudança de rede. Não atribuo a esses itens segurança comprovada.
- **Figuras do DOCX:** texto extraído, sem renderização visual. Os requisitos citados estão no texto das seções.

## Top 5 ações priorizadas

1. **Fechar a geração livre nas formas já compiláveis e preservar o significado na álgebra.** Critério: OR no período, agregado sobre outra expressão/variável, filtros em escopo ineficaz e condições desconectadas são rejeitados ou compilados corretamente; as consultas corretas continuam concordando com o oráculo. Incluir os contraexemplos C01/C02 e casos de OPTIONAL/subconsulta, sem assumir que uma lista de IRIs basta.
2. **Corrigir o contrato de resultado e a fidelidade da redação.** Critério: ASK verdadeiro/falso gera Sim/Não; ausência permanece distinguível; unidade incompatível nunca chega como resposta validada; avaliação mede separadamente tabela, status, texto e ressalvas. As reproduções C03/C04 devem deixar de confirmar os defeitos.
3. **Reconciliar ontologia, mapeamento e qualidade dos dados.** Critério: toda forma mapeada tem caso de consistência e shape/checagem aplicável; consulta de `WeatherReport/localDate` passa; Q2 só marca sequência horária contígua; top-1/top-2 informa insuficiência quando pertinente; P-16/P-17 ficam confirmados ou explicitamente provisórios na resposta.
4. **Congelar uma base reproduzível e refazer o desenho de avaliação.** Critério: manifesto identifica código, prompts, ontologias, mapeamento, limpeza, dados e dependências; RG24 é consolidado e divergência de IDs falha explicitamente; conjunto externo nunca usado no desenvolvimento e múltiplas rodadas são definidos antes da execução. Nova despesa exige autorização; não gastar o saldo atual apenas para repetir conjuntos já usados.
5. **Entregar um recorte mensurável da contribuição BFO + EvoOntology.** Critério: alinhamento formal revisado e verificado, visão QL derivada, Evidence com links PROV-O, gate obrigatório na promoção, candidato que melhora sinônimos sem alterar significado, e comparação Parent/Candidate congelada com regressão e possibilidade de reversão. Medir ablação da BFO separadamente da mudança de compilador/prompt.

## Autorrevisão dos achados de severidade alta

| Achado | Tentativa de refutação | Resultado |
|---|---|---|
| C01 | Procurei bloqueios de UNION, comparações inesperadas, tipagem e reformulação real. Testei pelo fluxo v6, não apenas função isolada. | Os bloqueios existem, mas não cobrem OR nem o argumento adulterado de AVG. Mantido; restrito à geração livre. |
| C02 | Conferi `PERIOD_DATES_MISMATCH`, `FILTER_VALUE_NOT_IN_QUESTION`, lista de cidades e confirmação. | Conferem certas invenções/datas completas; as omissões reproduzidas passam. Confirmação é opcional. Mantido sem alegar frequência no LLM. |
| C03 | Procurei suporte booleano no backend e no renderizador. | Ambos o têm, mas `result_status` classifica antes como vazio e o renderizador prioriza esse status. Fluxo real confirmado. |
| C04 | Conferi unidade canônica, `check_answer` e julgamento da avaliação. | A unidade está correta na tabela; warning é descartado e o texto em K é aceito. Mantido e delimitado ao texto. |
| C05 | Procurei importação/raciocinador, v5, MCP, publicação, gate e testes de sinônimo. | Há implementação parcial funcional, reconhecida neste relatório. Não há o ciclo integrado requerido nem medição isolada; não alego ausência das funções no núcleo externo. |
| C06 | Recalculei RF/RG, incorporei RG24 e separei respondíveis de todas as perguntas; depois conferi o split. | Números de RF/RG confirmados. Não há erro aritmético nesses placares; a inferência científica continua excessiva. O split requer explicitar a diferença de métrica, registrada separadamente em C20. |
| C07 | Repeti consulta Git fora do sandbox, sem locks opcionais, após o erro de acesso inicial. | Estado não rastreado confirmado. Não pedi nem executei commit; a correção depende de decisão posterior do responsável. |

Também descartei como achados: suposta falta total de SHACL (há shapes e testes sintéticos), falta total de PROV-O (há PROV-O da resposta), ausência de testes reais (914 passaram) e uma suposta exigência de SPARQL como única linguagem intermediária (o §16 deixa a escolha aberta). A conclusão final preserva essas distinções.
