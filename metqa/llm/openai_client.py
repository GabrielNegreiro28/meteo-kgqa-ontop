"""Adaptador do LLM para a API Chat Completions da OpenAI (sem dependências: urllib).

Segurança da credencial: a chave é lida do ambiente ou de um arquivo .env apenas no momento da construção,
fica só num atributo privado e vai exclusivamente no cabeçalho Authorization. Nunca entra em mensagens de
erro, logs ou relatórios.

Preço: o custo é uma ESTIMATIVA conservadora (US$ por milhão de tokens, configurável por KGQA_PRICE_IN_PER_M /
KGQA_PRICE_OUT_PER_M; padrão alto de propósito) usada só para o teto de gasto, não para faturamento.
"""
from __future__ import annotations

import http.client
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .client import LLMError, LLMResponse, LLMTimeout, RateLimited

DEFAULT_BASE = "https://api.openai.com/v1"


def load_env(path: str | Path | None) -> dict[str, str]:
    """Lê KEY=VALUE de um .env (comentários com #). Variáveis já presentes no ambiente têm precedência."""
    cfg: dict[str, str] = {}
    if path and Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    cfg.update({k: v for k, v in os.environ.items() if k.startswith(("OPENAI_", "KGQA_"))})
    return cfg


class AuthError(LLMError):
    kind = "auth_error"


class RequestRejected(LLMError):
    kind = "request_rejected"


class OpenAIChatClient:
    def __init__(self, api_key: str, model: str, *, effort: str | None = None, min_output_tokens: int = 4000,
                 price_in_per_m: float = 5.0, price_out_per_m: float = 20.0, timeout_s: float = 90.0,
                 base_url: str = DEFAULT_BASE):
        if not api_key:
            raise AuthError("OPENAI_API_KEY ausente")
        self.__key = api_key
        self.model, self.effort, self.min_output_tokens = model, effort, min_output_tokens
        self.price_in, self.price_out, self.timeout_s, self.base_url = price_in_per_m, price_out_per_m, timeout_s, base_url
        self.dropped_params: list[str] = []          # parâmetros que o modelo recusou (registrado, não silencioso)

    def __repr__(self) -> str:                       # nunca expõe a chave em logs, tracebacks ou depuração
        return f"OpenAIChatClient(model={self.model!r}, base_url={self.base_url!r})"

    def __getstate__(self):
        raise TypeError("OpenAIChatClient não pode ser serializado (contém credencial)")

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> "OpenAIChatClient":
        c = load_env(env_path)
        return cls(c.get("OPENAI_API_KEY", ""), c.get("KGQA_MODEL", ""), effort=c.get("KGQA_EFFORT") or None,
                   min_output_tokens=int(c.get("KGQA_MAX_OUTPUT_TOKENS", "4000")),
                   price_in_per_m=float(c.get("KGQA_PRICE_IN_PER_M", "5.0")),
                   price_out_per_m=float(c.get("KGQA_PRICE_OUT_PER_M", "20.0")))

    def complete(self, stage: str, system: str, user: str, max_tokens: int, json_mode: bool = True) -> LLMResponse:
        body = {"model": self.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                # modelos com raciocínio gastam tokens "invisíveis": sem folga, a saída vem cortada
                "max_completion_tokens": max(max_tokens, self.min_output_tokens)}
        if json_mode:                       # etapa de texto livre não pode forçar JSON: o modelo devolvia o objeto de entrada
            body["response_format"] = {"type": "json_object"}
        if self.effort:
            body["reasoning_effort"] = self.effort
        for _ in range(3):
            try:
                payload = self._post(body)
                break
            except RequestRejected as e:
                bad = next((p for p in ("reasoning_effort", "response_format") if p in body and p in str(e)), None)
                if not bad:
                    raise
                body.pop(bad)                      # o modelo não aceita o parâmetro: segue sem ele, mas registra
                self.dropped_params.append(bad)
        else:
            raise RequestRejected("requisição recusada repetidamente")
        choice = payload["choices"][0]
        usage = payload.get("usage", {})
        cost = (usage.get("prompt_tokens", 0) * self.price_in + usage.get("completion_tokens", 0) * self.price_out) / 1e6
        return LLMResponse(text=choice["message"].get("content") or "", finish_reason=choice.get("finish_reason", "stop"),
                           cost_usd=cost, usage={"in": usage.get("prompt_tokens", 0), "out": usage.get("completion_tokens", 0)})

    def _post(self, body: dict) -> dict:
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {self.__key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300].replace(self.__key, "***")
            if e.code == 429:
                raise RateLimited(float(e.headers.get("Retry-After", 0) or 0)) from None
            if e.code in (401, 403):
                raise AuthError(f"HTTP {e.code}: credencial recusada") from None
            if e.code in (408, 500, 502, 503, 504):
                raise LLMTimeout(f"HTTP {e.code}") from None
            raise RequestRejected(f"HTTP {e.code}: {detail}") from None
        except (OSError, http.client.HTTPException) as e:   # inclui ConnectionResetError, queda no meio da leitura, resposta incompleta
            raise LLMTimeout(f"rede: {type(e).__name__}") from None
