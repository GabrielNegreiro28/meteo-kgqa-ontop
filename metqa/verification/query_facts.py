"""Extrai fatos estruturais de uma consulta SPARQL (IRIs, tipos, comparações, agregações, projeção).

As regras de validação trabalham sobre estes fatos, nunca sobre o texto da consulta: um LLM pode
escrever a mesma consulta de mil formas, mas a álgebra é única.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from rdflib import RDF, BNode, Literal, URIRef, Variable
from rdflib.paths import InvPath, Path, SequencePath
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.parserutils import CompValue

from ..knowledge.index import MET

XSD = "http://www.w3.org/2001/XMLSchema#"
NUMERIC = {XSD + t for t in ("integer", "decimal", "double", "float", "int", "long")}
AGG_NAMES = {"Aggregate_Avg": "avg", "Aggregate_Sum": "sum", "Aggregate_Min": "min",
             "Aggregate_Max": "max", "Aggregate_Count": "count"}


@dataclass
class Comparison:
    op: str
    value: Any            # Decimal | datetime | date
    kind: str             # "numeric" | "datetime" | "date"
    var: str | None = None   # variável comparada ('?d'), quando o lado esquerdo é uma variável simples


@dataclass
class QueryFacts:
    iris: set[str] = field(default_factory=set)
    types_by_var: dict[str, set[str]] = field(default_factory=dict)
    comparisons: list[Comparison] = field(default_factory=list)
    aggregates: set[str] = field(default_factory=set)
    projected: list[str] = field(default_factory=list)
    lang_literals: list[tuple[str, str]] = field(default_factory=list)
    triples: list[tuple[str, str, str]] = field(default_factory=list)   # (sujeito, propriedade, objeto), caminhos expandidos
    string_compares: list[tuple[str, str]] = field(default_factory=list)   # (?var, texto): FILTER(?var = "texto")
    functions: set[str] = field(default_factory=set)       # IRIs de funções chamadas (ex.: xsd:date)
    values: dict[str, set[str]] = field(default_factory=dict)   # VALUES ?var { <iri> ... }: ?var -> IRIs
    datetimes: list[datetime] = field(default_factory=list)     # todo literal xsd:dateTime da consulta (instantes e limites)
    has_union: bool = False                                     # a consulta combina padrões com UNION
    day_literals: list[date] = field(default_factory=list)      # datas constantes em `met:localDate "AAAA-MM-DD"^^xsd:date`
    bind_conflicts: list[str] = field(default_factory=list)     # BIND(... AS ?v) com ?v já em uso no padrão (o Ontop recusa; o rdflib aceita)
    filter_issues: list[str] = field(default_factory=list)      # FILTER que não é só conjunção de comparações (OR, NOT, EXISTS) ou filtro dentro de OPTIONAL/MINUS
    aggregate_args: list[tuple[str, str]] = field(default_factory=list)   # (agregação, "?var" | "*" | "expr"): o que cada AVG/SUM/MIN/MAX/COUNT recebe
    grouped_expr_projections: list[str] = field(default_factory=list)   # `SELECT (YEAR(?t) AS ?a) … GROUP BY (YEAR(?t))`: expressão sobre a chave do grupo


def _walk(node: Any):
    if isinstance(node, CompValue):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, (list, tuple, set)):
        for v in node:
            yield from _walk(v)
    elif isinstance(node, dict):
        for v in node.values():
            yield from _walk(v)


def _terms(node: Any):
    if isinstance(node, (URIRef, Literal)):
        yield node
    elif isinstance(node, Path):
        for a in getattr(node, "args", None) or [getattr(node, "arg", None)]:
            if a is not None:
                yield from _terms(a)
    elif isinstance(node, CompValue):
        for v in node.values():
            yield from _terms(v)
    elif isinstance(node, (list, tuple, set)):
        for v in node:
            yield from _terms(v)
    elif isinstance(node, dict):
        for v in node.values():
            yield from _terms(v)


def _expr_vars(node: Any) -> set[str]:
    """Nomes das variáveis que aparecem numa expressão da álgebra."""
    out: set[str] = set()

    def rec(x: Any) -> None:
        if isinstance(x, Variable):
            out.add(str(x))
        elif isinstance(x, CompValue):
            for v in x.values():
                rec(v)
        elif isinstance(x, (list, tuple, set)):
            for v in x:
                rec(v)
    rec(node)
    return out


def _pattern_vars(node: Any) -> set[Variable]:
    """Variáveis que o padrão `node` já liga: triplas, VALUES, projeção de subconsulta e BIND anterior."""
    out: set[Variable] = set()
    for n in _walk(node):
        if n.name == "BGP":
            for triple in n.get("triples", []):
                out |= {t for t in triple if isinstance(t, Variable)}
        elif n.name == "values":
            for row in n.get("res") or []:
                out |= {Variable(v) if not isinstance(v, Variable) else v for v in row}
        elif n.name == "Project":
            out |= {v for v in (n.get("PV") or []) if isinstance(v, Variable)}
        elif n.name == "Extend" and isinstance(n.get("var"), Variable):
            out.add(n.get("var"))
    return out


def node_key(t: Any) -> str:
    """Chave de nó: ?var, <iri>, _:bnode ou \"literal\"."""
    if isinstance(t, Variable):
        return f"?{t}"
    if isinstance(t, URIRef):
        return f"<{t}>"
    if isinstance(t, Literal):
        return '"lit"'
    return f"_:{t}" if isinstance(t, BNode) else str(t)


