"""Ciclo de evolução do EvoOntology ligado a esta pipeline (documento da arquitetura, §7.3 e §7.4 regras 4 e 5).

O núcleo (`evoontology.evolution.EvolutionSession`) é a máquina de estados: orçamento de rodadas congelado, Parent, Candidate, avaliação
registrada, publicação só por Accept. Aqui está o que o documento atribui ao PROJETO:

  1. MINERAR as trajetórias (só as de construção) atrás de problemas recorrentes e ATRIBUÍ-LOS a uma camada (conteúdo, ferramenta ou
     esquema/formal). Só problema de conteúdo vira Candidate; o resto vira PROPOSTA para revisão humana (§7.4 regra 5, duas vias de mudança).
  2. Montar o CANDIDATE: um remendo pequeno e localizado (um sinônimo), com Evidência ligada às trajetórias que o sustentam.
  3. Passar pela PORTA de validação (semantics/gate.py: IRI, categoria BFO, SHACL e raciocinador sobre os axiomas, com amostra do grafo real).
  4. Avaliar Parent e Candidate NAS MESMAS CONDIÇÕES (mesmos casos, mesmo avaliador, mesmo orçamento): conjunto de validação congelado + regressão.
  5. Aceitar só com melhora reprodutível e nenhuma regressão; senão rejeitar e registrar, e a próxima rodada começa do Parent.

QUEM É O "AGENTE DE EVOLUÇÃO" AQUI: o minerador é DETERMINÍSTICO (regras abaixo), não um LLM. O documento prevê um agente que lê as trajetórias e
propõe o remendo; um LLM pode ocupar o lugar do minerador sem mudar nada do resto, pois tudo o que ele propõe passa pela mesma porta e pela
mesma avaliação. O avaliador padrão (semantics/resolution.py) também é determinístico e mede o reconhecimento da grandeza, não a resposta final.
"""
from __future__ import annotations

import copy
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from evoontology.evolution.session import EvolutionSession
from evoontology.ontology.store import SemanticStore
from evoontology.trajectory.trajectory import TrajectoryStore

from metqa.knowledge.index import expand, fold

from .gate import validate_candidate
from .resolution import ResolutionAdapter

HELD_OUT = {"validation", "heldout", "test", "eval"}          # "eval": trilhas de medição (eval/run_independent), nunca mineradas
CONTENT, TOOL, FORMAL = "content", "tool", "formal"
# achados do verificador que NÃO se corrigem com conteúdo da camada semântica: defeito da ferramenta (prompt/regras) ou da ontologia formal
TOOL_FINDINGS = {"BAD_SCHEMA", "INVALID_OUTPUT", "PERIOD_MISMATCH", "FILTER_MISSING", "AGGREGATION_MISMATCH", "MISSING_COUNT", "SYNTAX_ERROR"}
FORMAL_FINDINGS = {"UNKNOWN_IRI", "TYPE_CLASH", "UNKNOWN_PROPERTY", "ATTRIBUTE_NOT_AVAILABLE", "DIMENSION_WITHOUT_DATA"}


@dataclass
class Hypothesis:
    id: str
    layer: str                       # content | tool | formal
    kind: str                        # add_alias
    term_id: str = ""
    alias: str = ""
    support: int = 0
    task_ids: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass
class Proposal:
    """Mudança que NÃO é conteúdo da camada semântica: vai para revisão humana (§13), nunca é aplicada automaticamente."""
    id: str
    layer: str
    finding: str
    support: int
    task_ids: list[str]
    rationale: str


# vocabulário de CONSULTA (limiar, recorte do período, parte do dia, mês, cálculo), não de grandeza: nunca vira sinônimo
FUNCTIONAL_PHRASES = (
    "acima de abaixo de maior que menor que superior a inferior a passou de passa de passaram de ultrapassou excedeu excede superou",
    "semestre trimestre bimestre quinzena semana verao inverno primavera outono inicio fim final metade ate desde entre a partir primeiro ultimo",
    "durante o dia durante a noite durante a madrugada de noite a noite de madrugada pela manha pela tarde de manha a tarde diurno noturno",
    "janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro")
AGG_CUES = {"avg": ("media", "medio", "medias", "medios"), "max": ("maxim", "maior", "mais alt", "mais quente", "pico"),
            "min": ("minim", "menor", "mais baix", "mais frio"), "sum": ("total", "soma", "somat"),
            "count": ("quantas", "quantos", "numero de", "contagem")}


