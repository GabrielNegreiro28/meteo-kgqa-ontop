"""Execução SPARQL somente leitura, com limite de tempo e de linhas.

Backend inicial: rdflib em memória, executado em PROCESSO FILHO. Motivo: rdflib não tem
timeout de consulta; matar o processo é a única forma confiável de interromper uma consulta
cara. Custo: o filho recarrega o grafo a cada chamada (aceitável no protótipo, ~2,6 mil triplas).
Trocar por Oxigraph/Fuseki/GraphDB = implementar outro SparqlBackend com a mesma assinatura.
"""
from __future__ import annotations

import multiprocessing as mp
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.parser import parseUpdate
from rdflib.plugins.sparql.parserutils import CompValue

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILES = [ROOT / "ontology" / "met.ttl", ROOT / "data" / "synthetic.nt"]

PREFIXES = """PREFIX met:  <https://example.org/kgqa-met/ontology#>
PREFIX d:    <https://example.org/kgqa-met/data/>
PREFIX st:   <https://example.org/kgqa-met/data/station/>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX time: <http://www.w3.org/2006/time#>
PREFIX qudt: <http://qudt.org/schema/qudt/>
PREFIX unit: <http://qudt.org/vocab/unit/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
PREFIX prov: <http://www.w3.org/ns/prov#>
"""

ALLOWED_FORMS = {"SelectQuery", "AskQuery"}
MAX_QUERY_CHARS = 6000                      # consulta gigante = custo de análise, aninhamento profundo e superfície de ataque
UNBOUNDED_PATH_MODS = {"*", "+"}            # p* e p+ percorrem o grafo sem limite; nenhuma pergunta suportada precisa deles
FORBIDDEN_NODES = {"ServiceGraphPattern"}   # SERVICE faria requisição de rede a partir do executor


class PolicyError(ValueError):
    pass


@dataclass
class ExecResult:
    ok: bool
    error_kind: str | None = None          # "syntax" | "policy" | "timeout" | "runtime"
    error: str | None = None
    results: dict[str, Any] | None = None  # SPARQL 1.1 JSON Results
    truncated: bool = False
    elapsed_ms: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


class SparqlBackend(Protocol):
    source_id: str
    def select(self, query: str, timeout_s: float = 10.0, max_rows: int = 1000) -> ExecResult: ...


def _walk(node: Any):
    if isinstance(node, CompValue):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _walk(v)
    elif isinstance(node, dict):
        for v in node.values():
            yield from _walk(v)


def check_policy(query: str) -> str:
    """Valida sintaxe e política. Retorna a forma da consulta. Levanta SyntaxError/PolicyError.

    Atualizações (INSERT/DELETE/LOAD/CLEAR...) não são aceitas pelo parser de *consultas*;
    se o texto for uma atualização SPARQL válida, é classificado como violação de política.
    """
    if len(query) > MAX_QUERY_CHARS:
        raise PolicyError(f"Consulta longa demais ({len(query)} > {MAX_QUERY_CHARS} caracteres).")
    try:
        pq = prepareQuery(query)
    except RecursionError as e:             # aninhamento profundo derruba o analisador: recusa, não propaga
        raise PolicyError("Consulta aninhada demais.") from e
    except Exception as e:  # pyparsing.ParseException e afins
        try:
            parseUpdate(query)
        except Exception:
            raise SyntaxError(str(e)) from e
        raise PolicyError("Operação de escrita (SPARQL Update) proibida.") from e
    form = pq.algebra.name
    if form not in ALLOWED_FORMS:
        raise PolicyError(f"Forma de consulta não permitida: {form}")
    if pq.algebra.get("datasetClause"):
        raise PolicyError("FROM/FROM NAMED não permitido (poderia carregar grafos remotos).")
    for n in _walk(pq.algebra):
        if n.name in FORBIDDEN_NODES:
            raise PolicyError("SERVICE não permitido.")
        for s_, p_, o_ in (n.get("triples") or []) if n.name == "BGP" else []:
            if _unbounded(p_):
                raise PolicyError("Caminho de comprimento ilimitado (* ou +) não permitido.")
    return form


