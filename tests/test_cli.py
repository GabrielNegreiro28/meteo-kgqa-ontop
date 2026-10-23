"""Linha de comando (`python -m kgqa`): a montagem, a saída e as falhas, sem rede e sem gastar nada (LLM roteirizado, grafo sintético)."""
import argparse
import json

import pytest

from kgqa import __main__ as cli
from kgqa.contract import Status
from kgqa.store import LocalRdflibBackend
from pipeline.llm import ScriptedLLM
from tests.test_pipeline import INDEX, QS, T08_INTERP


def _args(**kw):
    base = dict(prompts="v7", confirm="never", budget=0.1, timeout=20.0, endpoint=None, show_query=False, json=False)
    return argparse.Namespace(**{**base, **kw})


def _runtime(llm):
    return LocalRdflibBackend(), INDEX, llm, None


def test_default_prompts_is_v7_and_help_does_not_need_network_or_secrets(capsys):
    assert cli.parser().parse_args(["pergunta"]).prompts == "v7"
    with pytest.raises(SystemExit):
        cli.parser().parse_args(["--help"])
    assert "OPENAI" not in capsys.readouterr().out.replace("OPENAI_API_KEY", "")      # só cita o nome da variável, nunca um valor


def test_a_question_is_answered_with_one_llm_call_and_rendered():
    question = QS["T08"]["question"]
    llm = ScriptedLLM({"interpret": [json.dumps(T08_INTERP)], "generate": ["{}"], "answer": ["x"]})
    res = cli.ask(question, _args(), _runtime(llm))
    # o grafo sintético não tem sensores nem a forma de tempo do grafo real, então a consulta montada pode voltar vazia: aqui vale o CAMINHO
    # (uma só chamada ao LLM, consulta montada por código, saída legível); o dado certo é conferido no teste com o Ontop, abaixo
    assert res.response.status in (Status.ANSWERED, Status.NO_RESULTS)
    assert {c["stage"] for c in llm.calls} == {"interpret"}              # v7: consulta montada e resposta redigida por código
    assert any(t["event"] == "compile_structured" for t in res.trace)
    text = cli.render(res, show_query=True)
    assert text.startswith("[") and "Consulta SPARQL" in text and "Procedência" in text


def test_unsupported_question_is_rendered_with_the_reason():
    llm = ScriptedLLM({"interpret": [json.dumps({"status": "unsupported", "reason": "Cidade não existe nos dados"})], "generate": ["{}"], "answer": ["x"]})
    res = cli.ask("Qual a temperatura em Campinas?", _args(), _runtime(llm))
    assert res.response.status == Status.UNSUPPORTED
    assert cli.render(res).startswith("[unsupported]")


def test_no_confirmation_is_asked_without_a_terminal(monkeypatch):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False, raising=False)
    assert cli.make_confirm("assumptions") is None
    assert cli.make_confirm("never") is None


def test_main_reports_what_is_missing_without_internal_detail(monkeypatch, capsys):
    def boom(args):
        raise ConnectionError("detalhe interno com http://127.0.0.1:8080 e chave")
    monkeypatch.setattr(cli, "build_runtime", boom)
    assert cli.main(["qualquer pergunta"]) == 1
    err = capsys.readouterr().err
    assert "ConnectionError" in err and "127.0.0.1" not in err and "chave" not in err


def test_main_without_question_prints_usage(capsys):
    assert cli.main([]) == 2


from datetime import date  # noqa: E402

from tests.test_real_pipeline import needs_duck, needs_ontop  # noqa: E402


@needs_ontop
@needs_duck
def test_cli_answers_a_threshold_count_correctly_on_the_real_graph():
    from eval import oracle_real
    from kgqa.store import OntopBackend
    from pipeline.vocab import OntologyIndex
    interp = {"status": "ok", "properties": ["met:Precipitation"], "entities": [{"text": "SBLO", "iri": "st:SBLO"}], "filters": [{"op": ">=", "value": 10, "unit": "unit:MilliM"}],
              "period": {"start": "2020-01-01", "end": "2020-12-31", "tz": "-03:00", "inclusive_end": True}, "aggregation": "count", "record_kind": "observation"}
    llm = ScriptedLLM({"interpret": [json.dumps(interp)], "generate": ["{}"], "answer": ["x"]})
    backend = OntopBackend()
    res = cli.ask("Em SBLO, quantas horas de 2020 acumularam pelo menos 10 mm de chuva?", _args(), (backend, OntologyIndex.from_ontop(backend), llm, None))
    assert res.response.status == Status.ANSWERED
    d = oracle_real.between(oracle_real.load("obs_precip", "SBLO"), date(2020, 1, 1), date(2020, 12, 31))
    n = int((d.value >= 10).sum())
    assert str(n) in cli.render(res)
    assert "leituras" in cli.render(res)                                   # a ressalva de que a contagem é de leituras acompanha a resposta
