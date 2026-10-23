"""Registro persistente de gasto com o LLM.

Por que existe: o teto do orçamento era por execução (ResilientLLM.budget_usd). O `kgqa.env` fala em teto de gasto
ACUMULADO, e várias execuções somadas passaram dele sem que nenhuma regra visse. Aqui cada chamada é anexada a um arquivo
(JSON Lines) e o teto vale para a soma de tudo que já foi gasto. Passar do teto exige autorização explícita registrada.

O arquivo guarda só: data, etiqueta da execução, modelo, tokens e custo estimado. Nunca a chave, o prompt ou a resposta.
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from .llm import BudgetExceeded, LLMClient, LLMResponse


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def total(self) -> float:
        return round(sum(e.get("cost_usd", 0.0) for e in self.entries()), 6)

    def _append(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}, ensure_ascii=False) + "\n")

    def record(self, cost_usd: float, *, run: str, model: str = "", usage: dict | None = None, note: str = "") -> None:
        self._append({"run": run, "model": model, "usage": usage or {}, "cost_usd": round(cost_usd, 6), "note": note})

    @contextmanager
    def _lock(self, timeout_s: float = 10.0, stale_s: float = 30.0):
        """Exclusão mútua entre processos (arquivo de trava criado com O_EXCL): ler o total, decidir e anotar a reserva é uma operação só."""
        lock = self.path.with_suffix(self.path.suffix + ".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        while True:
            try:
                os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                break
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > stale_s:       # processo morto deixou a trava
                        lock.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.time() - t0 > timeout_s:
                    raise BudgetExceeded("ledger de gasto ocupado: não foi possível reservar o custo da chamada")
                time.sleep(0.02)
        try:
            yield
        finally:
            try:
                lock.unlink()
            except FileNotFoundError:
                pass

    def reserve(self, amount_usd: float, cap_usd: float, *, run: str, note: str = "") -> None:
        """Reserva o custo MÁXIMO da próxima chamada antes de fazê-la. Recusa se total + reserva alcançar o teto."""
        with self._lock():
            total, cap = self.total(), cap_usd + self.authorized_extra()
            if total + amount_usd >= cap:
                raise BudgetExceeded(f"teto acumulado de US$ {cap:.2f} atingido (gasto registrado: US$ {total:.2f}; "
                                     f"a próxima chamada pode custar até US$ {amount_usd:.3f})")
            self._append({"run": run, "model": "", "usage": {}, "cost_usd": round(amount_usd, 6), "note": f"reserva:{note}"})

    def authorize(self, extra_usd: float, *, by: str, reason: str) -> None:
        """Eleva o teto acumulado. Fica registrado quem autorizou e por quê (a autorização não é inferida)."""
        self._append({"authorization_usd": extra_usd, "by": by, "reason": reason})

    def authorized_extra(self) -> float:
        return round(sum(e.get("authorization_usd", 0.0) for e in self.entries()), 6)


class LedgerLLM:
    """Envolve um LLMClient: reserva o custo máximo da chamada antes de fazê-la, recusa se a soma alcançar o teto (base + autorizações) e
    ajusta a reserva ao custo real depois. Chamada que falha depois de enviada fica registrada com o custo da entrada (pode ter sido cobrada)."""

    def __init__(self, client: LLMClient, ledger: Ledger, *, base_cap_usd: float, run: str, model: str = ""):
        self.client, self.ledger, self.base_cap, self.run, self.model = client, ledger, base_cap_usd, run, model
        self.spent_usd = 0.0                                # desta execução

    @property
    def cap(self) -> float:
        return self.base_cap + self.ledger.authorized_extra()

    def _bounds(self, system: str, user: str, max_tokens: int) -> tuple[float, float]:
        """(custo da entrada, custo máximo) estimados com o preço do cliente. Cliente sem preço (teste) reserva 0."""
        p_in, p_out = getattr(self.client, "price_in", 0.0), getattr(self.client, "price_out", 0.0)
        tokens_in = (len(system) + len(user)) / 2.5 + 64            # 2,5 caracteres por token: acima do usual em português (estimativa por cima)
        return tokens_in * p_in / 1e6, (tokens_in * p_in + max_tokens * p_out) / 1e6

    def complete(self, stage: str, system: str, user: str, max_tokens: int, json_mode: bool = True) -> LLMResponse:
        cost_in, reserve = self._bounds(system, user, max_tokens)
        self.ledger.reserve(reserve, self.base_cap, run=self.run, note=stage)
        try:
            resp = self.client.complete(stage, system, user, max_tokens, **({} if json_mode else {"json_mode": False}))
        except BaseException:
            self.ledger._append({"run": self.run, "model": self.model, "usage": {}, "cost_usd": round(cost_in - reserve, 6), "note": f"falha:{stage}"})
            raise
        self.spent_usd += resp.cost_usd
        self.ledger.record(resp.cost_usd - reserve, run=self.run, model=self.model, usage=resp.usage, note=f"ajuste:{stage}")
        return resp
