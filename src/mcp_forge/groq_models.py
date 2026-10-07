"""Choix automatique du meilleur modèle Groq accessible à une clé.

L'API Groq ne fournit aucune note de qualité : on classe les modèles de chat par taille
(paramètres lus dans l'id), puis on vérifie qu'ils tiennent nos contraintes de sortie avec un
petit test. Les modèles à raisonnement (ex. gpt-oss) sont écartés : leurs tokens de réflexion
épuisent max_tokens et tronquent la réponse de façon imprévisible avec nos limites actuelles.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

import httpx

logger = logging.getLogger("mcp_forge.groq_models")

_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"

# Ids qui ne sont pas des modèles de chat texte (audio, modération, agents composés...)
_EXCLUDED = ("whisper", "orpheus", "tts", "guard", "compound", "embed")
_MAX_CANDIDATES = 3
_PROBE_MAX_TOKENS = 160  # même ordre de grandeur que nos appels d'enrichissement les plus serrés
_CACHE_TTL = 3600.0
_cache: dict[str, tuple[str, float]] = {}


def _size(model: dict) -> tuple[float, int]:
    params = 0.0
    for token in re.split(r"[-/_]", model["id"].lower()):
        number = token[:-1]
        if token.endswith("b") and number.replace(".", "", 1).isdigit():
            params = float(number)
            break
    return (params, model.get("context_window") or 0)


def _probe(api_key: str, model: str) -> bool | None:
    """True = utilisable, False = inadapté, None = indéterminé (erreur transitoire)."""
    try:
        response = httpx.post(
            f"{_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "max_tokens": _PROBE_MAX_TOKENS,
                "messages": [
                    {"role": "system", "content": "Reply with ONLY a JSON array, no prose."},
                    {
                        "role": "user",
                        "content": (
                            "Write a one-sentence description for each of these API tools: "
                            'getUser, deleteOrder, listItems. Format: [{"name": "...", "description": "..."}]'
                        ),
                    },
                ],
            },
            timeout=20,
        )
    except httpx.HTTPError:
        return None
    if response.status_code == 429 or response.status_code >= 500:
        return None
    if response.status_code != 200:
        return False
    try:
        data = response.json()
        choice = data["choices"][0]
        # La longueur du raisonnement varie d'un appel à l'autre : on écarte le modèle dès qu'il raisonne.
        reasoning_tokens = (data.get("usage", {}).get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
        if choice["message"].get("reasoning") or reasoning_tokens:
            return False
        content = (choice["message"].get("content") or "").strip()
        if choice.get("finish_reason") != "stop":
            return False
        if content.startswith("```"):
            content = content.strip("`").removeprefix("json").strip()
        items = json.loads(content)
        return isinstance(items, list) and len(items) == 3 and all("description" in i for i in items)
    except (ValueError, KeyError, TypeError):
        return False


def resolve_groq_model(api_key: str) -> str:
    """GROQ_MODEL (forçage manuel) > meilleur modèle utilisable pour cette clé > défaut."""
    override = os.environ.get("GROQ_MODEL")
    if override:
        return override

    cached = _cache.get(api_key)
    if cached and cached[1] > time.monotonic():
        return cached[0]

    try:
        response = httpx.get(f"{_BASE_URL}/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=5)
        response.raise_for_status()
        models = [
            m for m in response.json().get("data", [])
            if m.get("active", True) and not any(x in m["id"].lower() for x in _EXCLUDED)
        ]
    except Exception as exc:
        logger.warning("Groq: liste des modèles indisponible (%s) — modèle par défaut %s", exc, DEFAULT_MODEL)
        return DEFAULT_MODEL

    ranked = sorted((m for m in models if _size(m)[0] > 0), key=_size, reverse=True)
    for candidate in ranked[:_MAX_CANDIDATES]:
        verdict = _probe(api_key, candidate["id"])
        if verdict is None:
            # Erreur transitoire : on retient le mieux classé sans mémoriser le choix.
            logger.warning("Groq: test de %s indéterminé — utilisé sans vérification", candidate["id"])
            return candidate["id"]
        if verdict:
            _cache[api_key] = (candidate["id"], time.monotonic() + _CACHE_TTL)
            logger.info("Groq: modèle sélectionné %s", candidate["id"])
            return candidate["id"]
        logger.info("Groq: %s écarté (réponse tronquée ou invalide avec nos contraintes)", candidate["id"])

    logger.warning("Groq: aucun modèle utilisable parmi %d candidats — essai de %s", len(ranked), DEFAULT_MODEL)
    _cache[api_key] = (DEFAULT_MODEL, time.monotonic() + _CACHE_TTL)
    return DEFAULT_MODEL
