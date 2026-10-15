# KGQA meteorológico — módulo de perguntas sobre grafo (SPARQL)

Protótipo do módulo de consulta a grafos de conhecimento do projeto de integração IA + ontologias.
Duas suítes: **sintética** (rdflib, incremento 1) e **real** (boletins de 178 aeródromos 2016–2025 servidos
como grafo virtual pelo Ontop, incremento 2). A ontologia é **provisória**. Decisões e pendências: `DECISOES.md`.

## Incremento 2 — grafo virtual sobre os dados reais
```
CSV (61,7 mi linhas) ──pack.py──> .npz verificados ──load_raw──> DuckDB raw_*
   ──transform (regras R1–R7, CQ Q1a–Q5)──> DuckDB clean.* (105,4 mi obs) + quarantine (230 mil)
   ──export_pg──> PostgreSQL 16 (13 tabelas obs_*, chaves PK/FK) ──Ontop 5.5 + met.obda──> SPARQL :8080
```
| Arquivo | Papel |
|---|---|
| `data/DICIONARIO_DADOS.md` | significado, unidades e relações das colunas (levantado dos próprios dados) |
| `data/REGRAS_LIMPEZA.md` | regras de limpeza e controle de qualidade, com contagens |
| `ingest/` | `unpack`, `load_raw`, `transform`, `export_pg`, `finalize_pg`, `constraints` |
| `mapping/build_mapping.py` → `met.obda`, `met.r2rml.ttl` | mapeamento Ontop (nativo e W3C R2RML) |
| `infra/pg.sh`, `infra/ontop.sh`, `infra/rebuild.sh` | sobe PostgreSQL/Ontop; reconstrução de ponta a ponta |
| `kgqa/store.py::OntopBackend` | executor SPARQL somente leitura sobre o Ontop (política, LIMIT de proteção, timeout) |
| `eval/questions_real.yaml`, `eval/oracle_real.py` | 20 perguntas (8 dev + 12 test) e oráculo em pandas sobre a camada limpa |
| `tests/test_real_pipeline.py` | âncoras do CSV bruto, reconciliação, grafo × oráculo, mutações, somente leitura |

Reproduzir (Linux; Java 17+, Ontop CLI em `$ONTOP_HOME` com `postgresql-42.7.4.jar` em `jdbc/`):
```bash
pip install -r requirements.txt pgserver "psycopg[binary]" duckdb pandas
PACK=/caminho/pack ./infra/rebuild.sh            # ~25 min; termina rodando a suíte de testes
python -m eval.run_reference --suite real         # esperado: 15/15 conferem com o oráculo
```
Caminho de consulta idêntico ao sintético (sensores virtuais, D-17); dia local via `met:localDate`:
```sparql
st:SBGR sosa:hosts ?s .
?o sosa:madeBySensor ?s ; sosa:observedProperty met:Precipitation ; met:localDate "2024-01-19"^^xsd:date ;
   sosa:hasResult/qudt:numericValue ?v .
```

## Incremento 1 — suíte sintética

## Estrutura
```
ontology/met.ttl        ontologia provisória (SOSA + OWL-Time + QUDT)
ontology/shapes.ttl     restrições SHACL dos DADOS (separadas da semântica OWL)
data/generate.py        gerador reproduzível (seed fixa) -> observations.csv, forecasts.csv, synthetic.nt/.ttl
kgqa/contract.py        contrato de entrada/saída v0.1 (proposta)
kgqa/store.py           executor somente leitura (política, timeout, limite de linhas)
kgqa/verify.py          classificação pós-execução (answered x no_results, inclusive agregação vazia)
eval/questions.yaml     24 perguntas: 8 dev + 16 test, com consultas de referência e comportamento esperado
eval/oracle.py          respostas esperadas em Python puro sobre o CSV (independente de SPARQL)
eval/compare.py         comparação de RESULTADOS (tipos, unidades, multiplicidade, ordem com empates)
eval/run_reference.py   roda referências x oráculo e grava eval/reports/reference_run.json
tests/                  testes (dados, SHACL, executor, referências, mutações, valores conferidos à mão)
```

## Reproduzir
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python data/generate.py          # 219 observações, 1 previsão, 2624 triplas
python -m eval.run_reference     # esperado: 19/19 conferem com o oráculo
python -m pytest -q              # esperado: 64 passed com o Ontop no ar (testes reais são pulados sem ele)
```
SHA-256 de `data/synthetic.nt` gerado neste ambiente:
`972e68e02f6772d3764e7e466b48e1d9992f23e15b7a947596967f932f4eea45`.

## Modelo dos dados
- 3 estações: EST-A Serra Azul (T, UR, chuva), EST-B Vale Verde (T, UR, chuva), EST-C Litoral Sul (T, chuva; **sem higrômetro**).
- 02–08/03/2026, leituras às 00h, 06h, 12h, 18h (UTC−03:00).
- Temperatura (°C) e umidade relativa (%) são **instantâneas**; precipitação (mm) é **acumulada** em [h, h+6h).
- Casos planejados: valor exatamente 30,0 °C (limite), dia inteiro sem temperatura na EST-B (ausência ≠ zero),
  um intervalo de chuva ausente na EST-C, previsão de 35,0 °C acima de qualquer observação, empate em 15,0 mm.

Caminho típico no grafo:
```
?station a met:WeatherStation ; sosa:hosts ?sensor .
?obs sosa:madeBySensor ?sensor ; sosa:observedProperty met:AirTemperature ;
     sosa:phenomenonTime/time:inXSDDateTime ?t ;
     sosa:hasResult [ qudt:numericValue ?v ; qudt:unit unit:DEG_C ] .
```

## Semântica das agregações
- média/mín/máx de grandezas instantâneas: sobre as leituras existentes no período; reportar `n`.
- soma: só para acumulados (precipitação); reportar quantos intervalos entraram (`n` de 28 possíveis por semana).
- ausência nunca é zero; agregação sem dados é `no_results`, não valor 0.