def _expand(s: str, p: Any, o: str, fresh) -> list[tuple[str, str, str]]:
    """Desfaz caminhos de sequência (a/b) e inversos (^a) em tríades simples. Alternativas e fechos são ignorados."""
    if isinstance(p, URIRef):
        return [(s, str(p), o)]
    if isinstance(p, InvPath):
        return _expand(o, p.arg, s, fresh)
    if isinstance(p, SequencePath):
        out, cur = [], s
        for i, a in enumerate(p.args):
            nxt = o if i == len(p.args) - 1 else fresh()
            out += _expand(cur, a, nxt, fresh)
            cur = nxt
        return out
    return []


def _comparison(op: str, other: Any, var: str | None = None) -> Comparison | None:
    if getattr(other, "name", None) == "UnaryMinus" and isinstance(other.get("expr"), Literal):    # limiar negativo (-5): o parser o dá como `-` sobre 5
        base = _comparison(op, other.get("expr"), var)
        return Comparison(op, -base.value, "numeric", var) if base is not None and base.kind == "numeric" else None
    if not isinstance(other, Literal):
        return None
    dt = str(other.datatype) if other.datatype else ""
    try:
        if dt in NUMERIC:
            return Comparison(op, Decimal(str(other)), "numeric", var)
        if dt == XSD + "dateTime":
            v = other.toPython()
            return Comparison(op, v, "datetime", var) if isinstance(v, datetime) else None
        if dt == XSD + "date":
            v = other.toPython()
            return Comparison(op, v, "date", var) if isinstance(v, date) else None
    except (InvalidOperation, ValueError):
        return None
    return None


