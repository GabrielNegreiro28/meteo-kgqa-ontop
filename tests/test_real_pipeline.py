"""Testes da ingestão real e do grafo virtual (Ontop).

Pulados automaticamente quando a base local ou o endpoint não estão disponíveis (ex.: em outra máquina).
  - âncoras: valores calculados DIRETO do CSV bruto no computador do Gabriel (perfil de 14/10/2026),
    sem passar pela limpeza nem pelo grafo;
  - reconciliação: toda linha bruta termina no grafo, na quarentena ou colapsada como duplicata idêntica;
  - grafo x oráculo: as 15 consultas de referência reais;
  - mutações: consultas plausíveis porém erradas precisam falhar na comparação.
"""
import os
import urllib.request
from decimal import Decimal

import pytest

DUCK = "/home/claude/metdata/met.duckdb"
duck_ok = os.path.exists(DUCK)
try:
    urllib.request.urlopen(urllib.request.Request(
        "http://127.0.0.1:8080/sparql", data=b"query=ASK%7B%7D", method="POST",
        headers={"Accept": "application/sparql-results+json",
                 "Content-Type": "application/x-www-form-urlencoded"}), timeout=5)
    ontop_ok = True
except Exception:
    ontop_ok = False

needs_duck = pytest.mark.skipif(not duck_ok, reason="base DuckDB local ausente")
needs_ontop = pytest.mark.skipif(not ontop_ok, reason="endpoint Ontop fora do ar")


@pytest.fixture(scope="module")
def con():
    import duckdb
    c = duckdb.connect(DUCK, read_only=True)
    yield c
    c.close()


# ---------- âncoras do CSV bruto (perfil feito no computador do Gabriel) ----------

RAW_ROWS = {"precipitacao": 8_210_344, "pressao": 8_638_937, "visibilidade": 8_638_728,
            "temperatura": 10_307_346, "vento": 13_224_256, "nuvem": 12_648_891}


@needs_duck
@pytest.mark.parametrize("table,n", RAW_ROWS.items())
def test_raw_row_counts_match_source_profile(con, table, n):
    assert con.execute(f"SELECT COUNT(*) FROM raw_{table}").fetchone()[0] == n


@needs_duck
def test_annual_rain_anchors(con):
    # Somado no computador do Gabriel direto do CSV (boletins da hora cheia), antes de qualquer limpeza.
    got = dict(con.execute("""SELECT sigla, CAST(SUM(value) AS DOUBLE) FROM clean.obs_precip
                              WHERE sigla IN ('SBBE','SBGR') AND year(t_local) = 2019 GROUP BY 1""").fetchall())
    assert got == pytest.approx({"SBBE": 3196.0, "SBGR": 1834.2})


# ---------- reconciliação bruto = limpo + quarentena + duplicatas colapsadas ----------

DST = ("(CAST(hora_observacao AS DATE) IN (DATE '2016-10-16', DATE '2017-10-15', DATE '2018-11-04') "
       "AND hour(hora_observacao) = 1)")


@needs_duck
@pytest.mark.parametrize("src,col,table", [("pressao", "qnh", "obs_qnh"), ("temperatura", "bseco", "obs_air_temp"),
                                           ("visibilidade", "visibpre", "obs_visibility")])
def test_every_raw_value_is_accounted_for(con, src, col, table):
    """Nível 1 (linhas brutas): bruto = fora da faixa + dentro da faixa.
    Nível 2 (trios distintos estação/instante/valor): dentro da faixa colapsa em trios;
    cada trio vira uma observação no grafo OU uma entrada de quarentena do controle de qualidade."""
    q = lambda s: con.execute(s).fetchone()[0]
    base = f"FROM raw_{src} WHERE {col} IS NOT NULL AND NOT {DST}"
    raw = q(f"SELECT COUNT(*) {base}")
    out_of_range = q(f"SELECT COUNT(*) FROM clean.quarantine WHERE source='{src}' AND col='{col}' AND reason LIKE 'fora_da_faixa%'")
    in_range_ids = f"row_id NOT IN (SELECT row_id FROM clean.quarantine WHERE source='{src}' AND col='{col}' AND reason LIKE 'fora_da_faixa%')"
    in_range = q(f"SELECT COUNT(*) {base} AND {in_range_ids}")
    triples = q(f"SELECT COUNT(DISTINCT (sigla, hora_observacao, {col})) {base} AND {in_range_ids}")
    qc = q(f"SELECT COUNT(*) FROM clean.quarantine WHERE source='{src}' AND col='{col}' AND reason NOT LIKE 'fora_da_faixa%'")
    clean = q(f"SELECT COUNT(*) FROM clean.{table}")
    assert raw == out_of_range + in_range
    assert triples == clean + qc


