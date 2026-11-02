"""Índice do vocabulário permitido: a fonte de verdade das validações (o LLM nunca decide o que existe).

Construído a partir da ontologia (ontology/met.ttl) e do grafo de dados (entidades). Tudo que o LLM
citar — propriedade, classe, estação, unidade — é conferido aqui antes de qualquer execução.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from rdflib import OWL, RDF, RDFS, BNode, Graph, Literal, URIRef
from rdflib.namespace import SKOS

from ..util.text import ctx as _ctx

ROOT = Path(__file__).resolve().parent.parent.parent

MET = "https://example.org/kgqa-met/ontology#"
DATA = "https://example.org/kgqa-met/data/"
STATION_NS = DATA + "station/"
SOSA = "http://www.w3.org/ns/sosa/"
TIME = "http://www.w3.org/2006/time#"
QUDT = "http://qudt.org/schema/qudt/"
UNIT = "http://qudt.org/vocab/unit/"

PREFIX_MAP = {"met": MET, "d": DATA, "st": STATION_NS, "sosa": SOSA, "time": TIME, "qudt": QUDT, "unit": UNIT, "skos": "http://www.w3.org/2004/02/skos/core#"}

# Termos de vocabulários externos que o grafo realmente usa. Fora desta lista = IRI inventado.
EXTERNAL_TERMS = {
    SOSA: {"Observation", "Sensor", "Platform", "Result", "FeatureOfInterest", "ObservableProperty", "hosts",
           "hasResult", "madeBySensor", "observedProperty", "phenomenonTime", "resultTime",
           "hasFeatureOfInterest", "observes"},
    TIME: {"Instant", "Interval", "inXSDDateTime", "hasBeginning", "hasEnd", "hasTime"},
    QUDT: {"numericValue", "unit", "QuantityValue"},
}
# Vocabulários de uso livre (estruturais).
FREE_NAMESPACES = (str(RDF), str(RDFS), str(SKOS), "http://www.w3.org/2001/XMLSchema#",
                   "http://www.w3.org/ns/prov#", "http://purl.org/dc/terms/", str(OWL))

# Relações internas de guia (descrevem a ontologia, não existem no grafo): ficam fora do contexto do LLM.
GUIDE_ONLY = {MET + t for t in ("observedAs", "allowsAggregation", "requiresFullContainment", "symbol",
                                "canonicalUnit", "aggregationNote", "answerCaveat", "incompatibleWith", "alsoDomain")}
OBSERVATION = SOSA + "Observation"
FORECAST_TERMS = {MET + t for t in ("Forecast", "forStation", "forecastedProperty", "validTime", "issuedAt")}


def expand(iri: str) -> str:
    """'met:AirTemperature' -> IRI completo; IRIs completos passam sem alteração."""
    if ":" in iri and not iri.startswith("http"):
        pfx, local = iri.split(":", 1)
        if pfx in PREFIX_MAP:
            return PREFIX_MAP[pfx] + local
    return iri


@dataclass
class PropertyInfo:
    iri: str
    labels: list[str]
    unit: str | None
    kind: str | None = None                                  # classe de observação (met:observedAs)
    aggregations: set[str] = field(default_factory=set)      # notações admitidas (met:allowsAggregation)
    accumulated: bool = False                                # derivado de kind
    containment: bool = False                                # intervalo inteiro dentro do período (met:requiresFullContainment)
    caveat: str = ""                                         # ressalva exibida junto da resposta (met:answerCaveat)


@dataclass
class OntologyIndex:
    met_terms: set[str] = field(default_factory=set)
    properties: dict[str, PropertyInfo] = field(default_factory=dict)
    units: set[str] = field(default_factory=set)
    superclasses: dict[str, set[str]] = field(default_factory=dict)   # fecho transitivo de subClassOf
    disjoint: set[frozenset] = field(default_factory=set)
    check_disjoint: set[frozenset] = field(default_factory=set)       # disjuntas + incompatíveis: SÓ para checar consultas (não vai ao contexto)
    entities: dict[str, list[str]] = field(default_factory=dict)      # IRI da estação -> rótulos
    labels: set[str] = field(default_factory=set)                     # rótulos válidos de estações
    direct_types: set[str] = field(default_factory=set)               # classes com instâncias diretas no grafo
    data_predicates: set[str] = field(default_factory=set)            # propriedades com asserções no grafo (perfil dos dados)
    properties_with_data: set[str] = field(default_factory=set)       # grandezas com ao menos uma observação
    inference: bool = False                                           # regime do endpoint (D-03: sem inferência)
    domain: dict[str, str] = field(default_factory=dict)              # propriedade -> classe do sujeito
    also_domain: dict[str, set[str]] = field(default_factory=dict)    # propriedade -> outras classes de sujeito admitidas (met:alsoDomain)
    range_: dict[str, str] = field(default_factory=dict)              # propriedade -> classe do objeto
    value_restrictions: dict[tuple[str, str], str] = field(default_factory=dict)   # (classe, propriedade) -> classe (allValuesFrom)
    structure_props: set[str] = field(default_factory=set)            # propriedades descritas pela camada estrutural
    unit_symbols: dict[str, str] = field(default_factory=dict)        # IRI da unidade -> símbolo (met:symbol)
    fingerprint: str = ""                                             # sha256 (12 hex) de met.ttl + met-structure.ttl: qual ontologia respondeu
    coverage: tuple[date, date] | None = None                         # primeiro e último dia com dados (perfil dos dados)
    notes: dict[str, str] = field(default_factory=dict)               # IRI de met: -> rdfs:comment (texto da própria ontologia)
    attributes: dict[str, set[str]] = field(default_factory=dict)     # grandeza -> predicados das observações dela (do mapeamento real)

    @classmethod
    def load(cls, ontology: Path | None = None, data: Path | None = None, inference: bool = False,
             structure: Path | None = None, with_data: bool = True) -> "OntologyIndex":
        """`with_data=False` carrega só a ontologia (sem o grafo sintético): o perfil dos dados vem de outra fonte (`from_ontop`)."""
        ontology = ontology or ROOT / "ontology" / "met.ttl"
        data = data or ROOT / "data" / "synthetic.nt"
        structure = structure or ROOT / "ontology" / "met-structure.ttl"
        g = Graph().parse(ontology)
        sg = Graph().parse(structure) if structure.exists() else Graph()
        idx = cls(inference=inference)
        h = hashlib.sha256(Path(ontology).read_bytes())
        h.update(structure.read_bytes() if structure.exists() else b"")
        idx.fingerprint = h.hexdigest()[:12]
        idx.notes = {str(s): str(o) for s, o in g.subject_objects(RDFS.comment) if str(s).startswith(MET)}
        idx.met_terms = {str(s) for s in set(g.subjects()) if isinstance(s, URIRef) and str(s).startswith(MET)}
        for p in g.subjects(RDF.type, URIRef(SOSA + "ObservableProperty")):
            labels = [str(o) for o in g.objects(p, RDFS.label)] + [str(o) for o in g.objects(p, SKOS.altLabel)]
            unit = next((str(o) for o in g.objects(p, URIRef(MET + "canonicalUnit"))), None)
            note = next((str(o) for o in g.objects(p, URIRef(MET + "aggregationNote"))), "")
            kind = next((str(o) for o in sg.objects(p, URIRef(MET + "observedAs"))), None)
            aggs = {str(sg.value(a, SKOS.notation)) for a in sg.objects(p, URIRef(MET + "allowsAggregation"))}
            caveat = next((str(o) for o in sg.objects(p, URIRef(MET + "answerCaveat"))), "")
            idx.properties[str(p)] = PropertyInfo(str(p), labels, unit, kind, aggs, kind == MET + "AccumulatedObservation", caveat=caveat)
            if unit:
                idx.units.add(unit)
        for u, sym in sg.subject_objects(URIRef(MET + "symbol")):
            idx.unit_symbols[str(u)] = str(sym)
        direct: dict[str, set[str]] = {}
        for a, b in list(g.subject_objects(RDFS.subClassOf)) + list(sg.subject_objects(RDFS.subClassOf)):
            if isinstance(b, URIRef):                       # restrições (nós em branco) vão para value_restrictions
                direct.setdefault(str(a), set()).add(str(b))
        for c, r in sg.subject_objects(RDFS.subClassOf):
            if isinstance(r, BNode):
                on, allv = sg.value(r, OWL.onProperty), sg.value(r, OWL.allValuesFrom)
                if on is not None and allv is not None:
                    idx.value_restrictions[(str(c), str(on))] = str(allv)
        full = {str(c) for c in sg.subjects(URIRef(MET + "requiresFullContainment"), Literal(True))}
        for info in idx.properties.values():
            info.containment = bool(info.kind and (idx.closure(info.kind) | {info.kind}) & full)
        for c in direct:
            seen, stack = set(), list(direct[c])
            while stack:
                x = stack.pop()
                if x not in seen:
                    seen.add(x)
                    stack.extend(direct.get(x, ()))
            idx.superclasses[c] = seen
        idx.disjoint = {frozenset((str(a), str(b))) for gr in (g, sg) for a, b in gr.subject_objects(OWL.disjointWith)}
        incompat = URIRef(MET + "incompatibleWith")
        idx.check_disjoint = idx.disjoint | {frozenset((str(a), str(b))) for a, b in sg.subject_objects(incompat)}
        for p, d in sg.subject_objects(URIRef(MET + "alsoDomain")):
            idx.also_domain.setdefault(str(p), set()).add(str(d))
        xsd = "http://www.w3.org/2001/XMLSchema#"
        for gr, from_structure in ((g, False), (sg, True)):
            for p, d in gr.subject_objects(RDFS.domain):
                idx.domain[str(p)] = str(d)
                if from_structure:
                    idx.structure_props.add(str(p))
            for p, r in gr.subject_objects(RDFS.range):
                if not str(r).startswith(xsd):
                    idx.range_[str(p)] = str(r)
                if from_structure:
                    idx.structure_props.add(str(p))
        if not with_data:
            return idx
        dg = Graph().parse(data)
        idx.direct_types = {str(o) for o in dg.objects(None, RDF.type) if isinstance(o, URIRef)}
        # Perfil dos dados: a ontologia diz o que PODE existir; o grafo (ou, no Ontop, o mapeamento) diz o que ESTÁ populado.
        idx.data_predicates = {str(p) for p in dg.predicates()}
        idx.properties_with_data = {str(o) for o in dg.objects(None, URIRef(SOSA + "observedProperty"))} | \
                                   {str(o) for o in dg.objects(None, URIRef(MET + "forecastedProperty"))}
        days = [_parse_day(str(o)) for o in dg.objects(None, URIRef(TIME + "inXSDDateTime"))]
        days = [d for d in days if d]
        idx.coverage = (min(days), max(days)) if days else None
        for s in dg.subjects(RDF.type, URIRef(MET + "WeatherStation")):
            labels = [str(o) for o in dg.objects(s, RDFS.label)]
            idx.entities[str(s)] = labels
            idx.labels.update(labels)
        return idx

    @classmethod
    def from_ontop(cls, backend, obda: Path | None = None, ontology: Path | None = None, structure: Path | None = None,
                   timeout_s: float = 60.0) -> "OntologyIndex":
        """Índice do grafo REAL: a ontologia vem dos arquivos; estações, cobertura e grandezas com dados vêm do Ontop.

        `backend` é qualquer objeto com `select(consulta, timeout_s, max_rows)` (metqa.execution.store.OntopBackend). Falha de forma EXPLÍCITA se
        uma consulta falhar: um índice sem estações faria toda estação virar "desconhecida" e a pipeline recusaria tudo."""
        idx = cls.load(ontology=ontology, structure=structure, with_data=False)
        obda = obda or ROOT / "mapping" / "met.obda"
        if obda.exists():
            idx.with_profile_from_obda(obda)

        def ask(query: str) -> dict:
            r = backend.select(query, timeout_s=timeout_s, max_rows=10000)
            if not r.ok:
                raise RuntimeError(f"índice real: consulta ao grafo falhou ({r.error_kind}): {str(r.error)[:200]}")
            return r.results

        rdfs, sosa = str(RDFS), SOSA
        for b in ask(f"SELECT ?s ?l WHERE {{ ?s a <{MET}WeatherStation> ; <{rdfs}label> ?l }}")["results"]["bindings"]:
            idx.entities.setdefault(b["s"]["value"], []).append(b["l"]["value"])
            idx.labels.add(b["l"]["value"])
        if not idx.entities:
            raise RuntimeError("índice real: o grafo não tem nenhuma estação")
        cov = ask(f"SELECT (MIN(?d) AS ?a) (MAX(?d) AS ?b) WHERE {{ ?r a <{MET}WeatherReport> ; <{MET}localDate> ?d }}")["results"]["bindings"]
        if cov and "a" in cov[0]:
            idx.coverage = (date.fromisoformat(cov[0]["a"]["value"]), date.fromisoformat(cov[0]["b"]["value"]))
        idx.properties_with_data = {p for p in idx.properties
                                    if ask(f"ASK {{ ?o <{sosa}observedProperty> <{p}> }}").get("boolean")}
        return idx

    def closure(self, cls_iri: str) -> set[str]:
        return {cls_iri} | self.superclasses.get(cls_iri, set())

    def with_profile_from_obda(self, obda: Path) -> "OntologyIndex":
        """Perfil dos dados do grafo REAL: as propriedades e classes que o mapeamento do Ontop efetivamente produz.
        (No grafo sintético o perfil vem dos dados; no Ontop, quem diz o que está populado é o mapeamento.)"""
        preds, types = obda_profile(obda)
        self.data_predicates, self.direct_types = preds, types
        self.attributes = obda_observation_attributes(obda)
        return self

    def link_properties(self, question: str) -> dict[str, str]:
        """Grandezas que a PERGUNTA nomeia pelos rótulos da ontologia (rdfs:label/skos:altLabel), sem LLM: IRI -> rótulo.
        Vale o rótulo mais longo ('temperatura do ponto de orvalho' vence 'temperatura'). Quando nada casa (sinônimos
        como 'choveu'), devolve vazio e a decisão fica com o LLM, validada pelas demais regras."""
        # Casa por palavras NORMALIZADAS (sem de/do/da e com o plural reduzido): 'direções de vento' é 'direção do vento'. Sem isso o
        # apelido genérico 'vento' (velocidade) ganhava e a pergunta sobre direção era fundamentada na grandeza errada (medido: RT12).
        q = _core_tokens(question)
        spans: list[tuple[int, int, str, str]] = []
        for iri, info in self.properties.items():
            for label in info.labels:
                n = _core_tokens(label)
                for i in range(len(q) - len(n) + 1 if n else 0):
                    if q[i:i + len(n)] == n:
                        spans.append((i, i + len(n), iri, label))
        found: dict[str, str] = {}
        for s, e, iri, label in spans:
            if not any(s2 <= s and e <= e2 and (e2 - s2) > (e - s) and i2 != iri for s2, e2, i2, _ in spans):
                found.setdefault(iri, label)
        return found

    def link_entities(self, question: str) -> dict[str, str]:
        """Estações que a PERGUNTA cita (por rótulo ou código), sem LLM: IRI -> trecho encontrado.
        É a verdade de referência para conferir as entidades da interpretação (omitidas ou inventadas)."""
        q, found = fold(question), {}
        for iri, labels in self.entities.items():
            code = iri.rsplit("/", 1)[-1]
            for name in [*labels, code]:
                n = fold(name)
                if n and re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", q):
                    found[iri] = name
                    break
        return found

    def is_known_iri(self, iri: str) -> bool:
        if iri.startswith(MET):
            return iri in self.met_terms
        if iri.startswith(STATION_NS):
            return iri in self.entities
        if iri.startswith(UNIT):
            return iri in self.units
        for ns, terms in EXTERNAL_TERMS.items():
            if iri.startswith(ns):
                return iri[len(ns):] in terms
        return any(iri.startswith(ns) for ns in FREE_NAMESPACES)

    def time_paths(self, shape: str) -> list[str]:
        """Caminhos até os valores de tempo de uma forma (time:Instant, time:Interval), derivados de domínio/imagem."""
        leaves: list[list[str]] = []

        def walk(cls: str, prefix: list[str]) -> None:
            for p in sorted(p for p, d in self.domain.items() if d == cls and p in self.structure_props):
                nxt = self.range_.get(p)
                if nxt:
                    walk(nxt, prefix + [p])
                else:
                    leaves.append(prefix + [p])
        walk(shape, [])
        return ["/".join(_short(p) for p in leaf) for leaf in leaves]

    def time_shape(self, prop_iri: str) -> str | None:
        """Forma do tempo da grandeza: allValuesFrom de sosa:phenomenonTime na classe de observação dela."""
        info = self.properties.get(prop_iri)
        if not info or not info.kind:
            return None
        for c in self.closure(info.kind):
            if (c, SOSA + "phenomenonTime") in self.value_restrictions:
                return self.value_restrictions[(c, SOSA + "phenomenonTime")]
        return None

    def _paths(self, start: str, goal: str, populated, max_hops: int = 3) -> list[str]:
        """Caminhos MAIS CURTOS entre duas classes pelas relações declaradas (domínio/imagem) e populadas no grafo,
        andando também no sentido inverso. Cada nó do caminho é um indivíduo diferente: por isso o caminho da estação até
        a observação passa por sosa:Sensor (ou pelo local), nunca por sosa:hasFeatureOfInterest apontando para a estação."""
        edges = [(p, self.domain[p], self.range_[p]) for p in sorted(set(self.domain) & set(self.range_))
                 if p not in GUIDE_ONLY and populated(p)]
        frontier: list[tuple[str, str]] = [(start, _short(start))]
        for _ in range(max_hops):
            nxt, found = [], []
            for node, text in frontier:
                reach = self.closure(node)
                for p, d, r in edges:
                    if d in reach:
                        nxt.append((r, f"{text} —{_short(p)}→ {_short(r)}"))
                    if r in reach:
                        nxt.append((d, f"{text} ←{_short(p)}— {_short(d)}"))
            found = [t for n, t in nxt if goal in self.closure(n) or n == goal]
            if found:
                return sorted(set(found))
            frontier = nxt
        return []

    def _disjointness_notes(self) -> list[str]:
        """Consequências das disjunções para as classes de domínio: 'met:WeatherStation é sosa:Platform, logo nunca é
        sosa:FeatureOfInterest' (e quais relações levam a essa outra classe)."""
        notes = []
        for cls in sorted(c for c in self.superclasses if c.startswith(MET)):
            closed = self.closure(cls)
            for pair in self.disjoint:
                mine = pair & closed
                if len(mine) != 1 or cls in mine:
                    continue                       # só a disjunção HERDADA ensina algo; a própria já está na lista acima
                other = next(iter(pair - mine))
                if other in closed:
                    continue
                via = sorted(_short(p) for p, r in self.range_.items() if r == other and p in self.structure_props)
                notes.append(f"- {_short(cls)} é {_short(next(iter(mine)))}, logo NUNCA é {_short(other)}"
                             + (f" (objeto de {', '.join(via)} não é {_short(cls)})" if via else ""))
        return notes

    def _ontology_context(self) -> str:
        lines = ["Relações do grafo (sujeito —propriedade→ objeto):"]
        populated = lambda p: not self.data_predicates or p in self.data_predicates      # só o que o grafo realmente tem
        for p in sorted(q for q in (set(self.domain) | set(self.range_)) - GUIDE_ONLY if populated(q)):
            lines.append(f"- {_short(self.domain[p]) if p in self.domain else '(qualquer)'} —{_short(p)}→ "
                         f"{_short(self.range_[p]) if p in self.range_ else 'literal'}")
        day = MET + "localDate"
        if day in self.domain and populated(day):
            # Forma por DIA LOCAL, aceita pelas regras (PERIOD_MISMATCH confere as datas contra o período). Só entra quando o grafo
            # a popula: o grafo sintético não tem met:localDate e o contexto dele não muda.
            lines.append(f"Dia local da observação: ?obs {_short(day)} ?d (xsd:date). {self.notes.get(day, '')} "
                         "Para período de DIAS inteiros use ?d (?d >= início e ?d <= fim, ou ?d = o dia, sem fuso); para um INSTANTE "
                         "('às 12h') use o caminho de tempo da grandeza. Não misture as duas formas na mesma consulta.")
        lines.append("Classes disjuntas (nunca tipe a mesma variável com as duas; previsão não é observação):")
        for pair in sorted(sorted(_short(c) for c in pr) for pr in self.disjoint):
            lines.append(f"- {pair[0]} ⟂ {pair[1]}")
        lines += self._disjointness_notes()
        paths = self._paths(MET + "WeatherStation", OBSERVATION, populated)
        if paths:
            lines.append("Caminhos da estação até a observação (derivados das relações; cada seta liga indivíduos diferentes):")
            lines += [f"- {p}" for p in paths]
            if len(paths) > 1:
                lines.append("(são caminhos ALTERNATIVOS até as mesmas observações: escolha UM; juntar os dois com UNION conta cada observação duas vezes)")
        lines.append("Grandezas observáveis. Cada uma diz a classe de observação que a registra, o caminho de tempo e as agregações permitidas:")
        for p in self.properties.values():
            shape = self.time_shape(p.iri)
            paths = self.time_paths(shape) if shape else []
            phen = _short(SOSA + "phenomenonTime")
            if shape and _short(shape) == "time:Interval":
                # uma variável distinta por extremo (nome derivado da propriedade: hasBeginning -> ?hasBeginning)
                ends = [f"{x} ?{x.split('/')[0].split(':')[-1]}" for x in paths]
                tempo = f"?obs {phen} ?iv . ?iv " + " ; ".join(ends)
            elif shape:
                tempo = f"?obs {phen}/{paths[0] if paths else '?'} ?t"
            else:
                tempo = "n/d"
            unidade = f"{self.unit_symbols.get(p.unit, '')} ({_short(p.unit)}, um recurso, não um texto)" if p.unit else "sem unidade"
            periodo = (" | período: só entram intervalos INTEIROS dentro do período (início >= começo do período e fim <= fim exclusivo)"
                       if p.containment else "")
            dados = ("" if not self.properties_with_data else
                     (" | dados: sim" if p.iri in self.properties_with_data else " | dados: NENHUMA observação neste grafo"))
            # atributos que SÓ algumas grandezas têm (do mapeamento): ex.: cabeceira da pista só no vento
            own = sorted(self.attributes.get(p.iri, set()) - OBS_COMMON - {"a"})
            proprios = (" | atributos próprios (?obs <atributo> ?x): " + "; ".join(
                _short(a) + (f" ({_ctx(self.notes[a], 110)})" if a in self.notes else "") for a in own)) if own else ""
            lines.append(f"- {_short(p.iri)}{dados} | rótulos: {', '.join(_ctx(l) for l in p.labels)} | unidade: {unidade} | "
                         f"observação: {_short(p.kind or '')} | tempo ({_short(shape or '')}): {tempo}{periodo} | "
                         f"agregações: {', '.join(sorted(p.aggregations))}{proprios}")
        lines += self._station_lines()
        return "\n".join(lines)

    def _station_lines(self) -> list[str]:
        """Estações para o prompt. No grafo real o rótulo é o próprio código ICAO: uma linha por estação só repetiria a sigla
        (178 linhas, ~0,9 mil tokens por etapa), então vão numa linha só. Com nomes distintos do código (grafo sintético) o formato
        não muda: os prompts v1–v4 medidos no sintético continuam idênticos."""
        if self.entities and all(labels == [iri.rsplit("/", 1)[-1]] for iri, labels in self.entities.items()):
            codes = ", ".join(sorted(iri.rsplit("/", 1)[-1] for iri in self.entities))
            return [f"Estações conhecidas ({len(self.entities)}; o rótulo é o próprio código e o IRI é st:CÓDIGO): {codes}"]
        return ["Estações conhecidas:"] + [f"- {iri.replace(STATION_NS, 'st:')} | {', '.join(_ctx(l) for l in labels)}"
                                           for iri, labels in sorted(self.entities.items())]

    def _structure_lines(self) -> list[str]:
        """Seção 'Forma do resultado' do contexto da etapa 1 (prompt v6): dimensões de agrupamento e atributos próprios, derivados
        do mapeamento. O dia local só entra se o grafo o popula."""
        day = MET + "localDate" in self.data_predicates
        dims = ["station (por estação)"] + (["year (por ano)", "month (por mês)", "day (por dia local)"] if day else []) + \
               ['value (a frequência de cada valor medido; só com aggregation "count")']
        lines = ["Forma do resultado (campos opcionais da interpretação):", "- group_by, dimensões: " + "; ".join(dims)]
        own = [(p, sorted(a for a in self.attributes.get(p.iri, set()) - OBS_COMMON - {"a"})) for p in self.properties.values()]
        own = [(p, a) for p, a in own if a]
        if own:
            lines.append("- atributos próprios (valem em group_by e, no superlativo, em attributes):")
            for p, attrs in own:
                lines.append(f"  - {_short(p.iri)}: " + "; ".join(
                    _short(a) + (f" ({_ctx(self.notes[a], 100)})" if a in self.notes else "") for a in attrs))
        lines.append('- order: {"by": "aggregate", "direction": "desc"|"asc", "limit": N} ordena os grupos (exige group_by)')
        return lines

    def prompt_context(self, style: str = "labels") -> str:
        """Fragmento da ontologia entregue ao LLM (só o necessário, não o grafo inteiro).

        style="labels": rótulos, unidade e se é acumulada (contexto mínimo; prompts v1/v2).
        style="ontology": acrescenta as RELAÇÕES do grafo e, por grandeza, classe de observação, caminho de tempo e
        agregações, tudo derivado dos axiomas de ontology/met-structure.ttl (nenhum texto escrito à mão)."""
        if style == "ontology":
            return self._ontology_context()
        if style == "interpret":
            return self.prompt_context("labels") + "\n" + "\n".join(self._structure_lines())
        lines = ["Propriedades observáveis (use o IRI completo ou met:Nome):"]
        for p in self.properties.values():
            lines.append(f"- {p.iri.replace(MET, 'met:')} | rótulos: {', '.join(_ctx(l) for l in p.labels)} | "
                         f"unidade: {(p.unit or '').replace(UNIT, 'unit:')} | "
                         f"{'acumulada (soma permitida)' if p.accumulated else 'instantânea (sem soma)'}")
        lines += self._station_lines()
        return "\n".join(lines)


