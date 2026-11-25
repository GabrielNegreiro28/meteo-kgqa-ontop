"""Referências independentes sobre snapshot limpo, sem importar o compilador.

python -m eval.clean_reference --database met.duckdb --snapshot snapshot.json \
    --spec references.json --out references_frozen.json

O spec revisado contém cases: [{id, expected_status, parts: [{label, sql, units}]}].
SQL SELECT escrito pelo revisor; aliases das colunas devem corresponder ao contrato.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from eval.matching import match_rows
from ingest.manifest import load, verify_database


def encode(value):
    if isinstance(value, int):
        return value
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError("non-finite reference")
        return {"number": str(number)}
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def decode(value):
    return Decimal(value["number"]) if isinstance(value, dict) and set(value) == {"number"} else value


def freeze(database, snapshot, spec):
    import duckdb
    verify_database(snapshot, database)
    records, ids = {}, set()
    with duckdb.connect(str(database), read_only=True, config={"enable_external_access": False}) as db:
        for case in spec["cases"]:
            if case["id"] in ids or case["expected_status"] not in ("answered", "no_results"):
                raise ValueError("duplicate id or invalid reference status")
            ids.add(case["id"])
            parts = []
            for part in case["parts"]:
                statements = db.extract_statements(part["sql"])
                if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
                    raise ValueError("reference requires one SELECT")
                cursor = db.execute(part["sql"])
                columns = [d[0] for d in cursor.description]
                if len(set(columns)) != len(columns):
                    raise ValueError("duplicate column aliases")
                parts.append({"label": part.get("label", ""), "columns": columns, "units": part.get("units", {}),
                              "rows": [[encode(v) for v in row] for row in cursor.fetchall()]})
            if not parts or len({p['label'] for p in parts}) != len(parts):
                raise ValueError("reference needs uniquely labeled parts")
            records[case["id"]] = {"expected_status": case["expected_status"], "parts": parts}
    verify_database(snapshot, database)
    return {"version": 1, "snapshot_id": snapshot["snapshot_id"],
            "spec_sha256": hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest(), "cases": records}


def compare(response, reference):
    """Projeção explícita por nome; valores brutos, IRIs inteiros e unidades canônicas."""
    from metqa.execution.source import typed_rows
    if reference is None:
        raise ValueError("missing clean reference")
    if response.status.value != reference["expected_status"] or response.truncated:
        return False
    shapes = response.result_shape or []
    raw = response.results or {}
    if not shapes and response.status.value == 'no_results':
        return all(not p['rows'] for p in reference['parts'])
    parts = raw.get("parts", [{"label": shapes[0].get("label", "") if shapes else "", "results": raw}])
    if len(parts) != len(reference["parts"]) or len(shapes) != len(parts):
        return False
    expected = {p["label"]: p for p in reference["parts"]}
    if len(expected) != len(parts) or len({p['label'] for p in parts}) != len(parts):
        return False
    queries = [i.get("query", {}) for i in (response.interpretations or [])]
    for k, (part, shape) in enumerate(zip(parts, shapes)):
        ref = expected.get(part["label"])
        if ref is None or shape.get("units", {}) != ref["units"]:
            return False
        variables = part['results'].get('head', {}).get('vars', [])
        # a coluna "value" da referência é o valor que o ResultShape declara (numa contagem de leituras ele se chama "n")
        columns = [shape.get("value") or "value" if c == "value" else c for c in ref["columns"]]
        if any(c not in variables for c in columns):
            return False
        actual = [[row.get(c) for c in columns] for row in typed_rows(part["results"])]
        order = (queries[k] if k < len(queries) else {}).get("order") or {}
        if order.get("limit") and len(actual) == order["limit"] + 1:
            # o ranking busca uma linha a mais só para detectar empate no limite; ela não faz parte da resposta pedida
            actual = actual[:order["limit"]]
        wanted = [[decode(v) for v in row] for row in ref["rows"]]
        if not match_rows(actual, wanted):
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'snapshot', 'spec', 'out'):
        ap.add_argument('--' + name, required=True, type=Path)
    args = ap.parse_args()
    references = freeze(args.database, load(args.snapshot), json.loads(args.spec.read_text(encoding='utf-8')))
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(references, stream, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
