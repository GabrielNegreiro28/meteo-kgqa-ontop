"""Comparação de resultados (não de strings de consulta).

Normaliza SPARQL JSON e saída do oráculo para o mesmo espaço de valores:
  IRI -> último segmento (ex.: .../station/EST-A -> "EST-A")
  número (integer/decimal/double/float) -> Decimal
  xsd:dateTime -> datetime com fuso (igualdade respeita offset)
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

XSD = "http://www.w3.org/2001/XMLSchema#"
NUMERIC = {XSD + t for t in ("integer", "decimal", "double", "float", "int", "long")}


def norm_term(t: dict[str, str] | None) -> Any:
    if t is None:
        return None
    if t["type"] == "uri":
        return t["value"].rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    dt = t.get("datatype")
    if dt in NUMERIC:
        return Decimal(t["value"])
    if dt in (XSD + "dateTime", XSD + "dateTimeStamp"):
        return datetime.fromisoformat(t["value"])
    return t["value"]


def norm_py(v: Any) -> Any:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    return v


def rows_from_sparql(results: dict, columns: list[str]) -> list[tuple]:
    return [tuple(norm_term(b.get(c)) for c in columns) for b in results["results"]["bindings"]]


def _close(a: Any, b: Any, tol: float | None) -> bool:
    a, b = norm_py(a), norm_py(b)
    if tol is not None and isinstance(a, Decimal) and isinstance(b, Decimal):
        return abs(a - b) <= Decimal(str(tol))
    return a == b


def compare(actual: list[tuple], expected: list[tuple], spec: dict) -> tuple[bool, str]:
    cols: list[str] = spec["columns"]
    tol: dict[str, float] = spec.get("tolerance", {})
    expected = [tuple(norm_py(v) for v in row) for row in expected]
    actual = [tuple(norm_py(v) for v in row) for row in actual]
    mode = spec["mode"]

    if mode == "set":
        ca, ce = Counter(actual), Counter(expected)
        if ca == ce:
            return True, "ok"
        return False, f"faltando={list((ce - ca).elements())[:5]} sobrando={list((ca - ce).elements())[:5]}"

    if mode == "per_group":
        key_idx = [cols.index(k) for k in spec.get("key", [])]
        def index(rows):
            d = {}
            for r in rows:
                k = tuple(r[i] for i in key_idx)
                if k in d:
                    return None, f"chave duplicada {k}"
                d[k] = r
            return d, ""
        da, err = index(actual)
        if da is None:
            return False, err
        de, _ = index(expected)
        if set(da) != set(de):
            return False, f"grupos diferem: esperado={sorted(de)} obtido={sorted(da)}"
        for k, er in de.items():
            ar = da[k]
            for i, c in enumerate(cols):
                if i in key_idx:
                    continue
                if not _close(ar[i], er[i], tol.get(c)):
                    return False, f"grupo {k}, coluna {c}: esperado={er[i]} obtido={ar[i]}"
        return True, "ok"

    if mode == "ordered":
        if len(actual) != len(expected):
            return False, f"tamanho: esperado={len(expected)} obtido={len(actual)}"
        ki = cols.index(spec["order_key"])
        t = tol.get(spec["order_key"])
        for i, (a, e) in enumerate(zip(actual, expected)):
            if not _close(a[ki], e[ki], t):
                return False, f"posição {i}: chave esperada={e[ki]} obtida={a[ki]}"
        # Dentro de empates na chave, a ordem é livre: compara como multiconjunto por grupo.
        ga, ge = defaultdict(list), defaultdict(list)
        for a, e in zip(actual, expected):
            ga[e[ki]].append(a)
            ge[e[ki]].append(e)
        for k in ge:
            ea = sorted(ge[k], key=repr)
            aa = sorted(ga[k], key=repr)
            if len(ea) != len(aa) or not all(
                    all(_close(x, y, tol.get(c)) for x, y, c in zip(ar, er, cols)) for ar, er in zip(aa, ea)):
                return False, f"empate em {k}: esperado={ea} obtido={aa}"
        return True, "ok"

    raise ValueError(f"modo desconhecido: {mode}")
