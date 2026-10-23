"""Comparação de resultados (não de strings de consulta).

Normaliza SPARQL JSON e saída do oráculo para o mesmo espaço de valores:
  IRI -> último segmento (ex.: .../station/EST-A -> "EST-A")
  número (integer/decimal/double/float) -> Decimal
  xsd:dateTime -> datetime com fuso (igualdade respeita offset)
"""
from __future__ import annotations

import itertools
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


def judge(results: dict, expected: list, spec: dict) -> tuple[bool, str, str]:
    """Veredito com a CAUSA da divergência: (igual, nota, qualidade).

    qualidade: "exact" | "incomplete" | "order_only" | "wrong".
    - incomplete: os valores presentes batem, mas faltam colunas de identificação/tempo que a referência pede (ex.: a previsão sem o
      instante de emissão). O valor numérico está certo; falta informação exigida. NÃO é resposta errada.
    - order_only: mesmas linhas e valores, em outra ordem, onde a referência ordena (mode ordered).
    Tudo o mais é "wrong". As duas exceções ficam SEPARADAS nas métricas, nunca somem dentro de "corretas"."""
    same, why = compare_flexible(results, expected, spec)
    if same:
        return True, why, "exact"
    cols = spec["columns"]
    if len(expected) == 1:
        # só uma LINHA: sem associação entidade-valor a perder (com várias, omitir a coluna da entidade esconderia valores
        # trocados entre entidades). E só colunas SEM número: omitir o valor numérico nunca é "incompleto", é errado
        non_numeric = [c for i, c in enumerate(cols) if not any(isinstance(norm_py(r[i]), Decimal) for r in expected)]
        if non_numeric and len(non_numeric) < len(cols):
            ok, w = compare_flexible(results, expected, {**spec, "optional": non_numeric})
            if ok:
                return True, f"incompleta: {w}", "incomplete"
    if spec.get("mode") == "ordered":
        key = [c for c in cols if c != spec.get("order_key")][:1] or cols[:1]
        ok, w = compare_flexible(results, expected, {**spec, "mode": "per_group", "key": key})
        if ok:
            return True, "outra ordem", "order_only"
    return False, why, "wrong"


def compare_flexible(results: dict, expected: list, spec: dict) -> tuple[bool, str]:
    """Compara por VALOR, não por nome de variável: o LLM escolhe os nomes (?observation, ?average...).

    Casa as colunas esperadas com as do resultado em qualquer ordem. A única flexibilidade extra é a omissão de
    colunas que a própria referência declara em `compare.optional` (ex.: o instante, quando a pergunta só pede a
    estação e o valor); omitir qualquer outra coluna é erro, senão o comparador aceitaria respostas sem o valor."""
    if not results.get("results", {}).get("bindings") and not expected:
        return True, "ok (ambos vazios)"          # vazio é vazio, quaisquer que sejam as colunas projetadas
    cols, got = spec["columns"], results["head"]["vars"]
    optional = [c for c in spec.get("optional", []) if c in cols]
    last = "colunas insuficientes"
    for n_drop in range(len(optional) + 1):
        for drop in itertools.combinations(optional, n_drop):
            keep = [i for i, c in enumerate(cols) if c not in drop]
            kept = [cols[i] for i in keep]
            if len(got) < len(kept):
                continue
            spec2 = {**spec, "columns": kept, "key": [c for c in spec.get("key", []) if c in kept],
                     "tolerance": {c: t for c, t in spec.get("tolerance", {}).items() if c in kept}}
            exp2 = [tuple(row[i] for i in keep) for row in expected]
            for perm in itertools.permutations(got, len(kept)):
                ok, why = compare(rows_from_sparql(results, list(perm)), exp2, spec2)
                if ok:
                    return True, "ok" if not drop else f"ok (colunas omitidas: {list(drop)})"
                last = why
    return False, last
