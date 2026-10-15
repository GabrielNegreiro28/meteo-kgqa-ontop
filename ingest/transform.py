"""Camada limpa (schema `clean`) a partir das tabelas brutas `raw_*` no DuckDB.

Regras (documentadas em data/REGRAS_LIMPEZA.md):
  R1 Tempo: hora_observacao é tratada como hora local fixa UTC−3 (P-16). t_utc = t_local + 3 h.
  R2 Horário de verão: todas as linhas às 01:xx de 2016-10-16, 2017-10-15 e 2018-11-04 vão para
     quarentena (não dá para saber qual delas era a observação das 00:xx).
  R3 Faixas físicas: valores fora da faixa vão para quarentena, por variável.
  R4 Duplicatas: por (estação, instante[, cabeceira]) e variável, valores idênticos colapsam em uma
     observação; valores distintos viram observações distintas (seq 0, 1, ...) marcadas multi=true
     (o arquivo não identifica o sensor/pista que produziu cada uma).
  R5 Precipitação: só boletins da hora cheia; acumulado no intervalo [t−1 h, t].
     O dia local do acumulado é o dia do INÍCIO do intervalo (chuva das 23–24 h é do dia anterior).
  R6 Unidades canônicas: visibilidade e base de nuvem dam→m (×10); direção do vento dezenas de graus→graus.
  R7 Vazio nunca vira zero.
Uso: python ingest/transform.py /home/claude/metdata/met.duckdb
"""
import sys, time
import duckdb

DB = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/metdata/met.duckdb"
DST = ("(CAST(hora_observacao AS DATE) IN (DATE '2016-10-16', DATE '2017-10-15', DATE '2018-11-04') "
       "AND hour(hora_observacao) = 1)")

# nome, tabela bruta, coluna, (lo, hi) na unidade bruta, expressão do valor canônico, tipo SQL
SCALARS = [
    ("air_temp",      "temperatura",  "bseco",     (-30, 50),   "raw",          "DECIMAL(5,1)"),
    ("wet_bulb",      "temperatura",  "bumido",    (-30, 45),   "raw",          "DECIMAL(5,1)"),
    ("dew_point",     "temperatura",  "temppo",    (-40, 40),   "raw",          "DECIMAL(5,1)"),
    ("rel_humidity",  "temperatura",  "ur",        (1, 100),    "raw",          "DECIMAL(5,1)"),
    ("runway_temp",   "temperatura",  "temppista", (-30, 75),   "raw",          "DECIMAL(5,1)"),
    ("qnh",           "pressao",      "qnh",       (900, 1100), "raw",          "DECIMAL(6,1)"),
    ("visibility",    "visibilidade", "visibpre",  (0, 2000),   "raw * 10",     "INTEGER"),
]


def sql_scalar(name, src, col, rng, expr, typ):
    lo, hi = rng
    return f"""
CREATE OR REPLACE TABLE clean.obs_{name} AS
WITH base AS (
  SELECT row_id, sigla, hora_observacao AS t_local, {col} AS raw
  FROM raw_{src} WHERE {col} IS NOT NULL AND NOT {DST}
), valid AS (
  SELECT row_id, sigla, t_local, CAST({expr} AS {typ}) AS value FROM base WHERE raw BETWEEN {lo} AND {hi}
), dedup AS (
  SELECT sigla, t_local, value, MIN(row_id) AS src_row FROM valid GROUP BY sigla, t_local, value
)
SELECT sigla, t_local, t_local + INTERVAL 3 HOUR AS t_utc, CAST(t_local AS DATE) AS local_date,
       value,
       CAST(ROW_NUMBER() OVER (PARTITION BY sigla, t_local ORDER BY value) - 1 AS SMALLINT) AS seq,
       COUNT(*) OVER (PARTITION BY sigla, t_local) > 1 AS multi,
       src_row
FROM dedup;
INSERT INTO clean.quarantine
  SELECT '{src}', row_id, sigla, hora_observacao, '{col}', CAST({col} AS VARCHAR), 'fora_da_faixa[{lo},{hi}]'
  FROM raw_{src} WHERE {col} IS NOT NULL AND NOT {DST} AND NOT ({col} BETWEEN {lo} AND {hi});
"""


