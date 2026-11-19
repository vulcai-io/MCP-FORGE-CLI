"""
Dépense LLM : point d'accroche entre le moteur et celui qui paie.

Les trois sites d'appel (enrichissement, raffinement, évaluation) appellent
`before_call` avant chaque requête et `after_call` après, avec les tokens
réellement consommés. Sans garde installée (CLI, pipeline local), rien n'est
compté ni refusé. L'API installe une garde (api/services/llm_spend.py) qui
inscrit chaque dépense et refuse au-delà du budget journalier.

Compte (2026-11-15, plafond par compte, phase 1) : l'appelant déclare le
compte qui paie avec `with account(tenant_id):`. La garde réserve alors le
coût maximal de l'appel sous le verrou du compte avant qu'il parte
(`reserve`), et règle la réservation au coût réel après (`record`). La
déclaration suit le contexte (contextvars) : les fils d'un ThreadPoolExecutor
doivent recevoir une copie du contexte (`contextvars.copy_context().run`).

Un refus de facturation du fournisseur (solde épuisé, limite de dépense de
l'organisation, quota) est traité comme un budget atteint, garde installée
ou non : `LLMBudgetExhausted`, jamais de nouvel essai, jamais de bascule vers
un autre fournisseur. L'appelant dégrade proprement (génération sans
enrichissement ni raffinement, évaluation « non évaluée »).
"""
from __future__ import annotations

import contextvars
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol

logger = logging.getLogger("mcp_forge.llm_budget")

DAILY_BUDGET = "LLM_DAILY_BUDGET"
# Plafond du compte (licence bêta, clé de test), par jour UTC
ACCOUNT_DAILY_BUDGET = "LLM_ACCOUNT_DAILY_BUDGET"
BILLING_EXHAUSTED = "LLM_PROVIDER_BILLING_EXHAUSTED"

# Tarifs Anthropic en $ par million de tokens (entrée, sortie), vérifiés le
# 2026-10-29 (référence claude-api). Clé : préfixe de l'identifiant du modèle.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
}
# Modèle payant inconnu : le plus cher connu, pour ne jamais sous-compter
_UNKNOWN_PRICE = max(PRICES_PER_MTOK.values(), key=lambda p: p[1])

# Marqueurs d'un refus de facturation dans le corps d'une réponse d'erreur
# (Anthropic : 402 billing_error, ou 400 « credit balance is too low » /
# « reached your specified API usage limits » ; OpenAI : insufficient_quota).
_BILLING_MARKERS = (
    "billing_error",
    "credit balance",
    "usage limits",
    "spend limit",
    "insufficient_quota",
    "exceeded your current quota",
)


class LLMBudgetExhausted(RuntimeError):
    """Plus d'appel LLM possible pour l'instant. `reason` : DAILY_BUDGET ou
    BILLING_EXHAUSTED."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


class SpendGuard(Protocol):
    def blocked_reason(self, account: str | None = None) -> str | None: ...
    def reserve(self, site: str, account: str | None) -> tuple[str | None, str | None]: ...
    def record(self, site: str, provider: str, model: str, input_tokens: int, output_tokens: int,
               account: str | None = None, reservation: str | None = None) -> None: ...
    def billing_refused(self, site: str, provider: str, detail: str) -> None: ...


_guard: SpendGuard | None = None
_account: contextvars.ContextVar[str | None] = contextvars.ContextVar("llm_account", default=None)
# Réservation de l'appel en cours dans ce contexte (posée par before_call,
# réglée par after_call)
_reservation: contextvars.ContextVar[str | None] = contextvars.ContextVar("llm_reservation", default=None)


@contextmanager
def account(tenant_id: str | None) -> Iterator[None]:
    """Compte qui paie les appels LLM faits dans ce bloc (None : aucun)."""
    token = _account.set(tenant_id)
    try:
        yield
    finally:
        _account.reset(token)


def current_account() -> str | None:
    return _account.get()


def install(guard: SpendGuard | None) -> None:
    global _guard
    _guard = guard


def blocked_reason() -> str | None:
    """Raison pour laquelle aucun appel ne doit partir (budget global, ou
    celui du compte déclaré), ou None. Sans réservation."""
    return _guard.blocked_reason(_account.get()) if _guard is not None else None


def before_call(site: str) -> None:
    """Avant chaque appel payant : réserve son coût maximal pour le compte
    déclaré (sous verrou), ou lève LLMBudgetExhausted."""
    if _guard is None:
        return
    reason, reservation = _guard.reserve(site, _account.get())
    if reason:
        raise LLMBudgetExhausted(reason, f"{site} skipped")
    _reservation.set(reservation)


def after_call(site: str, provider: str, model: str, input_tokens: int | None, output_tokens: int | None) -> None:
    if _guard is None:
        return
    reservation = _reservation.get()
    _reservation.set(None)
    try:
        _guard.record(site, provider, model, int(input_tokens or 0), int(output_tokens or 0),
                      account=_account.get(), reservation=reservation)
    except Exception:  # la dépense a eu lieu : ne pas faire échouer l'appel pour autant
        logger.exception("LLM spend not recorded site=%s model=%s", site, model)


def is_billing_error(status_code: int | None, body: str) -> bool:
    if status_code == 402:
        return True
    if status_code not in (400, 403, 429):
        return False
    text = (body or "").lower()
    return any(marker in text for marker in _BILLING_MARKERS)


def check_provider_error(site: str, provider: str, status_code: int | None, body: str) -> None:
    """À appeler sur une réponse en erreur : lève LLMBudgetExhausted si c'est
    un refus de facturation, sinon ne fait rien (l'appelant gère l'erreur)."""
    if not is_billing_error(status_code, body):
        return
    detail = f"{provider} HTTP {status_code}: {(body or '')[:200]}"
    if _guard is not None:
        _guard.billing_refused(site, provider, detail)
    raise LLMBudgetExhausted(BILLING_EXHAUSTED, detail)


def cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    if provider == "local":
        return 0.0
    price_in, price_out = next(
        (p for prefix, p in PRICES_PER_MTOK.items() if (model or "").startswith(prefix)), _UNKNOWN_PRICE
    )
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000
