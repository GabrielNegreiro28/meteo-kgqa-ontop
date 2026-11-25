"""Camada limpa (schema `clean`) a partir das tabelas brutas `raw_*` no DuckDB.

Regras (documentadas em data/REGRAS_LIMPEZA.md):
  R1 Tempo (corrigida em 25/11/2026, conferida contra METAR em UTC: data/VERIFICACAO_PREMISSAS.md): o relógio de hora_observacao mudou.
     Até 15/04/2021 (e no lote de 19/04/2021) é a hora legal PADRÃO da estação, sem horário de verão (UTC−2 a UTC−5, data/estacoes.csv);
     de 16/04/2021 em diante é UTC. t_utc sai dessa regra; t_local e local_date são a hora e o dia CIVIS da estação (zona IANA, com o
     horário de verão onde e quando vigorou). As poucas linhas de 16 a 30/04/2021 fora da nuvem (relógio incerto) vão para quarentena.
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
As faixas físicas (R3) vêm do catálogo de grandezas (ontology/catalog.py), na unidade canônica; aqui elas só são levadas à unidade
BRUTA de cada coluna (dam -> m e dezenas de graus -> graus dividem por 10). O SHACL usa as mesmas faixas.
Uso: python ingest/transform.py /home/claude/metdata/met.duckdb
"""
import os, sys, time
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ontology.catalog import quantity_by_sensor  # noqa: E402


def R(sensor, scale=1):
    """Faixa física do catálogo na unidade bruta da coluna (valor canônico = bruto * scale)."""
    q = quantity_by_sensor(sensor)
    as_num = lambda d: int(d) if d == d.to_integral_value() else float(d)
    return as_num(q.low / scale), as_num(q.high / scale)

DB = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MET_HOME", "/home/claude/metdata") + "/met.duckdb"
DST = ("(CAST(clock AS DATE) IN (DATE '2016-10-16', DATE '2017-10-15', DATE '2018-11-04') "
       "AND hour(clock) = 1)")
STATIONS = Path(__file__).resolve().parent.parent / "data" / "estacoes.csv"
SWITCH = "TIMESTAMP '2021-04-16'"                 # primeiro instante em UTC (R1)
OLD_BATCH = "DATE '2021-04-19'"                   # lote tardio ainda no relógio antigo
TRANSITION = (f"(clock >= {SWITCH} AND clock < TIMESTAMP '2021-05-01' AND CAST(clock AS DATE) <> {OLD_BATCH})")
SOURCES = ["temperatura", "pressao", "visibilidade", "precipitacao", "vento", "nuvem"]


def local(t: str) -> str:
    """Instante UTC (TIMESTAMP sem fuso) -> hora civil da estação; exige `z.fuso_iana` no FROM."""
    return f"timezone(z.fuso_iana, timezone('UTC', {t}))"


def sources(con) -> None:
    """R1: visões src_* = raw_* com `clock` (o relógio do CSV) e `hora_observacao` = instante UTC verdadeiro."""
    con.execute(f"""CREATE OR REPLACE TABLE clean.station_tz AS
        SELECT sigla, CAST(fuso_legal AS INTEGER) AS fuso_legal, fuso_iana FROM read_csv('{STATIONS}', header = true, all_varchar = true)""")
    for src in SOURCES:
        con.execute(f"""CREATE OR REPLACE TEMP VIEW src_{src} AS
            SELECT r.* EXCLUDE (hora_observacao), r.hora_observacao AS clock,
                   CASE WHEN r.hora_observacao < {SWITCH} OR CAST(r.hora_observacao AS DATE) = {OLD_BATCH}
                        THEN r.hora_observacao + to_hours(-z.fuso_legal) ELSE r.hora_observacao END AS hora_observacao
            FROM raw_{src} r JOIN clean.station_tz z USING (sigla)""")
        missing = con.execute(f"SELECT COUNT(*) FROM raw_{src} WHERE sigla NOT IN (SELECT sigla FROM clean.station_tz)").fetchone()[0]
        assert missing == 0, f"{src}: {missing} linhas de estação fora de data/estacoes.csv"