@needs_duck
def test_no_impossible_values_left(con):
    q = lambda s: con.execute(s).fetchone()[0]
    assert q("SELECT MAX(CAST(value AS DOUBLE)) FROM clean.obs_air_temp") < 46
    assert q("SELECT MAX(CAST(value AS DOUBLE)) FROM clean.obs_wind_gust") <= 100
    assert q("SELECT MAX(s) FROM (SELECT SUM(CAST(value AS DOUBLE)) s FROM clean.obs_precip GROUP BY sigla, year(t_local))") < 5000


# ---------- grafo virtual x oráculo ----------

@needs_duck
@needs_ontop
def test_real_reference_suite():
    from eval.run_reference import run
    rep = [e for e in run(suite="real") if e["checked"] == "executed"]
    failed = [(e["id"], e["detail"]) for e in rep if not e["passed"]]
    assert len(rep) == 15 and not failed, failed


@needs_duck
@needs_ontop
def test_mutation_precip_day_by_utc_end_time_is_wrong():
    """Somar a chuva do dia pelo instante FINAL em UTC desloca 4 horas: resultado deve divergir do oráculo."""
    from eval import oracle_real
    from eval.compare import compare, rows_from_sparql
    from kgqa.store import PREFIXES, OntopBackend
    wrong = """SELECT (SUM(?v) AS ?total) (COUNT(?v) AS ?n) WHERE {
      st:SBGR sosa:hosts ?s .
      ?o sosa:madeBySensor ?s ; sosa:observedProperty met:Precipitation ; sosa:resultTime ?t ;
         sosa:hasResult/qudt:numericValue ?v .
      FILTER(?t >= "2024-01-19T00:00:00Z"^^xsd:dateTime && ?t < "2024-01-20T00:00:00Z"^^xsd:dateTime) }"""
    r = OntopBackend().select(PREFIXES + wrong, timeout_s=60)
    assert r.ok
    ok, _ = compare(rows_from_sparql(r.results, ["total", "n"]), oracle_real.expected("RT07"),
                    {"mode": "per_group", "columns": ["total", "n"], "key": [], "tolerance": {"total": 0.001}})
    assert not ok


@needs_ontop
def test_ontop_is_read_only_at_database_level():
    import psycopg
    with psycopg.connect("host=127.0.0.1 port=5433 user=kgqa_reader dbname=met") as c:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            c.execute("DELETE FROM station WHERE sigla = 'XXXX'")


@needs_ontop
def test_ontop_backend_policy_and_truncation():
    from kgqa.store import PREFIXES, OntopBackend
    b = OntopBackend()
    assert b.select("INSERT DATA { <urn:a> <urn:b> <urn:c> }").error_kind == "policy"
    r = b.select(PREFIXES + "SELECT ?s WHERE { ?s a met:WeatherStation }", max_rows=10)
    assert r.ok and r.truncated and len(r.results["results"]["bindings"]) == 10


@needs_ontop
def test_ontop_results_are_typed_and_in_utc():
    from kgqa.store import PREFIXES, OntopBackend
    r = OntopBackend().select(PREFIXES + """SELECT ?t ?v WHERE { st:SBBE sosa:hosts ?s .
        ?o sosa:madeBySensor ?s ; sosa:observedProperty met:AirTemperature ; sosa:resultTime ?t ;
           sosa:hasResult/qudt:numericValue ?v . FILTER(?t = "2019-01-06T05:00:00Z"^^xsd:dateTime) }""")
    b = r.results["results"]["bindings"][0]
    assert b["v"] == {"type": "literal", "value": "24.7", "datatype": "http://www.w3.org/2001/XMLSchema#decimal"}
    assert b["t"]["value"].endswith("+00:00") or b["t"]["value"].endswith("Z")
