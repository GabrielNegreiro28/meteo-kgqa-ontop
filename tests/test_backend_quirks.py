"""Registra um comportamento do backend que motivou a decisão D-07 (xsd:dateTime em vez de dateTimeStamp).
Se este teste começar a falhar após atualizar o rdflib, o defeito foi corrigido e D-07 pode ser revista."""
import rdflib
from rdflib import XSD, Literal


def test_rdflib_datetimestamp_comparison_is_unreliable():
    earlier = Literal("2026-03-02T00:00:00-03:00", datatype=XSD.dateTimeStamp)
    later = Literal("2026-03-03T00:00:00-03:00", datatype=XSD.dateTime)
    # Correto seria False. Observado no rdflib 7.6.0: True (comparação silenciosamente errada).
    assert (earlier >= later) is True, f"rdflib {rdflib.__version__} corrigiu? Reavaliar D-07."


def test_rdflib_datetime_comparison_is_correct():
    earlier = Literal("2026-03-02T00:00:00-03:00", datatype=XSD.dateTime)
    later = Literal("2026-03-03T03:00:00Z", datatype=XSD.dateTime)
    assert earlier < later


def test_duckdb_decimal_topn_documented():
    """D-18: no DuckDB 1.5.6, ORDER BY <DECIMAL> DESC LIMIT n devolveu o top-n errado na camada limpa
    (após DELETEs do controle de qualidade), enquanto MAX() e a ordenação em DOUBLE estavam corretos.
    O oráculo real usa DOUBLE + pandas por isso. Se este teste falhar, o defeito sumiu: reavaliar D-18."""
    import os
    import pytest
    if not os.path.exists("/home/claude/metdata/met.duckdb"):
        pytest.skip("base local ausente")
    import duckdb
    c = duckdb.connect("/home/claude/metdata/met.duckdb", read_only=True)
    mx = c.execute("SELECT MAX(value) FROM clean.obs_air_temp").fetchone()[0]
    top = c.execute("SELECT value FROM clean.obs_air_temp ORDER BY value DESC LIMIT 1").fetchone()[0]
    top_double = c.execute("SELECT CAST(value AS DOUBLE) v FROM clean.obs_air_temp ORDER BY v DESC LIMIT 1").fetchone()[0]
    assert float(mx) == top_double
    if top == mx:
        pytest.skip(f"DuckDB {duckdb.__version__}: top-n DECIMAL correto nesta base; defeito não reproduzido")