# nome, tabela bruta, coluna, (lo, hi) na unidade bruta (do catálogo), expressão do valor canônico, tipo SQL
SCALARS = [
    ("air_temp",      "temperatura",  "bseco",     R("air_temp"),          "raw",      "DECIMAL(5,1)"),
    ("wet_bulb",      "temperatura",  "bumido",    R("wet_bulb"),          "raw",      "DECIMAL(5,1)"),
    ("dew_point",     "temperatura",  "temppo",    R("dew_point"),         "raw",      "DECIMAL(5,1)"),
    ("rel_humidity",  "temperatura",  "ur",        R("rel_humidity"),      "raw",      "DECIMAL(5,1)"),
    ("runway_temp",   "temperatura",  "temppista", R("runway_temp"),       "raw",      "DECIMAL(5,1)"),
    ("qnh",           "pressao",      "qnh",       R("qnh"),               "raw",      "DECIMAL(6,1)"),
    ("visibility",    "visibilidade", "visibpre",  R("visibility", 10),    "raw * 10", "INTEGER"),
]
WS, WD, WG = R("wind_speed"), R("wind_dir", 10), R("wind_gust")        # vento: nós, dezenas de graus, nós
PR, PD, CB = R("precip"), R("precip_duration"), R("cloud_base", 10)    # mm, minutos, base da nuvem em dam


def sql_scalar(name, src, col, rng, expr, typ):
    lo, hi = rng
    return f"""
CREATE OR REPLACE TABLE clean.obs_{name} AS
WITH base AS (
  SELECT row_id, sigla, hora_observacao AS t_inst, {col} AS raw
  FROM src_{src} WHERE {col} IS NOT NULL AND NOT {DST} AND NOT {TRANSITION}
), valid AS (
  SELECT row_id, sigla, t_inst, CAST({expr} AS {typ}) AS value FROM base WHERE raw BETWEEN {lo} AND {hi}
), dedup AS (
  SELECT sigla, t_inst, value, MIN(row_id) AS src_row FROM valid GROUP BY sigla, t_inst, value
)
SELECT d.sigla, {local('d.t_inst')} AS t_local, d.t_inst AS t_utc, CAST({local('d.t_inst')} AS DATE) AS local_date,
       d.value,
       CAST(ROW_NUMBER() OVER (PARTITION BY d.sigla, d.t_inst ORDER BY d.value) - 1 AS SMALLINT) AS seq,
       COUNT(*) OVER (PARTITION BY d.sigla, d.t_inst) > 1 AS multi,
       d.src_row
FROM dedup d JOIN clean.station_tz z USING (sigla);
INSERT INTO clean.quarantine
  SELECT '{src}', row_id, sigla, clock, '{col}', CAST({col} AS VARCHAR), 'fora_da_faixa[{lo},{hi}]'
  FROM src_{src} WHERE {col} IS NOT NULL AND NOT {DST} AND NOT {TRANSITION} AND NOT ({col} BETWEEN {lo} AND {hi});
"""


