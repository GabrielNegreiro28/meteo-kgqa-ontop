# Instruções para o gerador independente do conjunto do estudo (25/11/2026)

Quem gera não pode ler o código do sistema (`metqa/`, `eval/`, `semantics/`, `ontology/`, `mapping/`, `tests/`), os documentos (`docs/`,
`DECISOES.md`) nem os conjuntos antigos. Pode ler só `data/estacoes.csv` e consultar o banco limpo em modo leitura.

## Tarefa

Escrever 120 perguntas inéditas em português sobre dados meteorológicos de aeródromos brasileiros, com a resposta de referência de cada
pergunta respondível escrita em SQL sobre a base limpa:
- 80 respondíveis (`answerable`);
- 20 que exigem esclarecimento (`needs_clarification`): a pergunta admite leituras que mudam a resposta, ou falta estação, período ou cálculo;
- 20 fora do que os dados cobrem (`unsupported`): previsão do futuro, grandeza inexistente, coordenadas, lugar sem estação, período fora de 2016–2025.

Varie a forma, como um usuário real: perguntas curtas e longas, formais e informais, com siglas, apelidos de aeroporto, municípios, estados e
regiões (ver o cadastro). Use muitas estações diferentes, todos os anos, todas as grandezas, horas locais ("à tarde", "de madrugada",
"às 15h"), dias da semana, condições ("acima de 30 °C"), contagens, séries por ano/mês/dia, rankings e comparações de períodos.

## O banco (DuckDB, somente leitura)

Arquivo: `/home/gabriel/metdata/met.duckdb` no WSL (Ubuntu). Rode consultas com um script Python seu:
`wsl.exe -d Ubuntu -e bash -lc '$HOME/metdata/venv/bin/python /mnt/c/<caminho do seu script>.py'`, abrindo com
`duckdb.connect('/home/gabriel/metdata/met.duckdb', read_only=True)`. Use só o schema `clean`.

Tabelas de observação (uma linha por leitura válida; um instante pode ter várias leituras, `seq` 0, 1, ...; use todas):

| tabela | grandeza | unidade de `value` |
|---|---|---|
| clean.obs_air_temp | temperatura do ar | °C |
| clean.obs_dew_point | ponto de orvalho | °C |
| clean.obs_wet_bulb | bulbo úmido | °C |
| clean.obs_rel_humidity | umidade relativa | % |
| clean.obs_runway_temp | temperatura da pista (poucos aeródromos) | °C |
| clean.obs_qnh | pressão QNH (nível do mar) | hPa |
| clean.obs_visibility | visibilidade predominante (teto de registro 20.000 m) | m |
| clean.obs_wind_speed | velocidade do vento (por cabeceira `runway`; `condition` 'calm' ou 'variable') | nós |
| clean.obs_wind_dir | direção do vento (de onde sopra) | graus |
| clean.obs_wind_gust | rajada (só existe quando houve rajada) | nós |
| clean.obs_precip | chuva acumulada na hora que termina em `t_local` (só boletins da hora cheia) | mm |
| clean.obs_precip_duration | duração da chuva nessa hora | min |
| clean.obs_cloud_layer | uma linha por camada de nuvem: `okta` (oitavos), `base_m` (m), `genus` (CU, CB, ...) | — |

Colunas comuns: `sigla` (código ICAO), `t_local` (hora civil da estação), `t_utc`, `local_date` (dia civil da estação), `value`, `seq`.
Na chuva e na duração, `local_date` é o dia em que a hora acumulada COMEÇA (a chuva de 23h–24h é do dia; a de 0h–1h é do dia seguinte).
Hora local de uma leitura: `hour(t_local)`. Dia da semana: `isodow(local_date)` (1 = segunda ... 7 = domingo).
Cobertura: 2016-01-01 a 2025-12-31 (varia por estação: confira antes de perguntar).

## Formato de saída

Grave dois arquivos JSON (UTF-8) na pasta que lhe indicarem:

`perguntas.json`:
```json
{"reviewed_by": "gerador independente (modelo, data)", "questions": [
  {"id": "S001", "question": "...", "expected_behavior": "answerable", "rationale": "o que a pergunta pede, em uma frase"}]}
```

`referencias.json`, só para as respondíveis:
```json
[{"id": "S001", "measure": "air_temp", "is_count": false, "expected_status": "answered",
  "parts": [{"label": "", "sql": "SELECT avg(value) AS value FROM clean.obs_air_temp WHERE sigla = 'SBGR' AND local_date BETWEEN DATE '2023-03-01' AND DATE '2023-03-31'"}]}]
```
Regras do SQL de referência:
- um único SELECT por parte, só sobre `clean.*`;
- o número pedido sai na coluna `value` (média, máxima, mínima, soma ou contagem); `is_count` = true quando é uma contagem;
- agrupamentos saem nas colunas `station` (o IRI completo: `'https://example.org/kgqa-met/data/station/' || sigla`), `year`, `month`, `day`
  (a data), nessa nomenclatura; o ranking devolve exatamente as N linhas pedidas, com as mesmas colunas;
- uma pergunta que compara períodos de UMA estação tem uma parte por período, com `label` igual ao período em "DD/MM/AAAA a DD/MM/AAAA"
  (ou "DD/MM/AAAA" para um dia); evite comparar estações em partes separadas (prefira série por estação, `station` + `value`);
- `expected_status` é "answered", ou "no_results" quando o recorte não tem nenhuma leitura;
- confira que cada SQL roda e dá um resultado plausível; troque perguntas cujo resultado seja vazio por engano, trivial ou absurdo.

Não invente definições escondidas: se a pergunta depende de uma convenção (estação do ano, "dia chuvoso"), escreva a convenção na própria
pergunta, ou faça dela uma pergunta de esclarecimento.
