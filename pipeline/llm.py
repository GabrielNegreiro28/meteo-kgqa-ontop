"""Camada de acesso ao LLM: interface mínima e proteção contra falhas de infraestrutura.

Falhas tratadas aqui (não são alucinação, são limites): rate limit, timeout, saída cortada por limite de
tokens, orçamento esgotado, provedor fora do ar (circuit breaker) e saída que não é JSON.
Nenhum provedor real é implementado: o estudo usa ScriptedLLM (falhas injetadas, custo zero) e um
adaptador de provedor entra atrás da mesma interface (LLMClient).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


class LLMError(Exception):
    kind = "llm_error"
    retryable = False


class RateLimited(LLMError):
    kind, retryable = "rate_limited", True

    def __init__(self, retry_after: float = 0.0):
        super().__init__(f"rate limit (retry_after={retry_after}s)")
        self.retry_after = retry_after


class LLMTimeout(LLMError):
    kind, retryable = "timeout", True


class OutputTruncated(LLMError):
    kind = "output_truncated"          # finish_reason == "length": a saída está cortada, nunca usar


class BudgetExceeded(LLMError):
    kind = "budget_exceeded"


class CircuitOpen(LLMError):
    kind = "circuit_open"


class InvalidOutput(LLMError):
    kind = "invalid_output"
    raw: str = ""                      # início da saída recusada, para diagnóstico


@dataclass
class LLMResponse:
    text: str
    finish_reason: str = "stop"        # "stop" | "length" | outros do provedor
    cost_usd: float = 0.0
    usage: dict[str, int] = field(default_factory=dict)


class LLMClient(Protocol):
    def complete(self, stage: str, system: str, user: str, max_tokens: int, json_mode: bool = True) -> LLMResponse: ...


class ScriptedLLM:
    """LLM roteirizado para testes e experimentos. Cada estágio recebe uma fila de respostas;
    um item pode ser texto, LLMResponse ou uma exceção (que é levantada)."""

    def __init__(self, script: dict[str, list[Any]]):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[dict[str, Any]] = []

    def complete(self, stage: str, system: str, user: str, max_tokens: int, json_mode: bool = True) -> LLMResponse:
        self.calls.append({"stage": stage, "user": user, "max_tokens": max_tokens, "json_mode": json_mode})
        queue = self.script.get(stage)
        if not queue:
            raise LLMError(f"roteiro esgotado para o estágio {stage!r}")
        item = queue.pop(0) if len(queue) > 1 else queue[0]       # a última resposta se repete
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, LLMResponse) else LLMResponse(text=item)


class ResilientLLM:
    """Retry com backoff, circuit breaker, orçamento e detecção de saída cortada."""

    def __init__(self, client: LLMClient, *, budget_usd: float = 5.0, max_attempts: int = 3,
                 base_delay: float = 1.0, failure_threshold: int = 3, cooldown_s: float = 30.0,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.client, self.budget_usd, self.max_attempts = client, budget_usd, max_attempts
        self.base_delay, self.failure_threshold, self.cooldown_s = base_delay, failure_threshold, cooldown_s
        self._sleep, self._clock = sleep, clock
        self.spent_usd = 0.0
        self._failures = 0
        self._opened_at: float | None = None

    def complete(self, stage: str, system: str, user: str, max_tokens: int, json_mode: bool = True) -> LLMResponse:
        if self.spent_usd >= self.budget_usd:
            raise BudgetExceeded(f"orçamento de US$ {self.budget_usd:.2f} esgotado")
        if self._opened_at is not None:
            if self._clock() - self._opened_at < self.cooldown_s:
                raise CircuitOpen("provedor suspenso após falhas consecutivas")
            self._opened_at = None                                  # meia-abertura: tenta de novo
        last: LLMError | None = None
        for attempt in range(self.max_attempts):
            try:
                # clientes antigos não conhecem json_mode: só o repassa quando é preciso desligá-lo
                resp = self.client.complete(stage, system, user, max_tokens, **({} if json_mode else {"json_mode": False}))
            except LLMError as e:
                if not e.retryable:
                    raise
                last = e
                self._register_failure()
                if self._opened_at is not None or attempt == self.max_attempts - 1:
                    break
                self._sleep(max(getattr(e, "retry_after", 0.0), self.base_delay * 2 ** attempt))
                continue
            self._failures = 0
            self.spent_usd += resp.cost_usd
            if resp.finish_reason == "length":
                raise OutputTruncated(f"saída do estágio {stage!r} cortada por limite de tokens ({max_tokens})")
            return resp
        raise last or LLMError("falha desconhecida")

    def _register_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = self._clock()


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.S)


MAX_JSON_DEPTH = 32       # as saídas legítimas do pipeline têm no máximo ~4 níveis


def _too_deep(text: str, limit: int = MAX_JSON_DEPTH) -> bool:
    """Profundidade de aninhamento acima do limite, contada sem recursão e ignorando o que está dentro de textos."""
    depth, in_str, esc = 0, False, False
    for ch in text:
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
            if depth > limit:
                return True
        elif ch in "]}":
            depth -= 1
    return False


def parse_json_object(text: str, allowed_keys: set[str]) -> dict[str, Any]:
    """JSON estrito: um objeto, sem chaves fora do esquema. Cercas ```json são o único ajuste aceito."""
    t = text.strip()
    m = _FENCE.match(t)
    if m:
        t = m.group(1)
    if _too_deep(t):                                  # limite explícito: o RecursionError do json.loads varia com a versão do Python
        raise InvalidOutput("saída JSON aninhada demais")
    try:
        obj = json.loads(t)
    except json.JSONDecodeError as e:
        raise InvalidOutput(f"saída não é JSON: {e.msg}") from e
    except RecursionError as e:                       # '[[[[…' profundo: não é erro do sistema, é saída inválida
        raise InvalidOutput("saída JSON aninhada demais") from e
    if not isinstance(obj, dict):
        raise InvalidOutput("saída não é um objeto JSON")
    extra = set(obj) - allowed_keys
    if extra:
        raise InvalidOutput(f"chaves fora do esquema: {sorted(extra)}")
    return obj