def main():
    con = duckdb.connect(DB)
    # Limite de memória com transbordo para disco: o ambiente também roda PostgreSQL e Ontop (JVM).
    con.execute("SET memory_limit = '2GB'")
    con.execute(f"SET temp_directory = '{os.environ.get('MET_HOME', '/home/claude/metdata')}/duckdb_tmp'")
    con.execute("SET preserve_insertion_order = false")
    con.execute("CREATE SCHEMA IF NOT EXISTS clean")
    con.execute("""CREATE OR REPLACE TABLE clean.quarantine (
        source VARCHAR, row_id BIGINT, sigla VARCHAR, t_local TIMESTAMP, col VARCHAR, raw VARCHAR, reason VARCHAR)""")
    t0 = time.time()

    sources(con)
    # R2: quarentena de horário de verão (todas as colunas da linha, registradas uma vez por linha)
    for src in SOURCES:
        con.execute(f"""INSERT INTO clean.quarantine
            SELECT '{src}', row_id, sigla, clock, '*', NULL, 'horario_de_verao_ambiguo'
            FROM src_{src} WHERE {DST}""")
        if src != "nuvem":                             # R1: transição de abril de 2021 com relógio incerto
            con.execute(f"""INSERT INTO clean.quarantine
                SELECT '{src}', row_id, sigla, clock, '*', NULL, 'transicao_de_relogio_2021'
                FROM src_{src} WHERE {TRANSITION} AND NOT {DST}""")

    for spec in SCALARS:
        con.execute(sql_scalar(*spec))

    # Vento: por cabeceira (R4 com cabeceira na chave)
    con.execute(f"""
CREATE OR REPLACE TABLE clean._wind AS
SELECT row_id, sigla, hora_observacao AS t_inst, clock,
       NULLIF(NULLIF(cabeceira, ''), 'nan') AS runway, velvento, dirvento, rajada
FROM src_vento WHERE NOT {DST} AND NOT {TRANSITION};
INSERT INTO clean.quarantine SELECT 'vento', row_id, sigla, clock, 'velvento', CAST(velvento AS VARCHAR), 'fora_da_faixa[{WS[0]},{WS[1]}]'
  FROM clean._wind WHERE velvento IS NOT NULL AND NOT velvento BETWEEN {WS[0]} AND {WS[1]};
INSERT INTO clean.quarantine SELECT 'vento', row_id, sigla, clock, 'dirvento', CAST(dirvento AS VARCHAR), 'codigo_invalido'
  FROM clean._wind WHERE dirvento IS NOT NULL AND NOT (dirvento BETWEEN 0 AND {WD[1]} OR dirvento = 99);
INSERT INTO clean.quarantine SELECT 'vento', row_id, sigla, clock, 'rajada', CAST(rajada AS VARCHAR), 'fora_da_faixa[{WG[0]},{WG[1]}]'
  FROM clean._wind WHERE rajada IS NOT NULL AND NOT rajada BETWEEN {WG[0]} AND {WG[1]};
""")
    for name, col, cond, expr, typ, extra in [
        ("wind_speed", "velvento", f"velvento BETWEEN {WS[0]} AND {WS[1]}", "velvento", "DECIMAL(5,1)",
         ", CASE WHEN dirvento = 0 AND velvento = 0 THEN 'calm' WHEN dirvento = 99 THEN 'variable' END AS condition"),
        ("wind_dir", "dirvento", f"dirvento BETWEEN {WD[0]} AND {WD[1]}", "dirvento * 10", "INTEGER", ""),
        ("wind_gust", "rajada", f"rajada BETWEEN {WG[0]} AND {WG[1]}", "rajada", "DECIMAL(5,1)", ""),
    ]:
        extra_cols = ", condition" if extra else ""
        con.execute(f"""
CREATE OR REPLACE TABLE clean.obs_{name} AS
WITH valid AS (
  SELECT row_id, sigla, t_inst, runway, CAST({expr} AS {typ}) AS value {extra}
  FROM clean._wind WHERE {col} IS NOT NULL AND {cond}
), dedup AS (
  SELECT sigla, t_inst, runway, value {extra_cols}, MIN(row_id) AS src_row
  FROM valid GROUP BY ALL
)
SELECT d.sigla, {local('d.t_inst')} AS t_local, d.t_inst AS t_utc, CAST({local('d.t_inst')} AS DATE) AS local_date,
       d.runway, d.value {extra_cols.replace(', ', ', d.')},
       CAST(ROW_NUMBER() OVER (PARTITION BY d.sigla, d.t_inst ORDER BY d.runway NULLS LAST, d.value) - 1 AS SMALLINT) AS seq,
       COUNT(*) OVER (PARTITION BY d.sigla, d.t_inst, d.runway) > 1 AS multi,
       d.src_row
FROM dedup d JOIN clean.station_tz z USING (sigla)""")
    con.execute("DROP TABLE clean._wind")

    # Precipitação (R5)
    con.execute(f"""
INSERT INTO clean.quarantine SELECT 'precipitacao', row_id, sigla, clock, 'precip', CAST(precip AS VARCHAR), 'excluido_boletim_nao_horario'
  FROM src_precipitacao WHERE minute(hora_observacao) <> 0 AND precip IS NOT NULL AND NOT {DST} AND NOT {TRANSITION};
INSERT INTO clean.quarantine SELECT 'precipitacao', row_id, sigla, clock, 'precip', CAST(precip AS VARCHAR), 'fora_da_faixa[{PR[0]},{PR[1]}]'
  FROM src_precipitacao WHERE minute(hora_observacao) = 0 AND precip IS NOT NULL AND NOT precip BETWEEN {PR[0]} AND {PR[1]} AND NOT {DST} AND NOT {TRANSITION};
INSERT INTO clean.quarantine SELECT 'precipitacao', row_id, sigla, clock, 'durpreci', CAST(durpreci AS VARCHAR), 'fora_da_faixa[{PD[0]},{PD[1]}]'
  FROM src_precipitacao WHERE minute(hora_observacao) = 0 AND durpreci IS NOT NULL AND NOT durpreci BETWEEN {PD[0]} AND {PD[1]} AND NOT {DST} AND NOT {TRANSITION};
""")
    for name, col, hi, typ in [("precip", "precip", PR[1], "DECIMAL(5,1)"), ("precip_duration", "durpreci", PD[1], "SMALLINT")]:
        con.execute(f"""
CREATE OR REPLACE TABLE clean.obs_{name} AS
WITH valid AS (
  SELECT row_id, sigla, hora_observacao AS t_inst, CAST({col} AS {typ}) AS value
  FROM src_precipitacao
  WHERE minute(hora_observacao) = 0 AND {col} IS NOT NULL AND {col} BETWEEN 0 AND {hi} AND NOT {DST} AND NOT {TRANSITION}
), dedup AS (SELECT sigla, t_inst, value, MIN(row_id) AS src_row FROM valid GROUP BY ALL)
SELECT d.sigla, {local('d.t_inst')} AS t_local, d.t_inst AS t_utc,
       {local("d.t_inst - INTERVAL 1 HOUR")} AS start_local, d.t_inst - INTERVAL 1 HOUR AS start_utc,
       CAST({local("d.t_inst - INTERVAL 1 HOUR")} AS DATE) AS local_date,
       d.value,
       CAST(ROW_NUMBER() OVER (PARTITION BY d.sigla, d.t_inst ORDER BY d.value) - 1 AS SMALLINT) AS seq,
       COUNT(*) OVER (PARTITION BY d.sigla, d.t_inst) > 1 AS multi, d.src_row
FROM dedup d JOIN clean.station_tz z USING (sigla)""")

    # Nuvens: uma observação por camada
    con.execute(f"""
INSERT INTO clean.quarantine SELECT 'nuvem', row_id, sigla, clock, 'qtdnuvem', qtdnuvem, 'codigo_invalido'
  FROM src_nuvem WHERE NOT {DST} AND NOT (qtdnuvem IN ('1','2','3','4','5','6','7','8','9'));
CREATE OR REPLACE TABLE clean.obs_cloud_layer AS
WITH valid AS (
  SELECT row_id, sigla, hora_observacao AS t_inst,
         CASE WHEN qtdnuvem = '9' THEN NULL ELSE CAST(qtdnuvem AS SMALLINT) END AS okta,
         qtdnuvem = '9' AS sky_obscured,
         CASE WHEN altnuvem BETWEEN {CB[0]} AND {CB[1]} THEN CAST(altnuvem * 10 AS INTEGER) END AS base_m,
         CASE WHEN tipo_nuvem IN ('/','X','') THEN NULL ELSE tipo_nuvem END AS genus,
         CASE WHEN direcao_nuvem IN ('N','NE','E','SE','S','SW','W','NW') THEN direcao_nuvem END AS movement
  FROM src_nuvem WHERE NOT {DST} AND qtdnuvem IN ('1','2','3','4','5','6','7','8','9')
), dedup AS (
  SELECT sigla, t_inst, okta, sky_obscured, base_m, genus, movement, MIN(row_id) AS src_row
  FROM valid GROUP BY ALL
)
SELECT d.sigla, {local('d.t_inst')} AS t_local, d.t_inst AS t_utc, CAST({local('d.t_inst')} AS DATE) AS local_date,
       d.okta, d.sky_obscured, d.base_m, d.genus, d.movement,
       CAST(ROW_NUMBER() OVER (PARTITION BY d.sigla, d.t_inst ORDER BY d.base_m NULLS LAST, d.okta, d.genus) - 1 AS SMALLINT) AS seq,
       d.src_row
FROM dedup d JOIN clean.station_tz z USING (sigla)""")

    quality_control(con)

    # Boletins e estações
    keys = " UNION ".join(f"SELECT sigla, hora_observacao FROM src_{s} WHERE NOT {DST}" + ("" if s == "nuvem" else f" AND NOT {TRANSITION}")
                          for s in SOURCES)
    con.execute(f"""
CREATE OR REPLACE TABLE clean.report AS
SELECT k.sigla, {local('k.hora_observacao')} AS t_local, k.hora_observacao AS t_utc,
       CAST({local('k.hora_observacao')} AS DATE) AS local_date, minute(k.hora_observacao) = 0 AS is_hourly
FROM ({keys}) k JOIN clean.station_tz z USING (sigla)""")
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
          WHERE p.sigla = obs_precip_duration.sigla AND p.t_utc = obs_precip_duration.t_utc AND p.value > 0)""",
        "inconsistente_duracao_zero_com_chuva")
    # Q2 sensor travado: mesmo valor ≥ 20 mm em ≥ 3 boletins horários CONSECUTIVOS. "Consecutivo" é de hora em hora: LAG/LEAD por linha
    # juntava leituras espaçadas (25 mm em 01/01/2019, 01/06/2019 e 01/01/2020 marcavam as três como travadas; Codex C09).
    con.execute("""CREATE OR REPLACE TEMP TABLE stuck AS
      WITH s AS (SELECT sigla, t_utc, value,
                 value = LAG(value,1) OVER w AND t_utc - LAG(t_utc,1) OVER w = INTERVAL 1 HOUR AS same_prev,
                 value = LEAD(value,1) OVER w AND LEAD(t_utc,1) OVER w - t_utc = INTERVAL 1 HOUR AS same_next,
                 value = LAG(value,2) OVER w AND t_utc - LAG(t_utc,1) OVER w = INTERVAL 1 HOUR
                       AND LAG(t_utc,1) OVER w - LAG(t_utc,2) OVER w = INTERVAL 1 HOUR AS same_prev2,
                 value = LEAD(value,2) OVER w AND LEAD(t_utc,1) OVER w - t_utc = INTERVAL 1 HOUR
                       AND LEAD(t_utc,2) OVER w - LEAD(t_utc,1) OVER w = INTERVAL 1 HOUR AS same_next2
                 FROM clean.obs_precip WHERE seq = 0 WINDOW w AS (PARTITION BY sigla ORDER BY t_utc))
      SELECT sigla, t_utc FROM s WHERE value >= 20 AND (
        (same_prev AND same_prev2) OR (same_prev AND same_next) OR (same_next AND same_next2))""")
    out["Q2"] = _move(con, "obs_precip", "precipitacao", "precip",
                      "(sigla, t_utc) IN (SELECT sigla, t_utc FROM stuck)", "sensor_travado")
    # Q3 pico isolado: difere > limiar da média dos instantes vizinhos (≤ 3 h) dos dois lados, no mesmo sentido
    for table, src, col, lim in [("obs_air_temp", "temperatura", "bseco", 8), ("obs_dew_point", "temperatura", "temppo", 8),
                                 ("obs_qnh", "pressao", "qnh", 8)]:
        con.execute(f"""CREATE OR REPLACE TEMP TABLE spikes AS
          WITH m AS (SELECT sigla, t_utc, AVG(value) AS v FROM clean.{table} GROUP BY 1, 2),
          nb AS (SELECT sigla, t_utc, LAG(v) OVER w AS pv, LEAD(v) OVER w AS nv,
                        LAG(t_utc) OVER w AS tp, LEAD(t_utc) OVER w AS tn
                 FROM m WINDOW w AS (PARTITION BY sigla ORDER BY t_utc))
          SELECT o.sigla, o.t_utc, o.seq FROM clean.{table} o JOIN nb USING (sigla, t_utc)
          WHERE pv IS NOT NULL AND nv IS NOT NULL
            AND o.t_utc - tp <= INTERVAL 3 HOUR AND tn - o.t_utc <= INTERVAL 3 HOUR
            AND ((o.value - pv > {lim} AND o.value - nv > {lim}) OR (pv - o.value > {lim} AND nv - o.value > {lim}))""")
        out[f"Q3_{table}"] = _move(con, table, src, col,
                                   "(sigla, t_utc, seq) IN (SELECT sigla, t_utc, seq FROM spikes)", "pico_isolado")
    # Q4 rajada inconsistente com o vento médio da mesma cabeceira: rajada < média ou rajada − média > 50 kt
    out["Q4"] = _move(con, "obs_wind_gust", "vento", "rajada", """
        EXISTS (SELECT 1 FROM clean.obs_wind_speed s
                WHERE s.sigla = obs_wind_gust.sigla AND s.t_utc = obs_wind_gust.t_utc
                  AND s.runway IS NOT DISTINCT FROM obs_wind_gust.runway
                  AND (obs_wind_gust.value < s.value OR obs_wind_gust.value - s.value > 50))""",
        "rajada_inconsistente_com_media")
    # Q5 pico isolado de velocidade do vento (por cabeceira): > 25 kt acima dos dois vizinhos (≤ 3 h)
    con.execute("""CREATE OR REPLACE TEMP TABLE wspk AS
      WITH m AS (SELECT sigla, runway, t_utc, AVG(value) AS v FROM clean.obs_wind_speed GROUP BY 1, 2, 3),
      nb AS (SELECT sigla, runway, t_utc, LAG(v) OVER w AS pv, LEAD(v) OVER w AS nv,
                    LAG(t_utc) OVER w AS tp, LEAD(t_utc) OVER w AS tn
             FROM m WINDOW w AS (PARTITION BY sigla, runway ORDER BY t_utc))
      SELECT o.sigla, o.t_utc, o.seq FROM clean.obs_wind_speed o
      JOIN nb ON nb.sigla = o.sigla AND nb.t_utc = o.t_utc AND nb.runway IS NOT DISTINCT FROM o.runway
      WHERE pv IS NOT NULL AND nv IS NOT NULL
        AND o.t_utc - tp <= INTERVAL 3 HOUR AND tn - o.t_utc <= INTERVAL 3 HOUR
        AND o.value - pv > 25 AND o.value - nv > 25""")
    out["Q5"] = _move(con, "obs_wind_speed", "vento", "velvento",
                      "(sigla, t_utc, seq) IN (SELECT sigla, t_utc, seq FROM wspk)", "pico_isolado")
    print("controle de qualidade (linhas movidas para quarentena):", out)
    return out


if __name__ == "__main__":
    main()