def fold(text: str) -> str:
    """Minúsculas sem acento: 'Estação Serra Azul' e 'estacao serra azul' são o mesmo texto."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


_DROPPED_WORDS = {"de", "do", "da", "dos", "das"}


def _core_tokens(text: str) -> list[str]:
    """Palavras sem acento, sem preposições e com o plural reduzido ('direções de vento' -> ['direcao', 'vento'])."""
    out = []
    for w in re.findall(r"[a-z0-9]+", fold(text)):
        if w in _DROPPED_WORDS:
            continue
        if w.endswith("oes") or w.endswith("aes"):
            w = w[:-3] + "ao"
        elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
            w = w[:-1]
        out.append(w)
    return out


def _parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _obda_statements(obda: Path):
    """(sujeito, [(predicado, objeto), ...]) de cada declaração das linhas `target` de um mapeamento .obda, com prefixos expandidos
    nos predicados e nos objetos de `a`/`observedProperty` (o sujeito fica como no arquivo, ex.: ':obs/air_temp/{sigla}/{tmin}/{seq}')."""
    text = Path(obda).read_text(encoding="utf-8")
    prefixes = {m.group(1): m.group(2) for m in re.finditer(r"^([A-Za-z0-9_]*):\t+<?([^\s>]+)>?\s*$", text, re.M)}
    expand_pn = lambda pn: prefixes[pn.split(":", 1)[0]] + pn.split(":", 1)[1] if pn.split(":", 1)[0] in prefixes else pn
    for m in re.finditer(r"^target\t+(.*)$", text, re.M):
        for stmt in re.split(r"\s\.\s", m.group(1)):
            tokens = re.findall(r"""\{[^}]*\}(?:\^\^\S+)?|"[^"]*"(?:\^\^\S+)?|\S+""", stmt)
            # sujeito, depois pares (predicado objeto) separados por ';'
            seq, cur = [], []
            for tok in tokens[1:]:
                if tok in (";", ","):
                    if tok == ";":
                        seq.append(cur)
                        cur = []
                    continue
                cur.append(tok)
            seq.append(cur)
            pairs = [("a" if pair[0] == "a" else expand_pn(pair[0]), expand_pn(pair[1].rstrip(";.")))
                     for pair in seq if len(pair) >= 2]
            if tokens and pairs:
                yield tokens[0], pairs