def _unbounded(path: Any) -> bool:
    from rdflib.paths import MulPath, Path
    if isinstance(path, MulPath) and path.mod in UNBOUNDED_PATH_MODS:
        return True
    if isinstance(path, Path):
        return any(_unbounded(a) for a in (getattr(path, "args", None) or [getattr(path, "arg", None)]) if a is not None)
    return False


def term_to_json(t: Any) -> dict[str, str]:
    if isinstance(t, URIRef):
        return {"type": "uri", "value": str(t)}
    if isinstance(t, BNode):
        return {"type": "bnode", "value": str(t)}
    if isinstance(t, Literal):
        d = {"type": "literal", "value": str(t)}
        if t.language:
            d["xml:lang"] = t.language
        elif t.datatype:
            d["datatype"] = str(t.datatype)
        return d
    return {"type": "literal", "value": str(t)}


def _child(files: list[str], query: str, max_rows: int, q: mp.Queue) -> None:
    try:
        g = Graph()
        for f in files:
            g.parse(f)
        t0 = time.perf_counter()
        res = g.query(query)
        if res.type == "ASK":
            q.put({"ok": True, "results": {"head": {}, "boolean": bool(res.askAnswer)},
                   "truncated": False, "elapsed_ms": (time.perf_counter() - t0) * 1000})
            return
        vars_ = [str(v) for v in res.vars]
        bindings, truncated = [], False
        for i, row in enumerate(res):
            if i >= max_rows:
                truncated = True
                break
            b = {}
            for v in vars_:
                val = row[v]
                if val is not None:   # variável não ligada (OPTIONAL) fica ausente, como na especificação
                    b[v] = term_to_json(val)
            bindings.append(b)
        q.put({"ok": True, "results": {"head": {"vars": vars_}, "results": {"bindings": bindings}},
               "truncated": truncated, "elapsed_ms": (time.perf_counter() - t0) * 1000})
    except Exception as e:
        q.put({"ok": False, "error_kind": "runtime", "error": f"{type(e).__name__}: {e}"})


class LocalRdflibBackend:
    def __init__(self, files: list[Path] | None = None, source_id: str = "kg:synthetic-met-v1"):
        self.files = [str(p) for p in (files or DEFAULT_FILES)]
        self.source_id = source_id

    def select(self, query: str, timeout_s: float = 10.0, max_rows: int = 1000) -> ExecResult:
        t0 = time.perf_counter()
        try:
            check_policy(query)
        except PolicyError as e:
            return ExecResult(False, "policy", str(e))
        except SyntaxError as e:
            return ExecResult(False, "syntax", str(e))
        ctx = mp.get_context("spawn")   # portátil (Windows/macOS/Linux)
        q: mp.Queue = ctx.Queue()
        p = ctx.Process(target=_child, args=(self.files, query, max_rows, q), daemon=True)
        p.start()
        # Espera o resultado distinguindo: resposta, morte do filho (erro) e estouro de tempo.
        deadline = time.monotonic() + timeout_s
        out = None
        while out is None:
            try:
                out = q.get(timeout=0.05)
            except Exception:
                if not p.is_alive():
                    try:
                        out = q.get(timeout=0.5)   # pode ter chegado logo antes de sair
                    except Exception:
                        return ExecResult(False, "runtime",
                                          f"Processo de execução terminou sem resposta (exitcode={p.exitcode}).",
                                          elapsed_ms=(time.perf_counter() - t0) * 1000)
                elif time.monotonic() > deadline:
                    p.kill()
                    p.join()
                    return ExecResult(False, "timeout", f"Consulta excedeu {timeout_s:.1f} s e foi interrompida.",
                                      elapsed_ms=(time.perf_counter() - t0) * 1000)
        p.join(timeout=2)
        total = (time.perf_counter() - t0) * 1000
        if not out["ok"]:
            return ExecResult(False, out["error_kind"], out["error"], elapsed_ms=total)
        return ExecResult(True, results=out["results"], truncated=out["truncated"], elapsed_ms=total,
                          extra={"query_ms": out["elapsed_ms"]})


