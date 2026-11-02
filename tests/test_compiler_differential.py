"""Teste DIFERENCIAL do compilador: especificações sorteadas (grandeza × agregação × período × filtro × agrupamento) são montadas por
código, executadas no grafo real (Ontop) e comparadas com pandas sobre a camada limpa. Sem LLM, sem custo.

Prova o compilador em volume em vez de depender de poucas perguntas. Semente fixa: o mesmo conjunto em toda execução.
Pulado sem o Ontop e o DuckDB (WSL do Gabriel).
"""
import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from metqa.execution.store import PREFIXES, OntopBackend
from metqa.planning.sparql import compile_structured
from metqa.verification.rules import PipelineInterpretation, validate_query
from metqa.knowledge.index import OntologyIndex
from tests.test_real_pipeline import needs_duck, needs_ontop

PROPS = {"met:AirTemperature": ("obs_air_temp", "DEG_C", (-5, 38)), "met:Precipitation": ("obs_precip", "MilliM", (0, 10)),
         "met:PressureQNH": ("obs_qnh", "HectoPA", (1000, 1022)), "met:RelativeHumidity": ("obs_rel_humidity", "PERCENT", (30, 95)),
         "met:PrevailingVisibility": ("obs_visibility", "M", (1000, 9000))}
STATIONS = ["SBGL", "SBPA", "SBCT", "SBFZ", "SBBR"]
N_SPECS = 56
CHECKED = []                                     # especificações cuja comparação teve linhas de verdade (não só vazio = vazio)


def _specs():
    rnd = random.Random(20261023)
    out = []
    for k in range(N_SPECS):
        prop = rnd.choice(sorted(PROPS))
        aggs = ["avg", "min", "max", "count"] + (["sum"] if prop == "met:Precipitation" else [])
        year = rnd.choice(range(2016, 2026))
        a = date(year, rnd.randint(1, 12), rnd.randint(1, 28))
        b = a + timedelta(days=rnd.choice([0, 6, 14, 30, 90, 200]))
        b = min(b, date(2025, 12, 31))
        shape = rnd.choice(["plain", "plain", "filter", "station", "year", "month", "daily", "daily"])
        spec = dict(properties=[prop], aggregation=rnd.choice(aggs), period={"start": a.isoformat(), "end": b.isoformat(), "tz": "-03:00", "inclusive_end": True},
                    entities=[], filters=[], group_by=[], record_kind="observation")
        sts = rnd.sample(STATIONS, 3 if shape == "station" else 1)
        spec["entities"] = [{"text": s, "iri": f"st:{s}"} for s in sts]
        if shape == "filter":
            lo, hi = PROPS[prop][2]
            spec["filters"] = [{"op": rnd.choice([">", ">=", "<", "<="]), "value": rnd.randint(lo, hi), "unit": f"unit:{PROPS[prop][1]}"}]
        elif shape == "daily":
            lo, hi = PROPS[prop][2]
            spec["aggregation"] = "count"
            spec["daily"] = {"agg": rnd.choice(["max", "min", "avg"] + (["sum"] if prop == "met:Precipitation" else [])),
                             "op": rnd.choice([">", ">=", "<", "<="]), "value": rnd.randint(lo, hi), "unit": f"unit:{PROPS[prop][1]}"}
        elif shape != "plain":
            spec["group_by"] = [shape]
        if shape == "year":
            spec["period"] = {"start": f"{year}-01-01", "end": f"{min(year + 2, 2025)}-12-31", "tz": "-03:00", "inclusive_end": True}
        out.append((k, spec))
    return out


@pytest.fixture(scope="module")
def world():
    backend = OntopBackend()
    return backend, OntologyIndex.from_ontop(backend)