def obda_profile(obda: Path) -> tuple[set[str], set[str]]:
    """(propriedades, classes) que as linhas `target` de um mapeamento .obda produzem."""
    preds: set[str] = set()
    types: set[str] = set()
    for _, pairs in _obda_statements(obda):
        for pred, obj in pairs:
            (types if pred == "a" else preds).add(obj if pred == "a" else pred)
    return preds, types


# Predicados que TODA observação tem; o que sobra, por grandeza, são os atributos próprios dela (ex.: cabeceira só no vento).
OBS_COMMON = ({SOSA + t for t in ("observedProperty", "madeBySensor", "hasFeatureOfInterest", "phenomenonTime", "resultTime", "hasResult")}
              | {MET + t for t in ("localDate", "localHour", "localWeekday", "inReport", "multipleReadings", "sourceFile", "sourceRow")})


def obda_observation_attributes(obda: Path) -> dict[str, set[str]]:
    """grandeza (IRI) -> predicados que as observações dela têm no mapeamento. Liga o sujeito ':obs/<nome>/…' à grandeza pelo
    mapeamento principal (`sosa:observedProperty`) e junta os mapeamentos extras do mesmo sujeito (ex.: obs_wind_speed_runway)."""
    stmts = list(_obda_statements(obda))
    subj_name = lambda subj: (re.match(r":obs/([A-Za-z0-9_]+)/", subj) or [None, None])[1]
    prop_of = {subj_name(subj): obj for subj, pairs in stmts for pred, obj in pairs
               if pred == SOSA + "observedProperty" and subj_name(subj)}
    out: dict[str, set[str]] = {p: set() for p in prop_of.values()}
    for subj, pairs in stmts:
        name = subj_name(subj)
        if name in prop_of:
            out[prop_of[name]] |= {pred for pred, _ in pairs if pred != "a"}
    return out



def convert_filter_value(value, unit: str | None, canonical: str | None):
    """Valor do filtro na unidade canônica da grandeza, ou None se a conversão não é conhecida (nada de "chutar" a escala: RD14/E14,
    "abaixo de 1 km" virou `< 1` em metros). Sem unidade = já canônica. Fatores: o catálogo de grandezas (ontology/catalog.py)."""
    from decimal import Decimal

    from ontology.catalog import convert
    if not unit or not canonical:
        return Decimal(str(value))
    return convert(value, expand(unit), expand(canonical))


def _short(iri: str) -> str:
    for pfx, ns in PREFIX_MAP.items():
        if iri.startswith(ns):
            return f"{pfx}:{iri[len(ns):]}"
    return iri
