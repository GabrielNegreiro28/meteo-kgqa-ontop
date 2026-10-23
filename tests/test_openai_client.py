"""Adaptador OpenAI com a camada HTTP simulada: mapeamento de erros e sigilo da chave. Sem rede."""
import io
import json
import urllib.error

import pytest

from pipeline import openai_client as oc
from pipeline.llm import LLMTimeout, RateLimited, ResilientLLM

KEY = "chave-secreta-de-teste-1234567890"


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code, body="", headers=None):
    return urllib.error.HTTPError("https://x", code, "err", headers or {}, io.BytesIO(body.encode()))


def ok_payload(text='{"answer": "ok"}', finish="stop"):
    return json.dumps({"choices": [{"message": {"content": text}, "finish_reason": finish}],
                       "usage": {"prompt_tokens": 1000, "completion_tokens": 500}}).encode()


def client(**kw):
    return oc.OpenAIChatClient(KEY, "modelo-x", **kw)


def patch(monkeypatch, *events):
    calls = []
    it = iter(events)

    def fake(req, timeout=None):
        calls.append(json.loads(req.data))
        ev = next(it)
        if isinstance(ev, Exception):
            raise ev
        return FakeResp(ev)
    monkeypatch.setattr(oc.urllib.request, "urlopen", fake)
    return calls


def test_success_estimates_cost_and_never_sends_key_in_body(monkeypatch):
    calls = patch(monkeypatch, ok_payload())
    r = client(price_in_per_m=5, price_out_per_m=20).complete("answer", "s", "u", 600)
    assert r.text == '{"answer": "ok"}' and r.cost_usd == pytest.approx(0.015)
    assert KEY not in json.dumps(calls[0])
    assert calls[0]["max_completion_tokens"] == 4000          # folga para modelos com raciocínio


def test_length_finish_reason_is_reported(monkeypatch):
    patch(monkeypatch, ok_payload(finish="length"))
    assert client().complete("x", "s", "u", 10).finish_reason == "length"


def test_http_errors_are_mapped(monkeypatch):
    patch(monkeypatch, http_error(429, headers={"Retry-After": "7"}))
    with pytest.raises(RateLimited) as e:
        client().complete("x", "s", "u", 10)
    assert e.value.retry_after == 7
    patch(monkeypatch, http_error(503))
    with pytest.raises(LLMTimeout):
        client().complete("x", "s", "u", 10)
    patch(monkeypatch, urllib.error.URLError("sem rede"))
    with pytest.raises(LLMTimeout):
        client().complete("x", "s", "u", 10)


def test_auth_error_does_not_leak_the_key_and_is_not_retried(monkeypatch):
    calls = patch(monkeypatch, http_error(401, body=f"Incorrect API key provided: {KEY}"))
    with pytest.raises(oc.AuthError) as e:
        ResilientLLM(client(), sleep=lambda s: None).complete("x", "s", "u", 10)
    assert KEY not in str(e.value) and len(calls) == 1


def test_error_body_is_scrubbed_of_the_key(monkeypatch):
    patch(monkeypatch, http_error(400, body=f"bad request key={KEY}"))
    with pytest.raises(oc.RequestRejected) as e:
        client().complete("x", "s", "u", 10)
    assert KEY not in str(e.value)


def test_unsupported_param_is_dropped_and_recorded(monkeypatch):
    calls = patch(monkeypatch, http_error(400, body="Unsupported parameter: 'reasoning_effort'"), ok_payload())
    c = client(effort="low")
    assert c.complete("x", "s", "u", 10).text
    assert "reasoning_effort" in calls[0] and "reasoning_effort" not in calls[1]
    assert c.dropped_params == ["reasoning_effort"]


def test_env_file_parsing_and_environment_precedence(tmp_path, monkeypatch):
    f = tmp_path / "k.env"
    f.write_text(f"# c\nOPENAI_API_KEY={KEY}\nKGQA_MODEL=m1\nKGQA_EFFORT=low\n", encoding="utf-8")
    monkeypatch.setenv("KGQA_MODEL", "m2")
    c = oc.OpenAIChatClient.from_env(f)
    assert c.model == "m2" and c.effort == "low"
    with pytest.raises(oc.AuthError):
        oc.OpenAIChatClient("", "m")


def test_connection_reset_mid_read_is_a_retryable_timeout_not_a_crash(monkeypatch):
    """Falha real observada: ConnectionResetError no meio da leitura derrubou a execução inteira."""
    patch(monkeypatch, ConnectionResetError(10054, "conexão encerrada pelo host remoto"), ok_payload())
    sleeps = []
    out = ResilientLLM(client(), sleep=sleeps.append).complete("x", "s", "u", 10)
    assert out.text and len(sleeps) == 1


def test_incomplete_response_is_retryable(monkeypatch):
    import http.client
    patch(monkeypatch, http.client.IncompleteRead(b"par"), ok_payload())
    assert ResilientLLM(client(), sleep=lambda s: None).complete("x", "s", "u", 10).text


def test_free_text_stage_does_not_force_json_mode(monkeypatch):
    """Medido na 1ª campanha da v4: com response_format=json_object a etapa de texto livre devolvia JSON (o objeto de entrada),
    a saída era 'vazia' e cada resposta custava uma chamada de reparo a mais."""
    calls = patch(monkeypatch, ok_payload("texto livre"), ok_payload('{"a": 1}'))
    client().complete("answer", "s", "u", 100, json_mode=False)
    client().complete("interpret", "s", "u", 100)
    assert "response_format" not in calls[0] and calls[1]["response_format"] == {"type": "json_object"}