def extract(query: str) -> QueryFacts:
    """`query` deve incluir os PREFIX. Levanta exceção do rdflib se a consulta não for válida."""
    pq = prepareQuery(query)
    facts = QueryFacts()
    for t in _terms(pq.algebra):
        if isinstance(t, URIRef):
            facts.iris.add(str(t))
        elif t.datatype is not None and str(t.datatype) == XSD + "dateTime":
            v = t.toPython()
            if isinstance(v, datetime):
                facts.datetimes.append(v)
        elif t.language:
            facts.lang_literals.append((str(t), t.language))
    counter = iter(range(10**6))
    fresh = lambda: f"_:p{next(counter)}"
    for n in _walk(pq.algebra):
        if n.name == "BGP":
            for s, p, o in n.get("triples", []):
                facts.triples += _expand(node_key(s), p, node_key(o), fresh)
                if isinstance(p, URIRef) and str(p) == MET + "localDate" and isinstance(o, Literal) and isinstance(o.toPython(), date):
                    facts.day_literals.append(o.toPython())
                if p == RDF.type and isinstance(s, Variable) and isinstance(o, URIRef):
                    facts.types_by_var.setdefault(str(s), set()).add(str(o))
        elif n.name == "values":
            for row in n.get("res") or []:
                for var, term in row.items():
                    if isinstance(term, URIRef):
                        facts.values.setdefault(f"?{var}", set()).add(str(term))
        elif n.name == "Union":
            facts.has_union = True
        elif n.name == "Extend":
            # `(COUNT(?o) AS ?n)` no SELECT também vira Extend e o `_vars` do filho agregado inclui ?n: só conta conflito com variável
            # do PADRÃO (triplas, VALUES, subconsulta, BIND anterior), que é o que o SPARQL 1.1 e o Ontop proíbem.
            # O rdflib também insere Extend internos (expr `__agg_N__`) para reexpor variáveis do GROUP BY e aliases de agregados.
            internal = str(n.get("expr")).startswith("__agg_")
            if not internal and n.get("var") is not None and n.get("var") in _pattern_vars(n.get("p")):
                facts.bind_conflicts.append(str(n.get("var")))
            # Expressão NÃO agregada sobre a chave do grupo, calculada depois do agrupamento: o rdflib trata a chave como uma amostra
            # (Aggregate_Sample) e aceita; o Ontop responde HTTP 400 ("non-aggregate expression … not allowed in projection when using
            # GROUP BY"). O jeito aceito é dar nome à chave no GROUP BY: `GROUP BY (YEAR(?d) AS ?year)` e projetar ?year.
            if n.get("var") is not None and isinstance(n.get("expr"), CompValue):
                samples = {str(a.get("res")) for g in _walk(pq.algebra) if g.name == "AggregateJoin" for a in (g.get("A") or [])
                           if getattr(a, "name", "") == "Aggregate_Sample"}
                if _expr_vars(n.get("expr")) & samples:
                    facts.grouped_expr_projections.append(str(n.get("var")))
        elif n.name == "Function":
            facts.functions.add(str(n.get("iri")))
        elif n.name in AGG_NAMES:
            facts.aggregates.add(AGG_NAMES[n.name])
            arg = n.get("vars")
            facts.aggregate_args.append((AGG_NAMES[n.name], f"?{arg}" if isinstance(arg, Variable) else ("*" if arg in (None, "*") else "expr")))
        elif n.name == "Filter":
            # O validador compara CADA comparação achada com a interpretação, o que só vale se elas se somam (AND) e valem para o resultado
            # inteiro. `a >= x || b < y` amplia o período e passa na conferência de operadores (medido: média de 2019 → 2016–2025).
            for sub in _walk(n.get("expr")):
                if sub.name == "ConditionalOrExpression":
                    facts.filter_issues.append("OR")
                elif sub.name == "UnaryNot":
                    facts.filter_issues.append("NOT")
                elif sub.name in ("Builtin_EXISTS", "Builtin_NOTEXISTS"):
                    facts.filter_issues.append("EXISTS")
        elif n.name == "LeftJoin" and n.get("expr") is not None and getattr(n.get("expr"), "name", "") != "TrueFilter":
            facts.filter_issues.append("FILTER_IN_OPTIONAL")
        elif n.name == "Minus":
            facts.filter_issues.append("MINUS")
        elif n.name == "RelationalExpression":
            expr = n.get("expr")
            c = _comparison(str(n.get("op")), n.get("other"), f"?{expr}" if isinstance(expr, Variable) else None)
            if c:
                facts.comparisons.append(c)
            other = n.get("other")
            if (str(n.get("op")) in ("=", "!=") and isinstance(n.get("expr"), Variable) and isinstance(other, Literal)
                    and (other.datatype is None or str(other.datatype) == XSD + "string")):
                facts.string_compares.append((f"?{n.get('expr')}", str(other)))
    facts.projected = [str(v) for v in (pq.algebra.get("PV") or [])]
    return facts
