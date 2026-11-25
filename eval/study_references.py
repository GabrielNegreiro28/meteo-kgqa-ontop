"""Converte as referências do gerador independente (docs/PROMPT_ESTUDO_PERGUNTAS.md) no spec de `eval.clean_reference`.

Só acrescenta o que é contrato público: a unidade canônica da grandeza (do catálogo) na coluna `value`, e nenhuma unidade numa contagem.
O SQL do gerador não é alterado.
python -m eval.study_references <referencias.json> <spec.json>
"""
from __future__ import annotations

import json
import sys

from ontology.catalog import quantity_by_sensor

UNIT_NS = "http://qudt.org/vocab/unit/"


def spec(refs: list[dict]) -> dict:
    cases = []
    for r in refs:
        sensor = "cloud_base" if r["measure"] == "cloud_layer" else r["measure"]      # a única média sobre camadas é a da base
        unit = None if r.get("is_count") else quantity_by_sensor(sensor).unit
        units = {"value": UNIT_NS + unit} if unit else {}
        cases.append({"id": r["id"], "expected_status": r.get("expected_status", "answered"),
                      "parts": [{"label": p.get("label", ""), "sql": p["sql"], "units": units} for p in r["parts"]]})
    return {"cases": cases}


def main() -> None:
    refs = json.load(open(sys.argv[1], encoding="utf-8"))
    with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as f:
        json.dump(spec(refs), f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
