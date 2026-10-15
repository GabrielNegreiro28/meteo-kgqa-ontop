"""Valores conferidos À MÃO a partir de data/observations.csv (seed 20260302).
Protegem contra erro comum ao oráculo e às consultas (ex.: ambos lendo o CSV do mesmo jeito errado)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from eval import oracle

TZ = timezone(timedelta(hours=-3))


def test_d05_rain_vale_verde_0403():
    # 0.0 + 12.5 + 18.4 + 4.9 = 35.8 mm em 4 intervalos de 6 h
    assert oracle.expected("D05") == [(Decimal("35.8"), 4)]


def test_t04_min_rh_serra_azul():
    # menores leituras das 12h: 57.1, 55.4, 64.0, 60.4, 56.1, 63.7, 56.8 -> 55.4
    assert oracle.expected("T04") == [(Decimal("55.4"), 28)]


def test_t11_mean_vale_verde_ignores_missing_day():
    # soma manual das 24 leituras = 583.1 ; 583.1 / 24 = 24.2958...
    (avg, n), = oracle.expected("T11")
    assert n == 24 and abs(avg - Decimal("24.2958")) < Decimal("0.0001")


def test_t03_max_is_observation_not_forecast():
    assert oracle.expected("T03") == [("EST-C", Decimal("34.6"), datetime(2026, 3, 6, 12, tzinfo=TZ))]


def test_boundary_value_exists_exactly_once():
    assert [r[0] for r in oracle.expected("T02") if r[1] == Decimal("30.0")] == ["EST-A-TEMP-20260304T1200"]
