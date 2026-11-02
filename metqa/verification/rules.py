"""Regras determinísticas que validam o que o LLM propõe (interpretação e consulta SPARQL).

Camadas:
  L1 sintaxe e política   — a consulta é SELECT/ASK, sem SERVICE/FROM/escrita (metqa.execution.store.check_policy)
  L2 vocabulário          — todo IRI e rótulo existe na ontologia/grafo; tipos não violam disjunção (D-13)
  L3 conformidade         — a consulta faz exatamente o que a interpretação registrada diz
Nenhuma regra prova que a consulta responde à intenção do usuário; elas barram o que é verificável.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from metqa.domain.contract import Diagnostic, Interpretation
from metqa.execution.store import PREFIXES, PolicyError, check_policy

from rdflib import RDF

from ..knowledge import index as vocab
from .query_facts import QueryFacts, extract
from ..knowledge.index import OntologyIndex, expand

L1, L2, L3 = "L1", "L2", "L3"
AGGREGATIONS = {"avg", "min", "max", "sum", "count"}
COUNT_VARS = ("n", "count", "cnt")
_XSD = "http://www.w3.org/2001/XMLSchema#"
SPARQL_CASTS = {_XSD + t for t in ("integer", "decimal", "float", "double", "string", "boolean", "dateTime")}


@dataclass
class PipelineInterpretation(Interpretation):
    record_kind: str = "observation"     # "observation" | "forecast"
    instant: str | None = None           # consulta de UM instante ("às 12h"): ISO 8601 com fuso; exclui período
    # Forma do resultado (prompt v6). Vazios = comportamento de sempre. Quando preenchidos, a consulta é MONTADA por código
    # (pipeline/compiler.py::compile_structured) e não escrita pelo LLM: fiel à interpretação por construção.
    group_by: list = field(default_factory=list)    # "station"|"year"|"month"|"day"|"value"|"met:<atributo próprio da grandeza>"
    attributes: list = field(default_factory=list)  # atributos a mostrar junto do superlativo (ex.: "em qual cabeceira")
    order: dict | None = None                        # {"by": "aggregate", "direction": "asc"|"desc", "limit": 1..100}
    # "em quantos DIAS a máxima passou de 30": agrega cada dia (agg) e conta os dias que cumprem a condição; aggregation = "count"
    daily: dict | None = None                        # {"agg": "max"|"min"|"avg"|"sum", "op": ">"|..., "value": número, "unit": opcional}
    # v8 (pipeline/reconcile.py): vêm da leitura determinística da pergunta, nunca do LLM
    hours: tuple | None = None                       # parte do dia: [h0, h1) em hora local ("de madrugada" = (0, 6))
    weekdays: list | None = None                     # dias da semana (0 = segunda ... 6 = domingo); "fins de semana" = [5, 6]
    count_of: str | None = None                      # o que a contagem conta: "readings" | "hours" | "days" | "reports"
    local_hours: list | None = None                  # metqa: CONJUNTO de horas locais (atravessa a meia-noite); tem precedência sobre `hours`

    @property
    def structured(self) -> bool:
        return bool(self.group_by or self.attributes or self.order or self.daily)


GROUP_DIMS = ("station", "year", "month", "day", "value")
TIME_DIMS = ("year", "month", "day")
MAX_LIMIT = 100


def own_attributes(index: OntologyIndex, prop_iri: str) -> set[str]:
    """Atributos que só algumas grandezas têm (do mapeamento), ex.: met:runwayDesignator no vento."""
    return set(index.attributes.get(prop_iri, set())) - vocab.OBS_COMMON - {"a"}


@dataclass
class Finding:
    layer: str
    diag: Diagnostic


def _err(layer: str, code: str, msg: str, **details) -> Finding:
    return Finding(layer, Diagnostic(code, "error", msg, details))


# --------------------------------------------------------------------------------------------
# Interpretação (etapa 1)
# --------------------------------------------------------------------------------------------

def parse_period(period: dict) -> tuple[date, date, str, bool]:
    start, end = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
    tz = period.get("tz", "-03:00")
    datetime.fromisoformat(f"2000-01-01T00:00:00{tz}")     # valida o offset
    if end < start:
        raise ValueError("fim anterior ao início")
    return start, end, tz, bool(period.get("inclusive_end", True))


def _schema(interp: PipelineInterpretation) -> list[Finding]:
    """Tipos do que o LLM devolveu. JSON válido não garante forma: 'entities': ['SBGR'] ou 'period': '2024' derrubariam
    as regras seguintes com TypeError/AttributeError (e uma exceção não tratada é uma falha silenciosa do sistema)."""
    bad = []
    if not (isinstance(interp.properties, list) and all(isinstance(p, str) for p in interp.properties)):
        bad.append("properties deve ser lista de textos")
    if not (isinstance(interp.entities, list) and all(isinstance(e, dict) and isinstance(e.get("iri"), str) for e in interp.entities)):
        bad.append("entities deve ser lista de objetos com 'iri' (texto)")
    if not (isinstance(interp.filters, list) and all(isinstance(f, dict) for f in interp.filters)):
        bad.append("filters deve ser lista de objetos")
    if interp.period is not None and not (isinstance(interp.period, dict) and isinstance(interp.period.get("start"), str)
                                          and isinstance(interp.period.get("end"), str)):
        bad.append("period deve ser null ou objeto com 'start' e 'end' (AAAA-MM-DD)")
    if interp.aggregation is not None and not isinstance(interp.aggregation, str):
        bad.append("aggregation deve ser null ou texto")
    if not isinstance(interp.record_kind, str):
        bad.append("record_kind deve ser texto")
    if interp.instant is not None:
        try:
            if datetime.fromisoformat(str(interp.instant)).tzinfo is None:
                raise ValueError("sem fuso")
        except (TypeError, ValueError):
            bad.append("instant deve ser null ou data-hora ISO 8601 com fuso (ex.: 2026-03-05T12:00:00-03:00)")
    for name in ("group_by", "attributes"):
        value = getattr(interp, name)
        if not (isinstance(value, list) and all(isinstance(x, str) for x in value)):
            bad.append(f"{name} deve ser lista de textos")
    if interp.order is not None:
        o = interp.order
        if not (isinstance(o, dict) and o.get("by") == "aggregate" and o.get("direction") in ("asc", "desc")
                and isinstance(o.get("limit"), int) and not isinstance(o.get("limit"), bool) and 1 <= o["limit"] <= MAX_LIMIT):
            bad.append(f'order deve ser null ou {{"by": "aggregate", "direction": "asc"|"desc", "limit": 1 a {MAX_LIMIT}}}')
    if interp.daily is not None:
        d = interp.daily
        if not (isinstance(d, dict) and d.get("agg") in ("max", "min", "avg", "sum") and d.get("op") in (">", ">=", "<", "<=", "=")
                and isinstance(d.get("value"), (int, float)) and not isinstance(d.get("value"), bool)):
            bad.append('daily deve ser null ou {"agg": "max"|"min"|"avg"|"sum", "op": ">"|">="|"<"|"<="|"=", "value": número, "unit": opcional}')
    return [_err(L3, "BAD_SCHEMA", f"Formato inválido da interpretação: {m}") for m in bad]


def _structure_rules(interp: PipelineInterpretation, index: OntologyIndex) -> list[Finding]:
    """Forma do resultado (group_by / attributes / order): só o que o compilador sabe montar e o grafo tem."""
    if not interp.structured:
        return []
    if len(interp.properties) != 1 or interp.record_kind != "observation" or interp.instant is not None:
        return [_err(L3, "STRUCTURE_NEEDS_ONE_PROPERTY", "group_by, attributes e order valem para UMA grandeza observada, sem instante")]
    out: list[Finding] = []
    prop = expand(interp.properties[0])
    own = own_attributes(index, prop)
    day_data = vocab.MET + "localDate" in index.data_predicates
    seen: list[str] = []
    for dim in interp.group_by:
        d = dim if dim in GROUP_DIMS else expand(dim)
        if d in seen:
            out.append(_err(L3, "DUPLICATE_DIMENSION", f"Dimensão repetida em group_by: {dim}"))
        seen.append(d)
        if d in TIME_DIMS and not day_data:
            out.append(_err(L2, "DIMENSION_WITHOUT_DATA", f"'{dim}' agrupa pelo dia local (met:localDate), que este grafo não tem"))
        elif d not in GROUP_DIMS and d not in own:
            out.append(_err(L2, "UNKNOWN_DIMENSION",
                            f"'{dim}' não é dimensão de agrupamento de {interp.properties[0]} (use {', '.join(GROUP_DIMS)} ou "
                            f"{', '.join(sorted(vocab._short(a) for a in own)) or 'nenhum atributo próprio'})", dim=dim))
    if sum(d in TIME_DIMS for d in seen) > 1:
        out.append(_err(L3, "ONE_TIME_DIMENSION", "Use UMA só dimensão de tempo (year, month ou day)"))
    if interp.group_by and interp.aggregation is None:
        out.append(_err(L3, "GROUP_BY_NEEDS_AGGREGATION", "group_by sem agregação: informe avg, min, max, sum ou count"))
    if "value" in seen and interp.aggregation != "count":
        out.append(_err(L3, "VALUE_GROUP_NEEDS_COUNT", "Agrupar pelo valor medido só faz sentido contando (aggregation 'count')"))
    if interp.group_by and interp.filters:
        out.append(_err(L3, "GROUPED_FILTER_AMBIGUOUS", "Filtro numérico com agrupamento é ambíguo (filtrar as leituras ou os grupos?): não suportado"))
    for a in interp.attributes:
        if expand(a) not in own:
            out.append(_err(L2, "UNKNOWN_ATTRIBUTE", f"'{a}' não é atributo de {interp.properties[0]}", attribute=a))
    if interp.attributes and interp.group_by:
        out.append(_err(L3, "ATTRIBUTES_WITH_GROUPING", "attributes é para o superlativo; com group_by o atributo entra como dimensão"))
    if interp.attributes and not interp.group_by and interp.aggregation not in ("max", "min"):
        out.append(_err(L3, "ATTRIBUTES_NEED_SUPERLATIVE", "attributes só vale com aggregation 'max' ou 'min' (a leitura que atinge o máximo/mínimo)"))
    if interp.order and not interp.group_by:
        out.append(_err(L3, "ORDER_NEEDS_GROUP_BY", "order ordena os GRUPOS: precisa de group_by"))
    if interp.daily:
        if interp.aggregation != "count" or interp.group_by or interp.attributes or interp.order or interp.filters:
            out.append(_err(L3, "DAILY_SHAPE", "daily conta DIAS: use aggregation \"count\" e nenhum group_by, attributes, order ou filters"))
        info = index.properties.get(prop)
        if info is not None and info.aggregations and interp.daily["agg"] not in info.aggregations:
            out.append(_err(L3, "AGGREGATION_NOT_ALLOWED", f"A ontologia não admite '{interp.daily['agg']}' para {interp.properties[0]}"))
        if not day_data:
            out.append(_err(L2, "DIMENSION_WITHOUT_DATA", "daily agrupa pelo dia local (met:localDate), que este grafo não tem"))
    return out


def validate_interpretation(interp: PipelineInterpretation, index: OntologyIndex) -> list[Finding]:
    """Esquema, estrutura e mundo fechado (grandeza, estação, agregação admitida, período, filtros). Nada aqui olha a frase: a linguagem é do
    LLM, conferida por concordância, conservação da evidência e pelo usuário (metqa/understanding, metqa/dialogue)."""
    out: list[Finding] = _schema(interp)
    if out:
        return out
    out += _structure_rules(interp, index)
    for p in interp.properties:
        if expand(p) not in index.properties:
            out.append(_err(L2, "UNKNOWN_PROPERTY", f"Propriedade fora da ontologia: {p}", iri=p))
    for e in interp.entities:
        if expand(e.get("iri", "")) not in index.entities:
            out.append(_err(L2, "UNKNOWN_ENTITY", f"Entidade sem correspondência no grafo: {e.get('text')}", entity=e))
    if interp.aggregation is not None and interp.aggregation not in AGGREGATIONS:
        out.append(_err(L3, "BAD_AGGREGATION", f"Agregação inválida: {interp.aggregation}"))
    if interp.aggregation in AGGREGATIONS:
        for p in interp.properties:
            info = index.properties.get(expand(p))
            if info and info.aggregations and interp.aggregation not in info.aggregations:
                out.append(_err(L3, "AGGREGATION_NOT_ALLOWED",
                                f"A ontologia não admite '{interp.aggregation}' para {p} (admite: {', '.join(sorted(info.aggregations))})",
                                iri=p, allowed=sorted(info.aggregations)))
    if interp.period is not None:
        try:
            parse_period(interp.period)
        except (KeyError, ValueError) as e:
            out.append(_err(L3, "BAD_PERIOD", f"Período inválido: {e}", period=interp.period))
    for f in interp.filters:
        try:
            v = Decimal(str(f["value"]))
            # NaN, Infinity e expoentes absurdos ('1e999999999') quebram a consulta ou esgotam memória ao formatar
            if not v.is_finite() or abs(v) >= Decimal("1e15"):
                raise ValueError("valor fora de faixa")
            if f["op"] not in {">", ">=", "<", "<=", "="}:
                raise ValueError(f["op"])
        except (KeyError, ValueError, ArithmeticError):     # ArithmeticError: Overflow/InvalidOperation de Decimal ('1e999999999')
            out.append(_err(L3, "BAD_FILTER", f"Filtro inválido: {f}", filter=f))
    if interp.record_kind not in {"observation", "forecast"}:
        out.append(_err(L3, "BAD_RECORD_KIND", f"Tipo de registro inválido: {interp.record_kind}"))
    return out


# --------------------------------------------------------------------------------------------
# Consulta (etapa 2)
# --------------------------------------------------------------------------------------------

def _vocabulary(facts: QueryFacts, index: OntologyIndex) -> list[Finding]:
    out = []
    for iri in sorted(facts.iris):
        if not index.is_known_iri(iri):
            out.append(_err(L2, "UNKNOWN_IRI", f"IRI inexistente na ontologia/grafo: {iri}", iri=iri))
    for text, lang in facts.lang_literals:
        if lang == "pt" and text not in index.labels:
            out.append(_err(L2, "UNKNOWN_LABEL", f"Rótulo sem correspondência no grafo: {text!r}", label=text))
    # Funções fora do SPARQL 1.1: o rdflib deixa a variável sem valor em silêncio (ex.: BIND(xsd:date(?t) AS ?dia)
    # colapsa os grupos e devolve 1 linha no lugar de 7), e outros motores falham de modo diferente.
    for f in sorted(facts.functions - SPARQL_CASTS):
        out.append(_err(L2, "UNSUPPORTED_FUNCTION",
                        f"{f.rsplit('#', 1)[-1] and 'xsd:' + f.rsplit('#', 1)[-1]}() não é função do SPARQL 1.1 (só há casts para integer, decimal, "
                        f"float, double, string, boolean e dateTime). Para o dia local use SUBSTR(STR(?t), 1, 10).", function=f))
    # SPARQL 1.1: BIND não pode atribuir a uma variável que já aparece no padrão. O rdflib deixa passar; o Ontop responde HTTP 400
    # ("BIND clause alias 'station' was previously used"), o que chegaria ao usuário como erro de execução sem chance de reparo.
    for var in sorted(set(facts.bind_conflicts)):
        out.append(_err(L2, "BIND_REUSES_VARIABLE",
                        f"BIND(... AS ?{var}) usa um nome que já está em uso na consulta; o motor recusa. Use um nome novo para o BIND "
                        f"(ou projete a variável original)", var=var))
    for issue in sorted(set(facts.filter_issues)):
        out.append(_err(L2, "FILTER_NOT_CONJUNCTIVE",
                        f"FILTER com {issue}: as condições têm de ser uma conjunção (&&) de comparações no nível principal da consulta; "
                        f"com {issue} a conferência de período e limites deixa de garantir o que a consulta realmente seleciona", construct=issue))
    # AVG/SUM/MIN/MAX só sobre o valor numérico medido. `AVG(?v * 0)` ou `SUM(?outra)` devolve um número que parece resposta.
    numeric_vars = {o for _, p, o in facts.triples if p == vocab.QUDT + "numericValue"}
    for agg, arg in facts.aggregate_args:
        if agg == "count":
            continue
        if arg == "expr" or arg == "*" or arg not in numeric_vars:
            out.append(_err(L2, "AGGREGATE_ARGUMENT", f"{agg.upper()} recebe {arg if arg.startswith('?') else 'uma expressão'}: "
                            f"a agregação tem de ser sobre a variável do qudt:numericValue, sem cálculo", agregacao=agg, argumento=arg))
    # Idem para uma expressão sobre a chave do grupo na projeção (medido no grafo real, RF06 do v4): HTTP 400 no Ontop, aceito pelo rdflib.
    for var in sorted(set(facts.grouped_expr_projections)):
        out.append(_err(L2, "GROUPED_PROJECTION_EXPR",
                        f"(… AS ?{var}) calcula uma expressão sobre a chave do GROUP BY depois do agrupamento; o motor recusa. "
                        f"Dê nome à chave no próprio GROUP BY e projete o nome: GROUP BY (YEAR(?d) AS ?{var}) … SELECT ?{var}", var=var))
    # Relação que a ontologia declara mas o grafo não popula: a consulta é vazia por construção (ex.: met:inReport/reportOf
    # existem na ontologia e no mapeamento do Ontop, mas não neste grafo sintético).
    if index.data_predicates:
        used = {p for _, p, _ in facts.triples if p != str(RDF.type)}
        for p in sorted(used - index.data_predicates):
            if not any(p.startswith(ns) for ns in vocab.FREE_NAMESPACES):
                out.append(_err(L2, "RELATION_WITHOUT_DATA",
                                f"A relação {vocab._short(p)} existe na ontologia, mas este grafo não tem nenhuma asserção dela: a consulta seria vazia. "
                                f"Use apenas as relações listadas no contexto.", relation=p))
    # Caminhos ALTERNATIVOS até as mesmas observações (hosts/madeBySensor e siteOf/hasFeatureOfInterest) combinados por UNION
    # contam cada observação duas vezes: o SUM dobra e o ?n também, e nada na consulta parece errado. Medido: H02, 42,6 mm no
    # lugar de 21,3 mm, entregue como resposta. Com agregação, UNION não é necessário para nenhuma pergunta suportada.
    if facts.has_union and facts.aggregates:
        out.append(_err(L2, "UNION_WITH_AGGREGATE",
                        "UNION numa consulta agregada conta cada observação mais de uma vez (caminhos alternativos do contexto "
                        "chegam às MESMAS observações). Use UM só caminho."))
    # Sem inferência (D-03), tipar por uma superclasse sem instâncias diretas devolve 'sem registros' em silêncio
    # (ex.: ?o a sosa:Observation quando os dados só têm met:InstantaneousObservation).
    if not index.inference:
        for var, classes in facts.types_by_var.items():
            for c in sorted(classes - index.direct_types):
                out.append(_err(L2, "CLASS_WITHOUT_DIRECT_INSTANCES",
                                f"?{var} tipada por {c}, sem instâncias diretas e sem inferência no endpoint: o resultado seria vazio",
                                var=var, cls=c))
    # D-13: variável tipada com duas classes disjuntas é insatisfazível (resultado vazio silencioso)
    flagged = set()
    for var, classes in facts.types_by_var.items():
        closed = set().union(*(index.closure(c) for c in classes))
        for pair in (index.check_disjoint or index.disjoint):
            if pair <= closed:
                flagged.add(f"?{var}")
                out.append(_err(L2, "DISJOINT_TYPES", f"?{var} tipada com classes disjuntas: {sorted(pair)}", var=var))
    return out + _type_check(facts, index, flagged)


def _type_check(facts: QueryFacts, index: OntologyIndex, already: set[str]) -> list[Finding]:
    """Checagem de tipos dos CAMINHOS, derivada dos axiomas de ontology/met-structure.ttl.

    Propaga tipos por domínio/imagem das propriedades, pela classe de observação da grandeza (met:observedAs) e
    pelas restrições allValuesFrom (ex.: o tempo de uma observação acumulada é time:Interval). Um nó que acaba com
    dois tipos disjuntos (ex.: Interval e Instant) torna a consulta vazia por construção, mesmo sendo sintaticamente
    válida e usando só termos que existem."""
    types: dict[str, set[str]] = {}

    def add(n: str, c: str) -> None:
        types.setdefault(n, set()).add(c)

    def closed(n: str) -> set[str]:
        return set().union(*(index.closure(c) for c in types.get(n, ())))

    is_node = lambda o: o.startswith("?") or o.startswith("_:")
    rdf_type, observed = str(RDF.type), vocab.SOSA + "observedProperty"
    # tipos conhecidos pelo grafo: estações citadas como constante ou ligadas por VALUES são met:WeatherStation
    station = vocab.MET + "WeatherStation"
    for _, _, o in facts.triples:
        if o.startswith("<") and o[1:-1] in index.entities:
            add(o, station)
    for s, _, _ in facts.triples:
        if s.startswith("<") and s[1:-1] in index.entities:
            add(s, station)
    for var, iris in facts.values.items():
        if any(i in index.entities for i in iris):
            add(var, station)
    for s, p, o in facts.triples:                        # tipos declarados primeiro: o domínio alternativo (met:alsoDomain) depende deles
        if p == rdf_type and o.startswith("<"):
            add(s, o[1:-1])
    for _ in range(3):                                   # ponto fixo (poucas iterações bastam para cadeias curtas)
        for s, p, o in facts.triples:
            if p == rdf_type:
                if o.startswith("<"):
                    add(s, o[1:-1])
                continue
            if p in index.domain and is_node(s) and not (index.also_domain.get(p, set()) & closed(s)):   # sujeito já é de outro domínio admitido
                add(s, index.domain[p])
            if p in index.range_ and not o.startswith('"'):
                add(o, index.range_[p])
            if p == observed and o.startswith("<"):
                info = index.properties.get(o[1:-1])
                if info and info.kind:
                    add(s, info.kind)
            if is_node(o):
                for c in closed(s):
                    if (c, p) in index.value_restrictions:
                        add(o, index.value_restrictions[(c, p)])
    out = []
    # Estação CONSTANTE com a relação ao contrário: o domínio/imagem acima só se propaga para variáveis, e met:WeatherStation e
    # met:WeatherReport não são disjuntas, então `st:SBBE met:reportOf ?r` (o certo é `?r met:reportOf st:SBBE`) passava sem aviso,
    # era vazia por construção e chegava ao usuário como "sem registros" onde há dados (medido: RD02 no grafo real).
    station_closure = index.closure(station)
    for s, p, o in facts.triples:
        if s.startswith("<") and s[1:-1] in index.entities and p in index.domain and index.domain[p] not in station_closure:
            out.append(_err(L2, "RELATION_DIRECTION",
                            f"A estação não pode ser o sujeito de {vocab._short(p)}: o sujeito dessa relação é {vocab._short(index.domain[p])}. "
                            f"Relação escrita ao contrário? A consulta seria vazia.", relation=p, subject=s))
        if o.startswith("<") and o[1:-1] in index.entities and p in index.range_ and index.range_[p] not in station_closure:
            out.append(_err(L2, "RELATION_DIRECTION",
                            f"A estação não pode ser o objeto de {vocab._short(p)}: o objeto dessa relação é {vocab._short(index.range_[p])}. "
                            f"Relação escrita ao contrário? A consulta seria vazia.", relation=p, object=o))
    # um recurso (ex.: a unidade, objeto de qudt:unit) comparado a um texto nunca é verdadeiro: a consulta é vazia
    for var, text in facts.string_compares:
        if types.get(var):
            out.append(_err(L2, "RESOURCE_COMPARED_TO_STRING",
                            f"{var} é um recurso ({', '.join(sorted(vocab._short(c) for c in types[var]))}); compará-lo com o texto "
                            f"{text!r} nunca é verdadeiro. Use o IRI (ex.: unit:DEG_C) ou não compare.", var=var, text=text))
    for node in types:
        if node in already:
            continue
        for pair in (index.check_disjoint or index.disjoint):
            if pair <= closed(node):
                shapes = {vocab._short(c) for c in pair}
                hint = (" O caminho de tempo não corresponde à forma do tempo da grandeza (ver 'tempo' no contexto)."
                        if {"time:Instant", "time:Interval"} == shapes else
                        " A estação é uma plataforma que hospeda sensores (sosa:hosts); o objeto de sosa:hasFeatureOfInterest é o local (met:Site), não a estação."
                        if {"sosa:Platform", "sosa:FeatureOfInterest"} <= shapes else
                        " met:reportOf liga o BOLETIM (sujeito) à ESTAÇÃO (objeto): escreva `?boletim met:reportOf ?estacao`, nunca o contrário."
                        if shapes & {"met:WeatherReport"} and shapes & {"met:WeatherStation", "sosa:Platform"} else "")
                out.append(_err(L2, "TYPE_CLASH", f"{node} receberia tipos disjuntos {sorted(shapes)}: a consulta é vazia por construção.{hint}",
                                node=node, tipos=sorted(vocab._short(c) for c in types[node])))
    return out


def _expected_time(period: dict, containment: bool = False) -> tuple[list, list]:
    start, end, tz, inclusive = parse_period(period)
    end_excl = end + timedelta(days=1) if inclusive else end
    dt = lambda d: datetime.fromisoformat(f"{d.isoformat()}T00:00:00{tz}")
    lower = [(">=", dt(start)), (">=", start)]
    if containment:       # acumulado: o fim do intervalo pode coincidir com o fim do período (<=), nunca ser menor que ele (<)
        return lower, [("<=", dt(end_excl))]
    upper = [("<", dt(end_excl)), ("<=", dt(end_excl)), (("<=" if inclusive else "<"), end)]
    return lower, upper


LOCAL_TZ = "-03:00"      # met:localDate é o dia civil em UTC−3 (D-04)


def _check_day_period(period: dict, comparisons: list, literals: list[date]) -> list[Finding]:
    """Período expresso por `met:localDate` (dia local, sem fuso na consulta). Aceita, para o período [início, fim] inclusivo:
    `?d >= início` (ou `> início−1`), `?d <= fim` (ou `< fim+1`), e, para um dia só, `?d = dia` ou a data constante no padrão.
    Qualquer outro limite é recusado: um dia deslocado ou um fim contado errado muda a soma sem erro nenhum."""
    start, end, tz, inclusive = parse_period(period)
    one = timedelta(days=1)
    last = end if inclusive else end - one
    if tz != LOCAL_TZ:
        return [_err(L3, "LOCALDATE_TZ", f"met:localDate é o dia em UTC−3; o período está em {tz}: use o caminho de tempo com fuso", periodo=period)]
    lower = {(">=", start), (">", start - one)}
    upper = {("<=", last), ("<", last + one)}
    single = {("=", start)} if start == last else set()
    got = [(c.op, c.value) for c in comparisons]
    if literals:                                   # `met:localDate "2024-01-19"^^xsd:date`: vale só para um dia e sem outros limites
        ok = set(literals) == {start} and start == last and not got
    elif single & set(got):
        ok = len(got) == 1
    else:
        ok = any(g in lower for g in got) and any(g in upper for g in got) and all(g in lower | upper for g in got)
    if ok:
        return []
    return [_err(L3, "PERIOD_MISMATCH", "Datas de met:localDate da consulta diferem do período interpretado",
                 periodo=period, obtido=[(op, str(v)) for op, v in got] + [("=", str(d)) for d in literals])]


def _conformance(interp: PipelineInterpretation, facts: QueryFacts, index: OntologyIndex, strict_instant: bool = True) -> list[Finding]:
    out = []
    want_props = {expand(p) for p in interp.properties}
    got_props = {i for i in facts.iris if i in index.properties}
    if want_props != got_props:
        out.append(_err(L3, "PROPERTY_MISMATCH", "Propriedades da consulta diferem da interpretação",
                        esperado=sorted(want_props), obtido=sorted(got_props)))
    # atributo que só algumas grandezas têm (ex.: met:runwayDesignator só no vento): usá-lo com outra grandeza é consulta vazia por construção
    if index.attributes:
        own_all = set().union(*index.attributes.values()) - vocab.OBS_COMMON - {"a"}
        for attr in sorted(facts.iris & own_all):
            lacking = [p for p in interp.properties if expand(p) in index.attributes and attr not in index.attributes[expand(p)]]
            if lacking:
                out.append(_err(L3, "ATTRIBUTE_NOT_AVAILABLE", f"{vocab._short(attr)} não existe para {lacking}: a consulta seria vazia",
                                atributo=attr, grandezas=lacking))
    want_ents = {expand(e["iri"]) for e in interp.entities}
    got_ents = {i for i in facts.iris if i.startswith(vocab.STATION_NS)}
    # estação escolhida pelo RÓTULO (?s rdfs:label "Estação X"@pt) também é uma escolha de estação: conferir com a interpretação
    by_label = {l: iri for iri, labels in index.entities.items() for l in labels}
    got_ents |= {by_label[t] for t, lang in facts.lang_literals if lang == "pt" and t in by_label}
    if want_ents != got_ents:
        out.append(_err(L3, "ENTITY_MISMATCH", "Estações da consulta diferem da interpretação",
                        esperado=sorted(want_ents), obtido=sorted(got_ents)))
    # agregação: exatamente a pedida (mais a contagem ?n exigida por D-10)
    if facts.aggregates:
        expected = ({interp.aggregation} if interp.aggregation else set()) | {"count"}
        if interp.daily:                              # dias que cumprem a condição: agrega cada dia (agg) e soma os acertos
            expected |= {interp.daily["agg"]}
        extra = facts.aggregates - expected
        if extra or (interp.aggregation and interp.aggregation not in facts.aggregates):
            out.append(_err(L3, "AGGREGATION_MISMATCH", "Agregação da consulta difere da interpretação",
                            esperado=sorted(expected), obtido=sorted(facts.aggregates)))
        # D-10: toda consulta agregada projeta ?n. Sem ele, AVG/SUM sobre vazio (=0) parece dado, e a resposta
        # perde o tamanho da amostra (quantas leituras sustentam o valor).
        # (?n projetado mas sem COUNT que o vincule seria uma coluna sempre vazia)
        if "count" not in facts.aggregates or not any(v.lower() in COUNT_VARS for v in facts.projected):
            out.append(_err(L3, "MISSING_COUNT", "Consulta agregada sem ?n (D-10): 'zero' e 'sem dados' se confundem e a amostra some"))
    elif interp.aggregation:
        out.append(_err(L3, "AGGREGATION_MISMATCH", "A interpretação pede agregação e a consulta não agrega",
                        esperado=[interp.aggregation], obtido=[]))
    # filtros numéricos
    numeric = [(c.op, c.value) for c in facts.comparisons if c.kind == "numeric"]
    canon = index.properties.get(expand(interp.properties[0])).unit if len(interp.properties) == 1 and expand(interp.properties[0]) in index.properties else None
    wanted = []
    for f in [*interp.filters, *([interp.daily] if isinstance(interp.daily, dict) else [])]:
        if "op" not in f or "value" not in f:
            continue
        v = vocab.convert_filter_value(f["value"], f.get("unit"), canon)      # '1 km' numa grandeza em metros vale 1000, não 1
        if v is None:
            out.append(_err(L3, "FILTER_UNIT_UNKNOWN", f"Não sei converter a unidade {f.get('unit')} para {canon}: o limiar não pode ser aplicado", filter=f))
            continue
        wanted.append((f["op"], v))
    for op, val in wanted:
        if (op, val) not in numeric:
            same_val = [o for o, v in numeric if v == val]
            code = "FILTER_OPERATOR_MISMATCH" if same_val else "FILTER_MISSING"
            out.append(_err(L3, code, f"Filtro esperado ({op} {val}) ausente na consulta", obtido=same_val))
    for op, val in numeric:
        if (op, val) not in wanted:
            out.append(_err(L3, "FILTER_UNEXPECTED", f"Filtro numérico fora da interpretação: {op} {val}"))
    # instante fixo (consulta de um horário): a interpretação e a consulta têm de falar do MESMO instante
    inst = datetime.fromisoformat(interp.instant) if interp.instant else None
    used = set(facts.datetimes)
    cmp_values = {c.value for c in facts.comparisons if c.kind == "datetime"}
    if inst is not None:
        if inst not in used:
            out.append(_err(L3, "INSTANT_MISMATCH", "A consulta não usa o instante da interpretação", esperado=interp.instant, obtido=sorted(d.isoformat() for d in used)))
        elif used - {inst}:
            out.append(_err(L3, "INSTANT_UNEXPECTED", "A consulta usa outros instantes além do da interpretação", obtido=sorted(d.isoformat() for d in used)))
    elif strict_instant and used - cmp_values:       # prompts antigos (v1–v3) não têm o campo 'instant': não penalizar o que não podem dizer
        out.append(_err(L3, "INSTANT_UNEXPECTED", "A consulta fixa um instante que a interpretação não tem", obtido=sorted(d.isoformat() for d in used - cmp_values)))
    # período
    day_vars = {o for _, p, o in facts.triples if p == vocab.MET + "localDate"}
    day_cmp = [c for c in facts.comparisons if c.kind == "date" and c.var in day_vars]
    uses_day = bool(day_cmp or facts.day_literals)
    timed = [c for c in facts.comparisons if c.kind in ("datetime", "date") and c not in day_cmp
             and not (inst is not None and c.value == inst)]
    if interp.period is None:
        if timed or uses_day:
            out.append(_err(L3, "PERIOD_UNEXPECTED", "A consulta restringe o tempo, a interpretação não"))
    else:
        # Duas formas de dizer o período. A do dia local (met:localDate) e a por data-e-hora são conferidas CADA UMA contra o
        # período da interpretação. Se as duas aparecem, ambas têm de conferir: filtros se somam (AND), então redundância
        # consistente não conta nada duas vezes. Medido no grafo real (RD02): o modelo escreveu as duas, a consulta estava certa, e
        # recusá-la por "mistura" levou a um reparo que a estragou. Qualquer limite que não confira continua sendo PERIOD_MISMATCH.
        try:
            if uses_day:
                out += _check_day_period(interp.period, day_cmp, facts.day_literals)
            if timed or not uses_day:
                lower, upper = _expected_time(interp.period, any(
                    index.properties[expand(p)].containment for p in interp.properties if expand(p) in index.properties))
                has_lower = any((c.op, c.value) in lower for c in timed)
                has_upper = any((c.op, c.value) in upper for c in timed)
                stray = [c for c in timed if (c.op, c.value) not in lower + upper]
                if not (has_lower and has_upper) or stray:
                    out.append(_err(L3, "PERIOD_MISMATCH", "Limites de tempo da consulta diferem do período interpretado",
                                    periodo=interp.period, obtido=[(c.op, str(c.value)) for c in timed]))
        except (KeyError, ValueError):
            return out                                   # BAD_PERIOD já reportado na interpretação
    # observação x previsão
    uses_forecast = bool(facts.iris & vocab.FORECAST_TERMS)
    typed = set().union(*facts.types_by_var.values()) if facts.types_by_var else set()
    if interp.record_kind == "observation":
        if uses_forecast:
            out.append(_err(L3, "FORECAST_IN_OBSERVATION_QUERY", "Pergunta sobre valor registrado usa vocabulário de previsão (D-08)"))
    elif vocab.MET + "Forecast" not in typed:
        out.append(_err(L3, "FORECAST_NOT_SELECTED", "Pergunta sobre previsão sem tipar met:Forecast"))
    return out


def validate_query(sparql: str, interp: PipelineInterpretation | None, index: OntologyIndex,
                   strict_instant: bool = True) -> tuple[QueryFacts | None, list[Finding]]:
    """`sparql` sem PREFIX (o orquestrador os acrescenta)."""
    full = PREFIXES + sparql
    try:
        check_policy(full)
    except PolicyError as e:
        return None, [_err(L1, "POLICY_VIOLATION", str(e))]
    except SyntaxError as e:
        return None, [_err(L1, "SYNTAX_ERROR", f"Consulta inválida: {str(e)[:200]}")]
    try:
        facts = extract(full)
    except Exception as e:                           # falha fechada: se não dá para analisar, não dá para validar, logo não executa
        return None, [_err(L1, "ANALYSIS_ERROR", f"Não foi possível analisar a consulta ({type(e).__name__})")]
    findings = _vocabulary(facts, index)
    if interp is not None:
        findings += _conformance(interp, facts, index, strict_instant)
    return facts, findings


def layers_hit(findings: list[Finding]) -> set[str]:
    return {f.layer for f in findings}