def main():
    con = duckdb.connect(DB)
    # Limite de memória com transbordo para disco: o ambiente também roda PostgreSQL e Ontop (JVM).
    con.execute("SET memory_limit = '2GB'")
    con.execute("SET temp_directory = '/home/claude/metdata/duckdb_tmp'")
    con.execute("SET preserve_insertion_order = false")
    con.execute("CREATE SCHEMA IF NOT EXISTS clean")
    con.execute("""CREATE OR REPLACE TABLE clean.quarantine (
        source VARCHAR, row_id BIGINT, sigla VARCHAR, t_local TIMESTAMP, col VARCHAR, raw VARCHAR, reason VARCHAR)""")
    t0 = time.time()

    # R2: quarentena de horário de verão (todas as colunas da linha, registradas uma vez por linha)
    for src in ["temperatura", "pressao", "visibilidade", "precipitacao", "vento", "nuvem"]:
        con.execute(f"""INSERT INTO clean.quarantine
            SELECT '{src}', row_id, sigla, hora_observacao, '*', NULL, 'horario_de_verao_ambiguo'
            FROM raw_{src} WHERE {DST}""")

    for spec in SCALARS:
        con.execute(sql_scalar(*spec))

    # Vento: por cabeceira (R4 com cabeceira na chave)
    con.execute(f"""
CREATE OR REPLACE TABLE clean._wind AS
SELECT row_id, sigla, hora_observacao AS t_local,
       NULLIF(NULLIF(cabeceira, ''), 'nan') AS runway, velvento, dirvento, rajada
FROM raw_vento WHERE NOT {DST};
INSERT INTO clean.quarantine SELECT 'vento', row_id, sigla, t_local, 'velvento', CAST(velvento AS VARCHAR), 'fora_da_faixa[0,150]'
  FROM clean._wind WHERE velvento IS NOT NULL AND NOT velvento BETWEEN 0 AND 150;
INSERT INTO clean.quarantine SELECT 'vento', row_id, sigla, t_local, 'dirvento', CAST(dirvento AS VARCHAR), 'codigo_invalido'
  FROM clean._wind WHERE dirvento IS NOT NULL AND NOT (dirvento BETWEEN 0 AND 36 OR dirvento = 99);
INSERT INTO clean.quarantine SELECT 'vento', row_id, sigla, t_local, 'rajada', CAST(rajada AS VARCHAR), 'fora_da_faixa[0,200]'
  FROM clean._wind WHERE rajada IS NOT NULL AND NOT rajada BETWEEN 0 AND 200;
""")
    for name, col, cond, expr, typ, extra in [
        ("wind_speed", "velvento", "velvento BETWEEN 0 AND 150", "velvento", "DECIMAL(5,1)",
         ", CASE WHEN dirvento = 0 AND velvento = 0 THEN 'calm' WHEN dirvento = 99 THEN 'variable' END AS condition"),
        ("wind_dir", "dirvento", "dirvento BETWEEN 1 AND 36", "dirvento * 10", "INTEGER", ""),
        ("wind_gust", "rajada", "rajada BETWEEN 0 AND 200", "rajada", "DECIMAL(5,1)", ""),
    ]:
        extra_cols = ", condition" if extra else ""
        con.execute(f"""
CREATE OR REPLACE TABLE clean.obs_{name} AS
WITH valid AS (
  SELECT row_id, sigla, t_local, runway, CAST({expr} AS {typ}) AS value {extra}
  FROM clean._wind WHERE {col} IS NOT NULL AND {cond}
), dedup AS (
  SELECT sigla, t_local, runway, value {extra_cols}, MIN(row_id) AS src_row
  FROM valid GROUP BY ALL
)
SELECT sigla, t_local, t_local + INTERVAL 3 HOUR AS t_utc, CAST(t_local AS DATE) AS local_date,
       runway, value {extra_cols},
       CAST(ROW_NUMBER() OVER (PARTITION BY sigla, t_local ORDER BY runway NULLS LAST, value) - 1 AS SMALLINT) AS seq,
       COUNT(*) OVER (PARTITION BY sigla, t_local, runway) > 1 AS multi,
       src_row
FROM dedup""")
    con.execute("DROP TABLE clean._wind")

    # Precipitação (R5)
    con.execute(f"""
INSERT INTO clean.quarantine SELECT 'precipitacao', row_id, sigla, hora_observacao, 'precip', CAST(precip AS VARCHAR), 'excluido_boletim_nao_horario'
  FROM raw_precipitacao WHERE minute(hora_observacao) <> 0 AND precip IS NOT NULL AND NOT {DST};
INSERT INTO clean.quarantine SELECT 'precipitacao', row_id, sigla, hora_observacao, 'precip', CAST(precip AS VARCHAR), 'fora_da_faixa[0,150]'
  FROM raw_precipitacao WHERE minute(hora_observacao) = 0 AND precip IS NOT NULL AND NOT precip BETWEEN 0 AND 150 AND NOT {DST};
INSERT INTO clean.quarantine SELECT 'precipitacao', row_id, sigla, hora_observacao, 'durpreci', CAST(durpreci AS VARCHAR), 'fora_da_faixa[0,60]'
  FROM raw_precipitacao WHERE minute(hora_observacao) = 0 AND durpreci IS NOT NULL AND NOT durpreci BETWEEN 0 AND 60 AND NOT {DST};
""")
    for name, col, hi, typ in [("precip", "precip", 150, "DECIMAL(5,1)"), ("precip_duration", "durpreci", 60, "SMALLINT")]:
        con.execute(f"""
CREATE OR REPLACE TABLE clean.obs_{name} AS
WITH valid AS (
  SELECT row_id, sigla, hora_observacao AS t_local, CAST({col} AS {typ}) AS value
  FROM raw_precipitacao
  WHERE minute(hora_observacao) = 0 AND {col} IS NOT NULL AND {col} BETWEEN 0 AND {hi} AND NOT {DST}
), dedup AS (SELECT sigla, t_local, value, MIN(row_id) AS src_row FROM valid GROUP BY ALL)
SELECT sigla, t_local, t_local + INTERVAL 3 HOUR AS t_utc,
       t_local - INTERVAL 1 HOUR AS start_local, t_local + INTERVAL 2 HOUR AS start_utc,
       CAST(t_local - INTERVAL 1 HOUR AS DATE) AS local_date,
       value,
       CAST(ROW_NUMBER() OVER (PARTITION BY sigla, t_local ORDER BY value) - 1 AS SMALLINT) AS seq,
       COUNT(*) OVER (PARTITION BY sigla, t_local) > 1 AS multi, src_row
FROM dedup""")

    # Nuvens: uma observação por camada
    con.execute(f"""
INSERT INTO clean.quarantine SELECT 'nuvem', row_id, sigla, hora_observacao, 'qtdnuvem', qtdnuvem, 'codigo_invalido'
  FROM raw_nuvem WHERE NOT {DST} AND NOT (qtdnuvem IN ('1','2','3','4','5','6','7','8','9'));
CREATE OR REPLACE TABLE clean.obs_cloud_layer AS
WITH valid AS (
  SELECT row_id, sigla, hora_observacao AS t_local,
         CASE WHEN qtdnuvem = '9' THEN NULL ELSE CAST(qtdnuvem AS SMALLINT) END AS okta,
         qtdnuvem = '9' AS sky_obscured,
         CASE WHEN altnuvem BETWEEN 0 AND 999 THEN CAST(altnuvem * 10 AS INTEGER) END AS base_m,
         CASE WHEN tipo_nuvem IN ('/','X','') THEN NULL ELSE tipo_nuvem END AS genus,
         CASE WHEN direcao_nuvem IN ('N','NE','E','SE','S','SW','W','NW') THEN direcao_nuvem END AS movement
  FROM raw_nuvem WHERE NOT {DST} AND qtdnuvem IN ('1','2','3','4','5','6','7','8','9')
), dedup AS (
  SELECT sigla, t_local, okta, sky_obscured, base_m, genus, movement, MIN(row_id) AS src_row
  FROM valid GROUP BY ALL
)
SELECT sigla, t_local, t_local + INTERVAL 3 HOUR AS t_utc, CAST(t_local AS DATE) AS local_date,
       okta, sky_obscured, base_m, genus, movement,
       CAST(ROW_NUMBER() OVER (PARTITION BY sigla, t_local ORDER BY base_m NULLS LAST, okta, genus) - 1 AS SMALLINT) AS seq,
       src_row
FROM dedup""")

    quality_control(con)

    # Boletins e estações
    keys = " UNION ".join(f"SELECT sigla, hora_observacao FROM raw_{s} WHERE NOT {DST}"
                          for s in ["temperatura", "pressao", "visibilidade", "precipitacao", "vento", "nuvem"])
    con.execute(f"""
CREATE OR REPLACE TABLE clean.report AS
SELECT sigla, hora_observacao AS t_local, hora_observacao + INTERVAL 3 HOUR AS t_utc,
       CAST(hora_observacao AS DATE) AS local_date, minute(hora_observacao) = 0 AS is_hourly
FROM ({keys})""")
    con.execute("CREATE OR REPLACE TABLE clean.station AS SELECT DISTINCT sigla FROM clean.report ORDER BY sigla")

    print(f"transformação em {time.time()-t0:.0f}s")
    for (t,) in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='clean' ORDER BY 1").fetchall():
        print(f"  clean.{t}: {con.execute(f'SELECT COUNT(*) FROM clean.{t}').fetchone()[0]:,}")
    print(con.execute("SELECT source, reason, COUNT(*) FROM clean.quarantine GROUP BY 1,2 ORDER BY 1,3 DESC").fetchall())
    con.close()


