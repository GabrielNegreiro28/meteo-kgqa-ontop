"""Fundamentação da pergunta na camada semântica (documento da arquitetura, §8, passos 1 a 3).

No documento, o interpretador chama `resolve_semantics` para cada frase importante. O cliente de LLM deste projeto é de uma
chamada só (sem laço de ferramentas), então quem chama é o pipeline, de forma determinística: os trechos da pergunta são
oferecidos à ferramenta e o que ela resolve vai ao LLM como `<semantica>`. É um desvio do desenho, registrado em DECISOES.md.

Duas propriedades que o resto do sistema assume:
  - o IRI que chega ao LLM já passou pela ontologia formal (Termo `unbound` nunca é mostrado);
  - o texto vem de uma camada que o agente de evolução altera, logo é DADO: passa por `textsafe.ctx` e nunca é instrução.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pipeline.textsafe import ctx
from pipeline.vocab import _short, expand, fold

from .facade import GroundedLayer

MAX_N = 6                       # "temperatura do ponto de orvalho" tem 5 palavras
MAX_NGRAMS = 150                # teto por pergunta (a pergunta tem no máximo 1000 caracteres)
BATCH = 5                       # limite de `resolve_semantics` por chamada
SHOWN_CONSTRAINTS = ("aggregation_note", "allowed_aggregations", "period_containment")
STOPWORDS = frozenset("""a o as os um uma uns umas de do da dos das em no na nos nas e ou que qual quais quanto quanta quantos
quantas foi fui era eram é são ao aos à às para por com sem entre sobre até se mais menos me te nos vos lhe onde quando como
houve teve tem têm ter há tinha todo toda todos todas""".split())


@dataclass
class Mention:
    phrase: str
    start: int                  # índice da primeira palavra
    end: int                    # índice da última palavra (inclusive)
    result: dict[str, Any]


@dataclass
class Grounding:
    resolved: list[Mention] = field(default_factory=list)       # Termos de grandeza observável, com IRI
    ambiguous: list[Mention] = field(default_factory=list)
    unbound: list[str] = field(default_factory=list)
    ignored: int = 0                                            # resolvidos que não são grandeza (estação, boletim…)
    uncovered: list[str] = field(default_factory=list)          # palavras de conteúdo que nenhum Termo cobriu: candidatas a sinônimo


# Palavras que toda pergunta do domínio tem e que não são candidatas a sinônimo de grandeza nenhuma.
QUERY_WORDS = frozenset("""qual quais foi foram quanto quanta quantos quantas media medio maxima maximo minima minimo total soma
registrada registrado registrou registraram registro registros medicao medicoes leitura leituras entre ano anos mes meses dia dias valor
valores estacao estacoes aerodromo aerodromos aeroporto aeroportos maior menor mais menos cada todos todas teve tem tinha""".split())
_STATION_CODE = re.compile(r"s[bdiwn][a-z]{2}\d?")


def _is_candidate(word: str) -> bool:
    w = fold(word)
    return len(w) > 3 and w not in STOPWORDS and w not in QUERY_WORDS and not w.isdigit() and not _STATION_CODE.fullmatch(w)


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _exact(phrase: str, term: dict[str, Any]) -> bool:
    """O trecho É o nome ou um sinônimo do Termo. O casamento do núcleo é por subconjunto de palavras e ignora palavras de uma
    letra e a ordem: 'vento e a rajada' casaria com 'rajada de vento' e roubaria o 'vento' de 'velocidade do vento'."""
    return fold(phrase) in {fold(x) for x in [term["name"], *term["aliases"]]}


def _ngrams(words: list[str]) -> list[tuple[int, int]]:
    """(início, fim) dos trechos candidatos: nem começam nem terminam em palavra vazia, número ou letra solta."""
    ok = [len(w) > 1 and w not in STOPWORDS and not w.isdigit() for w in words]
    spans = [(i, j) for i in range(len(words)) if ok[i]
             for j in range(i, min(len(words), i + MAX_N)) if ok[j]]
    return sorted(spans, key=lambda s: (-(s[1] - s[0]), s[0]))[:MAX_NGRAMS]


class SemanticGrounder:
    def __init__(self, layer: GroundedLayer):
        self.layer = layer

    @property
    def version(self) -> str:
        return self.layer.version

    def ground(self, text: str) -> Grounding:
        words = _words(text)
        spans = _ngrams(words)
        phrases = [" ".join(words[i:j + 1]) for i, j in spans]
        found: dict[str, dict[str, Any]] = {}
        for k in range(0, len(phrases), BATCH):
            for r in self.layer.resolve(phrases[k:k + BATCH])["results"]:
                found[r["query"]] = r
        taken: set[int] = set()
        g = Grounding()
        for (i, j), phrase in zip(spans, phrases):           # mais longo primeiro: "ponto de orvalho" vence "orvalho"
            r = found.get(phrase)
            if not r or r["status"] == "unresolved" or taken & set(range(i, j + 1)):
                continue
            terms = [r["term"]] if r["status"] == "resolved" else [c["term"] for c in r["candidates"]]
            terms = [t for t in terms if _exact(phrase, t)]
            if not terms:
                continue                                     # casamento parcial não ocupa as palavras: 'umidade' ainda pode casar
            taken |= set(range(i, j + 1))
            bound = [t for t in terms if t.get("formal_status") == "bound"]
            g.unbound += [t["id"] for t in terms if t.get("formal_status") != "bound"]
            props = [t for t in bound if t["type"] == "observable_property"]
            if not props:
                g.ignored += 1
            elif r["status"] == "resolved":
                if not any(m.result["term"]["iri"] == r["term"]["iri"] for m in g.resolved):      # dois trechos, um Termo: mostra uma vez
                    g.resolved.append(Mention(phrase, i, j, r))
            else:
                g.ambiguous.append(Mention(phrase, i, j, {**r, "candidates": [c for c in r["candidates"] if c["term"] in props]}))
        g.resolved.sort(key=lambda m: m.start)
        g.ambiguous.sort(key=lambda m: m.start)
        g.uncovered = list(dict.fromkeys(w for i, w in enumerate(words) if i not in taken and _is_candidate(w)))
        return g

    def block(self, text: str) -> tuple[str, dict[str, Any]]:
        """(bloco `<semantica>` para o prompt, resumo para a trilha). Vazio se nada foi resolvido: o prompt não muda."""
        g = self.ground(text)
        info = {"layer": self.version, "resolved": [{"phrase": m.phrase, "iri": m.result["term"]["iri"]} for m in g.resolved],
                "ambiguous": [{"phrase": m.phrase, "iris": [c["term"]["iri"] for c in m.result["candidates"]]} for m in g.ambiguous],
                "unbound": sorted(set(g.unbound)), "ignored": g.ignored, "uncovered": g.uncovered}
        if not g.resolved and not g.ambiguous:
            return "", info
        lines = [f'<semantica camada="{ctx(self.version, 40)}">',
                 "Termos que a camada semântica reconheceu na pergunta. O IRI é o da ontologia formal; os avisos são cuidados de uso."]
        for m in g.resolved:
            t = m.result["term"]
            warns = [f"[{c['severity']}] {ctx(c['description'], 220)}" for c in m.result.get("constraints", [])
                     if any(c["id"].endswith("." + k) for k in SHOWN_CONSTRAINTS)]
            lines.append(f'- "{ctx(m.phrase, 60)}" = {_short(t["iri"])} | categoria BFO: {ctx(str(t["bfo_category"]), 40)} | '
                         f'{ctx(t["definition"], 200)}' + (" | " + " ".join(warns) if warns else ""))
        for m in g.ambiguous:
            lines.append(f'- "{ctx(m.phrase, 60)}" é ambígua entre: '
                         + ", ".join(_short(c["term"]["iri"]) for c in m.result["candidates"])
                         + " (se a consulta mudar conforme a leitura, peça esclarecimento)")
        lines.append("</semantica>\n")
        return "\n".join(lines), info

    def check(self, text: str, properties: list[str]) -> dict[str, Any]:
        """Sinal para a evolução (§13): a interpretação aceita concorda com o que a camada reconheceu na pergunta?
        Só registra; nenhuma regra barra por isso (não há medição de falso positivo)."""
        resolved = sorted({m.result["term"]["iri"] for m in self.ground(text).resolved})
        chosen = sorted({expand(p) for p in properties})
        agreement = "none" if not resolved else "agree" if set(resolved) <= set(chosen) else "disagree"
        return {"agreement": agreement, "resolved": [_short(i) for i in resolved], "chosen": [_short(i) for i in chosen]}