def _functional_words() -> frozenset[str]:
    """Palavras que a PIPELINE já interpreta por regra (agregação, limiar, recorte de tempo, parte do dia, mês) ou que são vocabulário de consulta.
    Nenhuma é sinônimo de grandeza: "acima" aparece em toda pergunta com limiar e levaria à grandeza que calhou de vir junto."""
    import re

    from .ground import QUERY_WORDS, STOPWORDS
    sources = [*FUNCTIONAL_PHRASES, *(w for words in AGG_CUES.values() for w in words)]
    extra = {"observacao", "observacoes", "observado", "observados", "boletim", "boletins", "dados", "hora", "horas", "vezes", "leitura", "leituras"}
    return frozenset(w for s in sources for w in re.findall(r"[a-z]{3,}", fold(s))) | {fold(w) for w in QUERY_WORDS | STOPWORDS} | extra


def trusted(t: dict[str, Any]) -> bool:
    """Trajetória em que se pode confiar para ensinar um sinônimo: respondeu, sem correção do usuário, e a avaliação (se houve) conferiu."""
    ev = t.get("evaluation") or {}
    sig = t.get("signals") or {}
    # corrigida e depois CONFIRMADA pelo usuário (virou exemplo verificado) é a interpretação mais confiável que há
    return (t.get("pipeline_status") == "answered" and (sig.get("verified_by_user") or not sig.get("user_corrections"))
            and ev.get("result_match") is not False and ev.get("status_ok") is not False)


def _interpreted_properties(t: dict[str, Any]) -> list[str]:
    for call in reversed(t.get("native_tool_calls", [])):
        if call.get("tool") == "interpret" and isinstance(call.get("result"), dict):
            interp = call["result"].get("interpretation") or {}
            props = interp.get("properties") if isinstance(interp, dict) else None
            if isinstance(props, list):
                return [p for p in props if isinstance(p, str)]
    return []


def construction_trajectories(workspace: str | Path) -> list[dict[str, Any]]:
    return [t for t in TrajectoryStore(workspace)._all() if t.get("split") not in HELD_OUT]


def mine(workspace: str | Path, version: str, *, min_support: int = 2, is_trusted: Callable[[dict], bool] = trusted
         ) -> tuple[list[Hypothesis], list[Proposal]]:
    """Problemas recorrentes das trajetórias de CONSTRUÇÃO, atribuídos a uma camada.

    Conteúdo: uma palavra da pergunta que nenhum Termo cobriu (`signals.semantics.uncovered`), repetida em >= `min_support` trajetórias
    confiáveis que terminaram na MESMA grandeza, vira sinônimo dessa grandeza. A mesma palavra levando a grandezas diferentes é ambiguidade real
    (não vira sinônimo) e uma palavra que já é nome ou sinônimo de outro Termo é conflito (idem).
    Ferramenta/formal: achados do verificador que se repetem viram propostas."""
    _, records = SemanticStore.load_records(workspace, version=version)
    terms = {t["iri"]: t for t in records["terms"] if t.get("iri")}
    known = {fold(x) for t in records["terms"] for x in [t["name"], *t.get("aliases", [])]}
    # palavras que já fazem parte do nome de algum Termo ("relativa" em "umidade relativa do ar"): fragmento, não sinônimo
    known |= {w for phrase in list(known) for w in phrase.split()}
    known |= _functional_words()
    trajectories = construction_trajectories(workspace)

    everywhere: dict[str, set[str]] = defaultdict(set)         # palavra -> grandezas das PERGUNTAS em que ela aparece (qualquer trajetória, confiável ou não)
    for t in trajectories:
        iris = {expand(p) for p in _interpreted_properties(t)}
        for w in set(re.findall(r"\w+", fold(t.get("question", "")))):
            everywhere[w] |= iris
    by_word: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    surface: dict[str, str] = {}                                # a forma COMO FOI ESCRITA ("calorão"): o casamento do núcleo é sensível a acento
    findings: dict[str, list[str]] = defaultdict(list)
    unclear: dict[str, list[str]] = defaultdict(list)          # palavra sem cobertura -> perguntas que terminaram em esclarecimento
    for t in trajectories:
        sig = t.get("signals") or {}
        for code in sig.get("verifier_findings", []):
            findings[code].append(t["task_id"])
        if sig.get("clarification"):
            for w in (sig.get("semantics") or {}).get("uncovered", []):
                if fold(w) not in known:
                    unclear[fold(w)].append(t["task_id"])
        if not is_trusted(t):
            continue
        iris = [expand(p) for p in _interpreted_properties(t)]
        if len(set(iris)) != 1 or iris[0] not in terms:
            continue                                          # a palavra só pode ser atribuída a UMA grandeza
        for w in (sig.get("semantics") or {}).get("uncovered", []):
            by_word[fold(w)][iris[0]].append(t["task_id"])
            surface.setdefault(fold(w), w)

    hypotheses: list[Hypothesis] = []
    for word, targets in sorted(by_word.items()):
        if len(targets) != 1 or word in known:
            continue
        (iri, tasks), = targets.items()
        if everywhere.get(word, set()) - {iri}:
            continue                                          # a palavra aparece em perguntas de OUTRA grandeza: não é exclusiva desta
        support = len(set(tasks))
        if support < min_support:
            continue
        term = terms[iri]
        hypotheses.append(Hypothesis(id=f"alias.{word}.{term['id']}", layer=CONTENT, kind="add_alias", term_id=term["id"], alias=surface[word], support=support,
                                     task_ids=sorted(set(tasks)),
                                     rationale=f"'{word}' aparece sem cobertura em {support} trajetórias confiáveis que terminaram em {term['name']}: sinônimo."))
    hypotheses.sort(key=lambda h: (-h.support, h.id))

    proposals: list[Proposal] = []
    for code, tasks in sorted(findings.items()):
        support = len(set(tasks))
        if support < min_support or code not in TOOL_FINDINGS | FORMAL_FINDINGS:
            continue
        layer = FORMAL if code in FORMAL_FINDINGS else TOOL
        proposals.append(Proposal(id=f"proposal.{layer}.{code}", layer=layer, finding=code, support=support, task_ids=sorted(set(tasks)),
                                  rationale=("A ontologia formal pode estar incompleta ou errada" if layer == FORMAL else
                                             "O prompt, as regras ou a descrição da ferramenta podem estar causando o achado")
                                  + f" ({code} em {support} trajetórias). Não é conteúdo da camada semântica: exige revisão humana."))
    for word, tasks in sorted(unclear.items()):
        support = len(set(tasks))
        if support >= min_support:                              # sem grandeza confirmada, não dá para atribuir: revisão humana
            proposals.append(Proposal(id=f"proposal.{CONTENT}.UNCOVERED_IN_CLARIFICATION.{word}", layer=CONTENT,
                                      finding="UNCOVERED_IN_CLARIFICATION", support=support, task_ids=sorted(set(tasks)),
                                      rationale=f"'{word}' não tem Termo e aparece em {support} perguntas que pediram esclarecimento: "
                                                "candidata a sinônimo ou a Termo novo, sem grandeza confirmada (exige revisão humana)."))
    return hypotheses, proposals