def _move(con, table, src_file, col, where, reason):
    """Move linhas de clean.<table> que satisfazem `where` para a quarentena."""
    con.execute(f"""INSERT INTO clean.quarantine
        SELECT '{src_file}', src_row, sigla, t_local, '{col}', CAST(value AS VARCHAR), '{reason}'
        FROM clean.{table} WHERE {where}""")
    n = con.execute(f"SELECT COUNT(*) FROM clean.{table} WHERE {where}").fetchone()[0]
    con.execute(f"DELETE FROM clean.{table} WHERE {where}")
    return n


def quality_control(con):
    """Q1–Q3: testes de consistência que a faixa física não pega (ver REGRAS_LIMPEZA.md)."""
    out = {}
    # Q1a código de erro: mesmo valor ≥ 50 mm repetido ≥ 5 vezes na mesma estação (ex.: 100,2 mm em SBIT)
    out["Q1a"] = _move(con, "obs_precip", "precipitacao", "precip", """
        value >= 50 AND (sigla, value) IN (SELECT sigla, value FROM clean.obs_precip
                                           WHERE value >= 50 GROUP BY 1, 2 HAVING COUNT(*) >= 5)""",
        "codigo_de_erro_valor_repetido")
    # Q1b chuva ≥ 0,1 mm com duração 0 min: o par é inconsistente; descarta-se a DURAÇÃO, mantém-se a chuva
    out["Q1b"] = _move(con, "obs_precip_duration", "precipitacao", "durpreci", """
        value = 0 AND EXISTS (SELECT 1 FROM clean.obs_precip p
          WHERE p.sigla = obs_precip_duration.sigla AND p.t_local = obs_precip_duration.t_local AND p.value > 0)""",
        "inconsistente_duracao_zero_com_chuva")
    # Q2 sensor travado: mesmo valor ≥ 20 mm em ≥ 3 boletins horários consecutivos
    con.execute("""CREATE OR REPLACE TEMP TABLE stuck AS
      WITH s AS (SELECT sigla, t_local, value,
                 LAG(value,1) OVER w AS p1, LAG(value,2) OVER w AS p2,
                 LEAD(value,1) OVER w AS n1, LEAD(value,2) OVER w AS n2
                 FROM clean.obs_precip WHERE seq = 0 WINDOW w AS (PARTITION BY sigla ORDER BY t_local))
      SELECT sigla, t_local FROM s WHERE value >= 20 AND (
        (value = p1 AND value = p2) OR (value = p1 AND value = n1) OR (value = n1 AND value = n2))""")
    out["Q2"] = _move(con, "obs_precip", "precipitacao", "precip",
                      "(sigla, t_local) IN (SELECT sigla, t_local FROM stuck)", "sensor_travado")
    # Q3 pico isolado: difere > limiar da média dos instantes vizinhos (≤ 3 h) dos dois lados, no mesmo sentido
    for table, src, col, lim in [("obs_air_temp", "temperatura", "bseco", 8), ("obs_dew_point", "temperatura", "temppo", 8),
                                 ("obs_qnh", "pressao", "qnh", 8)]:
        con.execute(f"""CREATE OR REPLACE TEMP TABLE spikes AS
          WITH m AS (SELECT sigla, t_local, AVG(value) AS v FROM clean.{table} GROUP BY 1, 2),
          nb AS (SELECT sigla, t_local, LAG(v) OVER w AS pv, LEAD(v) OVER w AS nv,
                        LAG(t_local) OVER w AS tp, LEAD(t_local) OVER w AS tn
                 FROM m WINDOW w AS (PARTITION BY sigla ORDER BY t_local))
          SELECT o.sigla, o.t_local, o.seq FROM clean.{table} o JOIN nb USING (sigla, t_local)
          WHERE pv IS NOT NULL AND nv IS NOT NULL
            AND o.t_local - tp <= INTERVAL 3 HOUR AND tn - o.t_local <= INTERVAL 3 HOUR
            AND ((o.value - pv > {lim} AND o.value - nv > {lim}) OR (pv - o.value > {lim} AND nv - o.value > {lim}))""")
        out[f"Q3_{table}"] = _move(con, table, src, col,
                                   "(sigla, t_local, seq) IN (SELECT sigla, t_local, seq FROM spikes)", "pico_isolado")
    # Q4 rajada inconsistente com o vento médio da mesma cabeceira: rajada < média ou rajada − média > 50 kt
    out["Q4"] = _move(con, "obs_wind_gust", "vento", "rajada", """
        EXISTS (SELECT 1 FROM clean.obs_wind_speed s
                WHERE s.sigla = obs_wind_gust.sigla AND s.t_local = obs_wind_gust.t_local
                  AND s.runway IS NOT DISTINCT FROM obs_wind_gust.runway
                  AND (obs_wind_gust.value < s.value OR obs_wind_gust.value - s.value > 50))""",
        "rajada_inconsistente_com_media")
    # Q5 pico isolado de velocidade do vento (por cabeceira): > 25 kt acima dos dois vizinhos (≤ 3 h)
    con.execute("""CREATE OR REPLACE TEMP TABLE wspk AS
      WITH m AS (SELECT sigla, runway, t_local, AVG(value) AS v FROM clean.obs_wind_speed GROUP BY 1, 2, 3),
      nb AS (SELECT sigla, runway, t_local, LAG(v) OVER w AS pv, LEAD(v) OVER w AS nv,
                    LAG(t_local) OVER w AS tp, LEAD(t_local) OVER w AS tn
             FROM m WINDOW w AS (PARTITION BY sigla, runway ORDER BY t_local))
      SELECT o.sigla, o.t_local, o.seq FROM clean.obs_wind_speed o
      JOIN nb ON nb.sigla = o.sigla AND nb.t_local = o.t_local AND nb.runway IS NOT DISTINCT FROM o.runway
      WHERE pv IS NOT NULL AND nv IS NOT NULL
        AND o.t_local - tp <= INTERVAL 3 HOUR AND tn - o.t_local <= INTERVAL 3 HOUR
        AND o.value - pv > 25 AND o.value - nv > 25""")
    out["Q5"] = _move(con, "obs_wind_speed", "vento", "velvento",
                      "(sigla, t_local, seq) IN (SELECT sigla, t_local, seq FROM wspk)", "pico_isolado")
    print("controle de qualidade (linhas movidas para quarentena):", out)


if __name__ == "__main__":
    main()