# ---------------------------------------------------------------------------------------------
# Backend Ontop: grafo virtual sobre PostgreSQL, acessado pelo protocolo SPARQL (HTTP).
# ---------------------------------------------------------------------------------------------
import json as _json
import re as _re
import urllib.error as _uerr
import urllib.parse as _uparse
import urllib.request as _ureq

_LIMIT_RE = _re.compile(r"\bLIMIT\s+(\d+)\s*(OFFSET\s+\d+\s*)?(?:#[^\n]*)?$", _re.IGNORECASE)    # comentário depois do LIMIT não o esconde
_TRAILING_COMMENT_LINES = _re.compile(r"(?:\s*\n[ \t]*#[^\n]*)+\s*$")


def cap_rows(query: str, max_rows: int) -> str:
    """Acrescenta LIMIT max_rows+1 ao fim da consulta, se ela não tiver LIMIT de nível superior menor.

    Um LIMIT de nível superior só corta linhas do resultado final (depois de GROUP BY/ORDER BY);
    não muda o valor de nenhuma linha. Assim o servidor não materializa milhões de linhas e
    ainda dá para saber se houve truncamento (veio a linha N+1).
    """
    q = _TRAILING_COMMENT_LINES.sub("", query.rstrip()).rstrip().rstrip(";")
    m = _LIMIT_RE.search(q)
    if m and int(m.group(1)) <= max_rows + 1:
        return q
    if m:
        return q[: m.start()] + f"LIMIT {max_rows + 1}" + (f" {m.group(2)}" if m.group(2) else "")
    return q + f"\nLIMIT {max_rows + 1}"


@dataclass
class Reformulation:
    """O que o próprio motor diz de uma consulta ANTES de executá-la (Ontop em modo --dev, rota /ontop/reformulate).

    status: "ok"          o motor traduziu a consulta para SQL (em `sql`);
            "empty"       o motor provou que ela nunca devolve linhas (nenhuma combinação de tipos/relações do mapeamento a satisfaz);
            "rejected"    o motor não conseguiu traduzi-la (dialeto, sintaxe) ou demorou demais;
            "unavailable" a rota não existe (modo --dev desligado) ou o motor não respondeu: não dá para checar, não há veredito.
    """
    status: str
    sql: str | None = None
    plan: str | None = None
    detail: str | None = None
    elapsed_ms: float = 0.0


def parse_reformulation(body: str) -> tuple[str, str | None]:
    """(status, sql) do texto que /ontop/reformulate devolve: `ans1(vars)`, depois `EMPTY [...]` ou `CONSTRUCT …`, `NATIVE […]` e o SQL."""
    lines = body.strip().splitlines()
    if any(l.strip().startswith("EMPTY") for l in lines[:3]):
        return "empty", None
    for i, l in enumerate(lines):
        if l.strip().startswith("NATIVE"):
            return "ok", "\n".join(lines[i + 1:]).strip() or None
    return "ok", None