@needs_ontop
@needs_duck
@pytest.mark.parametrize("k,spec", _specs(), ids=[f"S{k:02d}" for k, _ in _specs()])
def test_compiled_query_equals_pandas_on_the_real_graph(world, k, spec):
    import pandas as pd

    from eval import oracle_real
    backend, idx = world
    interp = PipelineInterpretation(**spec)
    sparql = compile_structured(interp, idx, force=True)
    assert sparql, "o compilador deve montar toda forma sorteada"
    _, findings = validate_query(sparql, interp, idx, True)
    assert not findings, [f.diag.code for f in findings]
    ex = backend.select(PREFIXES + sparql, timeout_s=120, max_rows=5000)
    assert ex.ok, ex.error
    table, _, _ = PROPS[spec["properties"][0]]
    a, b = date.fromisoformat(spec["period"]["start"]), date.fromisoformat(spec["period"]["end"])
    frames = [oracle_real.between(oracle_real.load(table, e["iri"].split(":")[1]), a, b) for e in spec["entities"]]
    d = pd.concat(frames)
    for f in spec["filters"]:
        v = f["value"]
        d = d[{">": d.value > v, ">=": d.value >= v, "<": d.value < v, "<=": d.value <= v}[f["op"]]]
    agg = spec["aggregation"]
    if "daily" in spec:                              # value = dias que cumprem a condição; n = dias com dados
        dd = spec["daily"]
        per_day = d.groupby("local_date").value.agg({"max": "max", "min": "min", "avg": "mean", "sum": "sum"}[dd["agg"]])
        hit = {">": per_day > dd["value"], ">=": per_day >= dd["value"], "<": per_day < dd["value"], "<=": per_day <= dd["value"]}[dd["op"]]
        CHECKED.append(bool(len(per_day)))
        row = ex.results["results"]["bindings"]
        assert len(row) == 1
        got_n = int(row[0]["n"]["value"])
        assert got_n == len(per_day), (got_n, len(per_day))
        if len(per_day):
            assert float(row[0]["value"]["value"]) == int(hit.sum()), (row[0], int(hit.sum()))
        return
    fn = {"avg": "mean", "min": "min", "max": "max", "sum": "sum", "count": "size"}[agg]
    gb = spec["group_by"]
    if gb == ["station"]:
        g = d.groupby("sigla").value.agg(fn)
        want = {(s,): (float(x), int(d[d.sigla == s].shape[0])) for s, x in g.items()}
    elif gb == ["year"]:
        g = d.groupby(d.local_date.map(lambda x: x.year)).value.agg(fn)
        want = {(int(y),): (float(x), int(d[d.local_date.map(lambda x: x.year) == y].shape[0])) for y, x in g.items()}
    elif gb == ["month"]:
        keys = d.local_date.map(lambda x: (x.year, x.month))
        g = d.groupby(keys).value.agg(fn)
        want = {k_: (float(x), int((keys == k_).sum())) for k_, x in g.items()}
    else:
        want = {(): ((float(getattr(d.value, fn)()) if len(d) else None) if fn != "size" else float(len(d)), int(len(d)))}
    got = {}
    for bnd in ex.results["results"]["bindings"]:
        key = tuple((bnd[c]["value"].rsplit("/", 1)[-1] if c == "station" else int(bnd[c]["value"])) for c in ("station", "year", "month") if c in bnd)
        if gb == ["month"]:
            key = (key[0], key[1])
        val = float(Decimal(bnd["value"]["value"])) if "value" in bnd else float(bnd["n"]["value"])
        got[key] = (val, int(bnd["n"]["value"]))
    CHECKED.append(bool(len(d)))
    if not len(d):                               # sem leituras: agregação sobre vazio é ausente (nunca zero); só a contagem vale 0
        assert all(n == 0 for _, n in got.values()) or not got
        return
    assert set(got) == set(want), (sorted(got)[:3], sorted(want)[:3])
    for key, (val, n) in want.items():
        assert got[key][1] == n, (key, got[key], (val, n))
        assert got[key][0] == pytest.approx(val, rel=1e-6, abs=1e-6), (key, got[key], (val, n))


@needs_ontop
@needs_duck
def test_the_random_specs_are_not_mostly_empty():
    if len(CHECKED) < N_SPECS:
        pytest.skip("rode o arquivo inteiro")
    assert sum(CHECKED) >= 0.75 * N_SPECS, f"só {sum(CHECKED)} de {N_SPECS} especificações tinham dados"