def write_proposals(workspace: str | Path, proposals: list[Proposal]) -> Path | None:
    """Via 2 de mudança (§7.4 regra 5): o que alteraria a camada formal ou a ferramenta vira PROPOSTA para revisão, nunca remendo automático."""
    if not proposals:
        return None
    path = Path(workspace) / "proposals"
    path.mkdir(parents=True, exist_ok=True)
    out = path / "pending.json"
    out.write_text(json.dumps([asdict(p) for p in proposals], ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def apply(records: dict[str, list], h: Hypothesis) -> dict[str, list]:
    """O remendo: acrescenta o sinônimo ao Termo e uma Evidência que aponta para as trajetórias que o sustentam."""
    out = copy.deepcopy(records)
    term = next(t for t in out["terms"] if t["id"] == h.term_id)
    for variant in dict.fromkeys([h.alias, fold(h.alias)]):
        if variant not in term["aliases"]:
            term["aliases"].append(variant)
    ev_id = "ev.evolve." + h.id.replace(".", "_")
    term.setdefault("evidence", []).append(ev_id)
    out["evidence"].append({"id": ev_id, "source": "semantics.evolve (trajetórias de construção)", "query": "",
                            "validation_method": f"minerado: {h.support} trajetórias confiáveis ({', '.join(h.task_ids[:5])})",
                            "timestamp": "", "result": h.rationale})
    return out


def _gate_input(parent: dict, cand: dict, regression: bool) -> dict[str, Any]:
    p = {c["id"]: c["score"] for c in parent["cases"]}
    c = {c["id"]: c["score"] for c in cand["cases"]}
    ids = sorted(p)
    return {"protocol": "ground_truth", "case_ids": ids, "parent_scores": [p[i] for i in ids], "candidate_scores": [c[i] for i in ids],
            "unacceptable_regressions": regression}


def run_evolution(workspace: str | Path, parent: str, validation: ResolutionAdapter, regression: ResolutionAdapter | None = None, *,
                  max_rounds: int = 3, min_support: int = 2, abox=None, require_reasoner: bool = False) -> dict[str, Any]:
    """Uma execução do ciclo: minera, e para cada hipótese de CONTEÚDO (uma por rodada, do maior suporte ao menor) monta o Candidate, passa pela
    porta, avalia Parent x Candidate e aceita ou rejeita. Para na primeira aceitação, quando as hipóteses acabam ou o orçamento de rodadas
    acaba. Devolve um resumo; o estado completo está em `<workspace>/evolution/run_N/`."""
    workspace = Path(workspace)
    hypotheses, proposals = mine(workspace, parent, min_support=min_support)
    proposals_file = write_proposals(workspace, proposals)
    if not hypotheses:                                         # o núcleo não deixa terminar uma run sem tentar: sem hipótese, nem se abre
        return {"run_id": None, "hypotheses": 0, "proposals": len(proposals), "proposals_file": str(proposals_file) if proposals_file else None,
                "rounds": [], "accepted_version": None, "note": "sem hipóteses de conteúdo com suporte: nada a evoluir"}
    session = EvolutionSession(workspace)
    session.start_run(parent, adapter="semantics.resolution", max_rounds=max_rounds, acceptance={"protocol": "ground_truth"})
    session.confirm_trajectory_sources([{"path": str(workspace / "trajectories"), "scope": "construction", "purpose": "mineração de sinônimos"}])
    summary: dict[str, Any] = {"run_id": session.run_id, "hypotheses": len(hypotheses), "proposals": len(proposals),
                               "proposals_file": str(proposals_file) if proposals_file else None, "rounds": [], "accepted_version": None}
    parent_val = validation.evaluate(parent)
    parent_reg = regression.evaluate(parent) if regression else None
    for h in hypotheses:
        try:
            n = session.begin_round(h.rationale, f"cand_{session.run_id}_r{session.run['round'] + 1}")
        except Exception as e:                                 # orçamento esgotado: o núcleo já marcou a run como incompleta
            summary["stopped"] = type(e).__name__
            break
        cand = session.run["current_candidate"]
        _, records = SemanticStore.load_records(workspace, version=parent)
        SemanticStore.save_version(workspace, cand, apply(records, h))
        gate = validate_candidate(workspace, cand, abox=abox, require_reasoner=require_reasoner)
        entry: dict[str, Any] = {"round": n, "candidate": cand, "hypothesis": h.id, "gate": gate["passed"], "reasoner": gate["reasoner"]}
        if not gate["passed"]:
            session.record_round(decision="reject", metrics={"gate_errors": gate["errors"]}, notes="reprovado na porta de validação, não foi avaliado")
            entry.update(decision="reject", reason="gate", errors=gate["errors"])
            summary["rounds"].append(entry)
            continue
        cand_val = validation.evaluate(cand)
        cand_reg = regression.evaluate(cand) if regression else None
        regress = any(c["score"] < p["score"] for c, p in zip(cand_val["cases"], parent_val["cases"])) or (
            cand_reg is not None and any(c["score"] < p["score"] for c, p in zip(cand_reg["cases"], parent_reg["cases"])))
        gi = _gate_input(parent_val, cand_val, regress)
        session.record_evaluation(parent, parent_val, role="parent")
        session.record_evaluation(cand, {**cand_val, "gate_input": gi}, role="candidate")
        mean_p, mean_c = parent_val["metrics"]["mean_score"], cand_val["metrics"]["mean_score"]
        entry.update(parent_score=mean_p, candidate_score=mean_c, regression=regress)
        if mean_c > mean_p and not regress:
            version = session.accept()
            entry.update(decision="accept", version=version)
            summary.update(accepted_version=version)
            summary["rounds"].append(entry)
            break
        session.record_round(decision="reject", metrics={"parent": mean_p, "candidate": mean_c, "regression": regress},
                             notes="sem melhora estrita na validação congelada" if not regress else "regressão em caso que o Parent acertava")
        entry.update(decision="reject", reason="regression" if regress else "no_gain")
        summary["rounds"].append(entry)
    if summary["accepted_version"] is None and session.status == "running":
        for reason in ("budget_exhausted", "missing_data"):    # o núcleo só admite parar por motivo externo, e recusa se ainda cabe tentar
            try:
                session.mark_incomplete(reason)
                summary["incomplete"] = reason
                break
            except Exception:                                  # noqa: BLE001 — EvolutionError: a run continua e pode ser retomada
                continue
        else:
            summary["note"] = "run ainda aberta (retomável): restam rodadas ou rejeições a acumular"
    return summary
