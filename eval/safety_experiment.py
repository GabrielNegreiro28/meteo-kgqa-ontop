"""Experimento de segurança por injeção de falhas (custo zero, determinístico, sem LLM).

Parte de consultas de referência CORRETAS (eval/questions.yaml) e aplica falhas típicas de LLM
(IRI inventado, filtro trocado, período deslocado, escrita...). Para cada mutante mede:
  - qual camada de validação o barra (L1 política/sintaxe, L2 vocabulário, L3 conformidade com a interpretação);
  - o que aconteceria sem ela: executa e devolve resposta errada em silêncio? (comparado ao oráculo independente)
Também injeta falhas no TEXTO da resposta (etapa 3) e mede a checagem de números (L5).

Uso: python -m eval.safety_experiment      -> docs/RESULTADOS_INJECAO_FALHAS.md e eval/reports/safety_injection.json
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from eval import oracle
from eval.compare import compare, rows_from_sparql
from eval.run_reference import load_questions
from kgqa.contract import Status
from kgqa.store import PREFIXES, LocalRdflibBackend
from kgqa.verify import result_status
from pipeline.grounding import NUM_RE, check_answer, render_fallback
from pipeline.validators import PipelineInterpretation, layers_hit, validate_query
from pipeline.vocab import OntologyIndex

ROOT = Path(__file__).resolve().parent.parent
ORDER = ["L1", "L2", "L3"]
CONFIGS = {"sem validação": set(), "L1 sintaxe+política": {"L1"}, "L1+L2 vocabulário": {"L1", "L2"},
           "L1+L2+L3 conformidade": {"L1", "L2", "L3"}}


def _p(start, end):
    return {"start": start, "end": end, "tz": "-03:00", "inclusive_end": True}


def _i(props, agg=None, ents=(), filters=(), period=None):
    return PipelineInterpretation(
        properties=[f"met:{p}" for p in props], aggregation=agg,
        entities=[{"text": e, "iri": f"st:{e}"} for e in ents], filters=list(filters), period=period)


CASES = {  # id -> (interpretação validada, variável do valor no SPARQL)
    "D03": (_i(["AirTemperature"], filters=[{"op": ">", "value": 30}]), "value"),
    "D04": (_i(["AirTemperature"], "avg", period=_p("2026-03-03", "2026-03-05")), "v"),
    "D05": (_i(["Precipitation"], "sum", ["EST-B"], period=_p("2026-03-04", "2026-03-04")), "v"),
    "T03": (_i(["AirTemperature"], "max", period=_p("2026-03-02", "2026-03-08")), "v"),
    "T04": (_i(["RelativeHumidity"], "min", ["EST-A"]), "v"),
    "T06": (_i(["Precipitation"], "sum", period=_p("2026-03-02", "2026-03-08")), "v"),
    "T07": (_i(["AirTemperature"], "avg", ["EST-C"], filters=[{"op": ">", "value": 28}]), "v"),
    "T08": (_i(["RelativeHumidity"], "avg", ["EST-C"]), "v"),
    "T11": (_i(["AirTemperature"], "avg", ["EST-B"], period=_p("2026-03-02", "2026-03-08")), "v"),
}

# ------------------------------------------------------------------------------------------
# Operadores de falha (consulta). Devolvem None quando não se aplicam ao caso.
# ------------------------------------------------------------------------------------------

def _filter_span(q: str):
    i = q.find("FILTER(")
    if i < 0:
        return None
    depth = 0
    for j in range(i + 6, len(q)):
        depth += q[j] == "("
        if q[j] == ")":
            depth -= 1
            if depth == 0:
                return i, j + 1
    return None


def f_hallucinated_property(q, c):
    for a, b in [("AirTemperature", "Temperature"), ("Precipitation", "Rainfall"), ("RelativeHumidity", "Humidity")]:
        if f"met:{a}" in q:
            return q.replace(f"met:{a}", f"met:{b}")


def f_hallucinated_class(q, c):
    for a, b in [("InstantaneousObservation", "Measurement"), ("AccumulatedObservation", "RainObservation")]:
        if f"met:{a}" in q:
            return q.replace(f"met:{a}", f"met:{b}")


def f_property_swapped(q, c):
    for a, b in [("AirTemperature", "RelativeHumidity"), ("Precipitation", "AirTemperature"), ("RelativeHumidity", "AirTemperature")]:
        if f"met:{a}" in q:
            return q.replace(f"met:{a}", f"met:{b}")


def f_wrong_operator(q, c):
    span = _filter_span(q)
    if not span:
        return None
    seg = q[span[0]:span[1]]
    m = re.search(r"(?<![<>=!])([<>])(=?)(?!=)", seg)
    if not m:
        return None
    new = m.group(1) + ("" if m.group(2) else "=")
    return q[:span[0]] + seg[:m.start()] + new + seg[m.end():] + q[span[1]:]


def f_shifted_period(q, c):
    m = re.search(r'"(\d{4})-(\d{2})-(\d{2})T', q)
    if not m:
        return None
    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3))) + timedelta(days=1)
    return q[:m.start()] + f'"{d.isoformat()}T' + q[m.end():]


def f_dropped_filter(q, c):
    span = _filter_span(q)
    return q[:span[0]] + q[span[1]:] if span else None


def f_dropped_count(q, c):
    return q.replace("(COUNT(?v) AS ?n)", "") if "(COUNT(?v) AS ?n)" in q else None


def f_wrong_aggregate(q, c):
    pairs = [("AVG(", "MAX("), ("SUM(", "AVG("), ("MAX(", "AVG("), ("MIN(", "AVG(")]
    hits = [(q.find(a), a, b) for a, b in pairs if a in q]
    if not hits:
        return None
    _, a, b = min(hits)
    return q.replace(a, b, 1)


def f_extra_filter(q, c):
    var = CASES[c][1]
    return q.replace("WHERE {", f"WHERE {{ FILTER(?{var} > 5) ", 1) if "WHERE {" in q else None


def f_unknown_station(q, c):
    return re.sub(r"st:EST-[ABC]\b", "st:EST-Z", q) if re.search(r"st:EST-[ABC]\b", q) else None


def f_wrong_station(q, c):
    m = re.search(r"st:EST-([ABC])\b", q)
    if not m:
        return None
    return q.replace(m.group(0), "st:EST-A" if m.group(1) != "A" else "st:EST-B")


def f_hallucinated_label(q, c):
    return q.replace("Estação Serra Azul", "Estação Serra Verde") if "Estação Serra Azul" in q else None


def f_wrong_station_label(q, c):
    return q.replace("Estação Serra Azul", "Estação Vale Verde") if "Estação Serra Azul" in q else None


def f_forecast_leak(q, c):
    if c != "T03":
        return None
    return """SELECT ?station ?value ?t WHERE {
      ?x sosa:hasResult/qudt:numericValue ?value ; (sosa:phenomenonTime|met:validTime)/time:inXSDDateTime ?t .
      ?x (sosa:madeBySensor/^sosa:hosts)|met:forStation ?station .
      ?x (sosa:observedProperty|met:forecastedProperty) met:AirTemperature .
    } ORDER BY DESC(?value) LIMIT 1"""


def f_superclass_type(q, c):
    return q.replace("a met:InstantaneousObservation", "a sosa:Observation") if "a met:InstantaneousObservation" in q else None


def f_interval_as_instant(q, c):
    """Precipitação (intervalo) consultada como se fosse um instante: vazia por construção."""
    old = "?iv time:hasBeginning/time:inXSDDateTime ?b ; time:hasEnd/time:inXSDDateTime ?e ."
    if old not in q:
        return None
    return q.replace("sosa:phenomenonTime ?iv ;", "sosa:phenomenonTime/time:inXSDDateTime ?b ;").replace(old, "BIND(?b AS ?e)")


def f_strict_interval_end(q, c):
    """Fim do intervalo estritamente menor que o fim do período: descarta o último intervalo (D-06)."""
    return q.replace("?e <= ", "?e < ") if "?e <= " in q else None


def f_unit_as_text(q, c):
    """Unidade (recurso) comparada com um texto: vazia por construção."""
    if "qudt:unit unit:DEG_C" not in q:
        return None
    return q.replace("qudt:unit unit:DEG_C", "qudt:unit ?u").replace("FILTER(?value > 30)", 'FILTER(?value > 30) FILTER(?u = "unit:DEG_C")')


def f_unpopulated_relation(q, c):
    """Usa met:inReport (declarada na ontologia, mas sem asserções neste grafo): vazia por construção."""
    import re
    m = re.search(r"sosa:madeBySensor (\?\w+) ;", q)
    return q[:m.end()] + " met:inReport ?rep ;" + q[m.end():] if m else None


def f_xsd_date(q, c):
    """xsd:date() não existe no SPARQL 1.1: o rdflib deixa o dia sem valor e os grupos colapsam."""
    return q.replace("SUBSTR(STR(?t), 1, 10)", "xsd:date(?t)") if "SUBSTR(STR(?t), 1, 10)" in q else None


def f_write_op(q, c):
    return "DELETE WHERE { ?s ?p ?o }"


def f_service(q, c):
    return q.replace("WHERE {", "WHERE { SERVICE <http://evil.example/sparql> { ?x ?y ?z } ", 1)


def f_syntax_cut(q, c):
    return q[:-15]


FAULTS: dict[str, Callable] = {
    "IRI de propriedade inventado": f_hallucinated_property,
    "IRI de classe inventado": f_hallucinated_class,
    "propriedade válida, mas errada": f_property_swapped,
    "estação inexistente": f_unknown_station,
    "estação válida, mas errada": f_wrong_station,
    "rótulo de estação inventado": f_hallucinated_label,
    "rótulo de estação válido, mas de outra estação": f_wrong_station_label,
    "operador de fronteira trocado (> por >=)": f_wrong_operator,
    "período deslocado em 1 dia": f_shifted_period,
    "filtro omitido": f_dropped_filter,
    "filtro extra não pedido": f_extra_filter,
    "agregação errada (AVG/MAX/SUM)": f_wrong_aggregate,
    "contagem ?n omitida": f_dropped_count,
    "previsão vaza para observação": f_forecast_leak,
    "tipa por superclasse sem inferência (sosa:Observation)": f_superclass_type,
    "intervalo (precipitação) consultado como instante": f_interval_as_instant,
    "fim do intervalo estrito (< em vez de <=)": f_strict_interval_end,
    "relação sem dados no grafo (met:inReport)": f_unpopulated_relation,
    "função fora do SPARQL 1.1 (xsd:date)": f_xsd_date,
    "unidade comparada com texto": f_unit_as_text,
    "escrita (DELETE)": f_write_op,
    "SERVICE (rede externa)": f_service,
    "saída cortada (consulta truncada)": f_syntax_cut,
}


@dataclass
class Mutant:
    case: str
    fault: str
    layers: set[str]
    codes: list[str]
    truth: str          # dangerous | blocked_syntax | silent_wrong | surfaced_empty | surfaced_error | harmless


def classify(case: str, fault: str, mutated: str, backend, index, questions) -> Mutant:
    interp, _ = CASES[case]
    facts, findings = validate_query(mutated, interp, index)
    layers, codes = layers_hit(findings), [f.diag.code for f in findings]
    if "L1" in layers:
        truth = "dangerous" if codes[0] == "POLICY_VIOLATION" else "blocked_syntax"
        return Mutant(case, fault, layers, codes, truth)
    q = questions[case]
    res = backend.select(PREFIXES + mutated, timeout_s=30)
    if not res.ok:
        return Mutant(case, fault, layers, codes, "surfaced_error")
    status, _ = result_status(res.results)
    same, _ = compare(rows_from_sparql(res.results, q["compare"]["columns"]), oracle.expected(case), q["compare"])
    if same:
        truth = "harmless"
    elif status == Status.NO_RESULTS:
        truth = "surfaced_empty"
    else:
        truth = "silent_wrong"
    return Mutant(case, fault, layers, codes, truth)


# ------------------------------------------------------------------------------------------
# Falhas no texto da resposta (etapa 3)
# ------------------------------------------------------------------------------------------

def t_digit_changed(text, ctx):
    m = next((m for m in NUM_RE.finditer(text) if len(m.group()) > 1), None)
    if not m:
        return None
    tok = m.group()
    last = tok[-1]
    return text[:m.start()] + tok[:-1] + str((int(last) + 3) % 10) + text[m.end():]


def t_invented_number(text, ctx):
    return text + " Em média histórica, 27,3 °C."


def t_value_swapped(text, ctx):
    toks = [m for m in NUM_RE.finditer(text) if "." in m.group()]
    if len(toks) < 2 or toks[0].group() == toks[1].group():
        return None
    a, b = toks[0], toks[1]
    return text[:a.start()] + b.group() + text[a.end():b.start()] + a.group() + text[b.end():]


def t_unit_dropped(text, ctx):
    new = text.replace(" °C", "").replace(" mm", "").replace(" %", "")
    return new if new != text else None


def t_truncation_hidden(text, ctx):
    return text.replace(" resultado parcial: limite de linhas atingido.", "") if ctx["truncated"] else None


def t_empty_as_zero(text, ctx):
    return "O valor registrado foi 0." if ctx["status"] == Status.NO_RESULTS else None


def t_row_dropped(text, ctx):
    lines = text.split("\n")
    rows = [i for i, l in enumerate(lines) if l.startswith("- ")]
    if len(rows) < 2 or ctx["status"] != Status.ANSWERED:
        return None
    del lines[rows[-1]]
    return "\n".join(lines)


def t_no_records_claim(text, ctx):
    return "Não há registros para os critérios da pergunta." if ctx["status"] == Status.ANSWERED else None


TEXT_FAULTS = {
    "dígito do valor alterado": t_digit_changed,
    "número inventado (não está nos resultados)": t_invented_number,
    "valores trocados entre entidades": t_value_swapped,
    "unidade omitida": t_unit_dropped,
    "truncamento não informado": t_truncation_hidden,
    "'sem dados' apresentado como zero": t_empty_as_zero,
    "linha dos resultados omitida da resposta": t_row_dropped,
    "'não há registros' onde há dados": t_no_records_claim,
}


INDEX_FOR_TEXT = OntologyIndex.load()


# ------------------------------------------------------------------------------------------
# Falhas na INTERPRETAÇÃO (etapa 1): a que L3 não alcança, pois a consulta pode ser coerente com ela
# ------------------------------------------------------------------------------------------

def _copy(i, **kw):
    d = {**i.__dict__, **kw}
    return PipelineInterpretation(**d)


def i_drop_entity(i, q):
    return _copy(i, entities=[]) if i.entities else None


def i_invent_entity(i, q):
    other = "EST-C" if not any("EST-C" in e["iri"] for e in i.entities) else "EST-A"
    return _copy(i, entities=[*i.entities, {"text": "Estação inventada", "iri": f"st:{other}"}])


def i_swap_aggregation(i, q):
    swap = {"avg": "max", "max": "min", "min": "max", "sum": "avg", "count": "avg"}
    return _copy(i, aggregation=swap[i.aggregation]) if i.aggregation in swap else None


def i_drop_aggregation(i, q):
    return _copy(i, aggregation=None) if i.aggregation else None


def i_shift_period(i, q):
    if not i.period:
        return None
    end = (date.fromisoformat(i.period["end"]) + timedelta(days=1)).isoformat()
    return _copy(i, period={**i.period, "end": end})


def i_drop_period(i, q):
    return _copy(i, period=None) if i.period else None


def i_invent_period(i, q):
    return _copy(i, period=_p("2026-03-02", "2026-03-04")) if not i.period else None


def i_change_filter(i, q):
    return _copy(i, filters=[{**f, "value": float(f["value"]) + 5} for f in i.filters]) if i.filters else None


def i_swap_property(i, q):
    other = {"met:AirTemperature": "met:DewPointTemperature", "met:RelativeHumidity": "met:AirTemperature",
             "met:Precipitation": "met:PrecipitationDuration"}
    return _copy(i, properties=[other[p] for p in i.properties]) if i.properties and i.properties[0] in other else None


INTERP_FAULTS = {
    "estação citada na pergunta omitida": i_drop_entity,
    "estação não citada acrescentada": i_invent_entity,
    "agregação trocada": i_swap_aggregation,
    "agregação omitida": i_drop_aggregation,
    "período deslocado em 1 dia": i_shift_period,
    "período omitido": i_drop_period,
    "período inventado": i_invent_period,
    "valor do filtro alterado": i_change_filter,
    "grandeza trocada": i_swap_property,
}


def run_interpretation_experiment(index, questions):
    """Cada interpretação de referência é corrompida de modo COERENTE (a consulta seguiria a interpretação errada, então
    L3 não vê nada). Mede quantas a fundamentação na pergunta (L4) barra. 'Passou' inclui equivalentes legítimos."""
    from pipeline.validators import validate_interpretation
    rows = defaultdict(Counter)
    detail = []
    for case, (interp, _) in CASES.items():
        question = questions[case]["question"]
        for name, fn in INTERP_FAULTS.items():
            bad = fn(interp, question)
            if bad is None:
                continue
            found = [f.diag.code for f in validate_interpretation(bad, index, question) if f.layer == "L4"]
            rows[name]["n"] += 1
            rows[name]["caught"] += bool(found)
            if not found:
                detail.append((case, name))
    return rows, detail


def run_text_experiment(backend, questions):
    rows = defaultdict(lambda: Counter())
    for case in CASES:
        res = backend.select(PREFIXES + questions[case]["sparql"], timeout_s=30)
        status, _ = result_status(res.results)
        units = {k: v for k, v in (questions[case].get("units") or {}).items()}
        units = {k: v.replace("unit:", "http://qudt.org/vocab/unit/") for k, v in units.items()}
        for truncated in (False, True):
            if truncated and status != Status.ANSWERED:
                continue
            shown = None if status == Status.NO_RESULTS else res.results
            base = render_fallback(status, shown, units, truncated)
            ctx = {"truncated": truncated, "status": status}
            for name, fn in TEXT_FAULTS.items():
                bad = fn(base, ctx)
                if bad is None or bad == base:
                    continue
                found = [f for f in check_answer(bad, questions[case]["question"], shown, status, truncated, units, INDEX_FOR_TEXT.entities)]
                rows[name]["n"] += 1
                rows[name]["detected"] += bool(found)
    return rows


# ------------------------------------------------------------------------------------------

def run_control(index, questions) -> list[tuple[str, list[str]]]:
    """Controle: a consulta de referência correta, com sua interpretação, NÃO pode gerar achados."""
    out = []
    for case, (interp, _) in CASES.items():
        _, findings = validate_query(questions[case]["sparql"], interp, index)
        out.append((case, [f.diag.code for f in findings]))
    return out


def main() -> int:
    index = OntologyIndex.load()
    backend = LocalRdflibBackend()
    questions = {q["id"]: q for q in load_questions()}
    mutants: list[Mutant] = []
    for case in CASES:
        base = questions[case]["sparql"]
        for fault, fn in FAULTS.items():
            mutated = fn(base, case)
            if mutated is None or mutated.strip() == base.strip():
                continue
            mutants.append(classify(case, fault, mutated, backend, index, questions))
            print(f"{case:4} {fault:45} {','.join(sorted(mutants[-1].layers)) or '-':10} {mutants[-1].truth}", file=sys.stderr)
    text_rows = run_text_experiment(backend, questions)
    interp_rows, interp_missed = run_interpretation_experiment(index, questions)
    control = run_control(index, questions)
    out = ROOT / "docs" / "RESULTADOS_INJECAO_FALHAS.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(render_markdown(mutants, text_rows, control, interp_rows, interp_missed), encoding="utf-8")
    rep = ROOT / "eval" / "reports"
    rep.mkdir(exist_ok=True)
    (rep / "safety_injection.json").write_text(json.dumps(
        [{**m.__dict__, "layers": sorted(m.layers)} for m in mutants], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(mutants)} mutantes -> {out}")
    return 0


def first_layer(m: Mutant) -> str:
    return next((l for l in ORDER if l in m.layers), "—")


def render_markdown(mutants: list[Mutant], text_rows, control, interp_rows=None, interp_missed=()) -> str:
    L = ["# Resultados da injeção de falhas", "",
         "Gerado por `python -m eval.safety_experiment` (determinístico, sem LLM, sobre o grafo sintético).",
         f"Base: {len(CASES)} consultas de referência corretas × {len(FAULTS)} operadores de falha; "
         f"**{len(mutants)} mutantes** aplicáveis. Verdade de cada mutante: executado e comparado ao oráculo independente.", "",
         "Legenda do desfecho sem validação: **perigosa** (escrita/rede chegaria ao armazenamento), **sintaxe** (erro explícito), "
         "**errada em silêncio** (executa e devolve valor diferente do oráculo), **vazia** (executa e devolve 'sem registros', "
         "exposta honestamente), **equivalente** (mesmo resultado do oráculo).", "",
         "## 0. Controle: consultas corretas barradas indevidamente", "",
         f"{sum(1 for _, c in control if not c)}/{len(control)} consultas de referência passam sem nenhum achado"
         + ("." if all(not c for _, c in control) else "; barradas: " + ", ".join(f"{k} ({', '.join(c)})" for k, c in control if c) + "."), "",
         "## 1. Mutantes de consulta (etapa 2): primeira camada que barra", "",
         "| Falha injetada | n | L1 | L2 | L3 | passou | do que passou: errada em silêncio / vazia / equivalente |",
         "|---|---:|---:|---:|---:|---:|---|"]
    by_fault = defaultdict(list)
    for m in mutants:
        by_fault[m.fault].append(m)
    for fault in FAULTS:
        ms = by_fault.get(fault)
        if not ms:
            continue
        c = Counter(first_layer(m) for m in ms)
        passed = [m for m in ms if first_layer(m) == "—"]
        t = Counter(m.truth for m in passed)
        L.append(f"| {fault} | {len(ms)} | {c['L1']} | {c['L2']} | {c['L3']} | {len(passed)} | "
                 f"{t['silent_wrong']} / {t['surfaced_empty']} / {t['harmless'] + t['surfaced_error']} |")
    L += ["", "## 2. Ablação das camadas", "",
          "Mutantes que chegariam ao usuário/armazenamento conforme as camadas ligadas.", "",
          "| Configuração | perigosa chega ao armazenamento | errada em silêncio | vazia (exposta como sem registros) | barrada com resultado coincidente |",
          "|---|---:|---:|---:|---:|"]
    for name, on in CONFIGS.items():
        pas = [m for m in mutants if not (m.layers & on)]
        blocked_equiv = sum(1 for m in mutants if m.truth == "harmless" and (m.layers & on))
        t = Counter(m.truth for m in pas)
        L.append(f"| {name} | {t['dangerous']} | {t['silent_wrong']} | {t['surfaced_empty']} | {blocked_equiv} |")
    sw = [m for m in mutants if m.truth == "silent_wrong" and not (m.layers & {'L1', 'L2', 'L3'})]
    L += ["", "### Falhas silenciosas que NENHUMA camada barrou (risco residual)", ""]
    if sw:
        L += [f"- `{m.case}` — {m.fault}" for m in sw]
    else:
        L += ["- (nenhuma neste conjunto de mutantes)"]
    eq = [m for m in mutants if m.truth == "harmless" and (m.layers & {'L1', 'L2', 'L3'})]
    L += ["", "### Barrados apesar de o resultado coincidir com o oráculo", "",
          "A consulta diverge da interpretação (logo, barrar está certo), mas por coincidência dos dados o resultado seria igual."]
    L += [f"- `{m.case}` — {m.fault}: {', '.join(m.codes)}" for m in eq] or ["- (nenhum)"]
    L += ["", "## 3. Mutantes de texto (etapa 3): checagem de números (L5)", "",
          "| Falha injetada no texto | n | detectadas | taxa |", "|---|---:|---:|---:|"]
    for name in TEXT_FAULTS:
        r = text_rows.get(name)
        if r and r["n"]:
            L.append(f"| {name} | {r['n']} | {r['detected']} | {100 * r['detected'] / r['n']:.0f}% |")
    if interp_rows:
        tot = sum(r["n"] for r in interp_rows.values())
        got = sum(r["caught"] for r in interp_rows.values())
        L += ["", "## 3b. Interpretação corrompida de modo coerente (etapa 1): fundamentação na pergunta (L4)", "",
              "A consulta seguiria a interpretação errada, então L3 (consulta = interpretação) não vê nada; sem L4 a taxa de detecção "
              "é **0%** (limite documentado na versão anterior). Aqui a interpretação é conferida contra o texto da pergunta.", "",
              "| Falha injetada na interpretação | n | barradas por L4 | taxa |", "|---|---:|---:|---:|"]
        for name in INTERP_FAULTS:
            r = interp_rows.get(name)
            if r and r["n"]:
                L.append(f"| {name} | {r['n']} | {r['caught']} | {100 * r['caught'] / r['n']:.0f}% |")
        L += [f"| **total** | **{tot}** | **{got}** | **{100 * got / tot:.0f}%** |", ""]
        if interp_missed:
            L += ["Não barradas (equivalentes legítimos ou lacuna das regras):", ""]
            L += [f"- `{c}` — {n}" for c, n in interp_missed]
    L += ["", "## 4. Detalhe por mutante", "", "| Caso | Falha | Códigos | Verdade sem validação |", "|---|---|---|---|"]
    for m in mutants:
        L.append(f"| {m.case} | {m.fault} | {', '.join(m.codes) or '—'} | {m.truth} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