class OntopBackend:
    """Consulta o endpoint SPARQL do Ontop. O teto rígido de tempo fica no PostgreSQL (statement_timeout)."""

    def __init__(self, endpoint: str = "http://127.0.0.1:8080/sparql", source_id: str = "kg:ontop-met-real-v1"):
        self.endpoint = endpoint
        self.source_id = source_id

    def reformulate(self, query: str, timeout_s: float = 15.0) -> Reformulation:
        """Pede ao motor a reformulação (SQL) sem executar. Pega, numa só checagem, o que o `rdflib` aceita e o Ontop não
        (BIND com nome em uso, GROUP BY sem alias…) e as consultas vazias por construção (relação ao contrário, tipo errado).
        Custa ~5 ms. POST (a GET estoura o limite de URL em consulta longa)."""
        t0 = time.perf_counter()
        ms = lambda: (time.perf_counter() - t0) * 1000
        try:
            check_policy(query)
        except (PolicyError, SyntaxError) as e:
            return Reformulation("rejected", detail=str(e)[:200], elapsed_ms=ms())
        url = self.endpoint.rsplit("/", 1)[0] + "/ontop/reformulate"
        req = _ureq.Request(url, data=_uparse.urlencode({"query": query}).encode(), method="POST")
        try:
            with _ureq.urlopen(req, timeout=timeout_s) as resp:
                body = resp.read().decode("utf-8", "replace")
        except _uerr.HTTPError as e:
            if e.code == 404:
                return Reformulation("unavailable", detail="rota /ontop/reformulate ausente (Ontop sem --dev)", elapsed_ms=ms())
            return Reformulation("rejected", detail=f"o motor recusou a consulta (HTTP {e.code})", elapsed_ms=ms())
        except TimeoutError:
            return Reformulation("rejected", detail=f"o motor levou mais de {timeout_s:.0f} s só para traduzir a consulta", elapsed_ms=ms())
        except (_uerr.URLError, ConnectionError, OSError) as e:
            if isinstance(getattr(e, "reason", None), TimeoutError):
                return Reformulation("rejected", detail=f"o motor levou mais de {timeout_s:.0f} s só para traduzir a consulta", elapsed_ms=ms())
            return Reformulation("unavailable", detail="motor inacessível", elapsed_ms=ms())
        status, sql = parse_reformulation(body)
        return Reformulation(status, sql=sql, plan=body[:4000], elapsed_ms=ms())

    def select(self, query: str, timeout_s: float = 30.0, max_rows: int = 1000) -> ExecResult:
        t0 = time.perf_counter()
        try:
            form = check_policy(query)
        except PolicyError as e:
            return ExecResult(False, "policy", str(e))
        except SyntaxError as e:
            return ExecResult(False, "syntax", str(e))
        sent = cap_rows(query, max_rows) if form == "SelectQuery" else query
        data = _uparse.urlencode({"query": sent, "timeout": str(int(max(1, timeout_s)))}).encode()
        req = _ureq.Request(self.endpoint, data=data, method="POST",
                            headers={"Accept": "application/sparql-results+json",
                                     "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with _ureq.urlopen(req, timeout=timeout_s) as resp:
                payload = _json.loads(resp.read().decode("utf-8"))
        except TimeoutError:
            return ExecResult(False, "timeout", f"Consulta excedeu {timeout_s:.1f} s.",
                              elapsed_ms=(time.perf_counter() - t0) * 1000)
        except _uerr.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:800]
            kind = "timeout" if "timeout" in body.lower() or "canceling statement" in body else "runtime"
            return ExecResult(False, kind, f"HTTP {e.code}: {body}", elapsed_ms=(time.perf_counter() - t0) * 1000)
        except (_uerr.URLError, ConnectionError) as e:
            if isinstance(getattr(e, "reason", None), TimeoutError):
                return ExecResult(False, "timeout", f"Consulta excedeu {timeout_s:.1f} s.",
                                  elapsed_ms=(time.perf_counter() - t0) * 1000)
            return ExecResult(False, "unavailable", f"Endpoint indisponível: {e}",
                              elapsed_ms=(time.perf_counter() - t0) * 1000)
        total = (time.perf_counter() - t0) * 1000
        if "boolean" in payload:
            return ExecResult(True, results=payload, elapsed_ms=total)
        b = payload["results"]["bindings"]
        truncated = len(b) > max_rows
        payload["results"]["bindings"] = b[:max_rows]
        return ExecResult(True, results=payload, truncated=truncated, elapsed_ms=total,
                          extra={"query_sent": sent})
