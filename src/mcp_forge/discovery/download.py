"""
Téléchargements de la découverte (spec OpenAPI par URL, page d'un site, scripts et configuration
d'une page Swagger UI ou Redoc, spec qu'elle affiche) : mêmes limites de taille et de temps pour
tous, côté CLI comme côté API (demande du PO du 2026-11-18).

- Taille : lecture en flux, arrêt dès que la limite est dépassée (en-tête Content-Length annoncé
  plus grand, ou octets reçus) ; la réponse n'est jamais gardée entière en mémoire au-delà.
- Temps : délai de connexion et de lecture de httpx, plus une durée totale (un serveur qui envoie
  quelques octets à la fois ne retient pas la découverte plus longtemps).

Introspection GraphQL (2026-11-18, avant le bac à sable) : comme une spec (la réponse est le
schéma) ; la requête de test d'authentification (`{ __typename }`), comme une configuration.

Valeurs : spec 32 Mio (la plus grosse spec de l'annuaire APIs.guru du banc fait 4,8 Mo ; GitHub
environ 11 Mo), page 10 Mio, script ou configuration d'une page de doc 512 Kio ; connexion 10 s,
lecture 30 s, durée totale 60 s (spec) ou 30 s (page, script, configuration).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

MiB = 1024 * 1024
SPEC_MAX_BYTES = 32 * MiB
PAGE_MAX_BYTES = 10 * MiB
CONFIG_MAX_BYTES = 512 * 1024
CONNECT_TIMEOUT_S = 10.0
READ_TIMEOUT_S = 30.0
SPEC_DEADLINE_S = 60.0
PAGE_DEADLINE_S = 30.0


class DownloadTooLarge(ValueError):
    """Réponse plus grande que la limite."""


class DownloadTooSlow(ValueError):
    """Réponse plus longue à recevoir que la durée totale permise."""


@dataclass
class Downloaded:
    status_code: int
    text: str
    url: str


def fetch(url: str, *, max_bytes: int, deadline_s: float, headers: dict[str, str] | None = None,
          method: str = "GET", json: Any = None) -> Downloaded:
    """Requête bornée en taille et en durée (redirections suivies) : GET, ou POST avec un corps
    JSON (introspection GraphQL). Lève DownloadTooLarge, DownloadTooSlow ou une erreur httpx."""
    timeout = httpx.Timeout(READ_TIMEOUT_S, connect=CONNECT_TIMEOUT_S)
    start = time.monotonic()
    extra = {"json": json} if json is not None else {}
    with httpx.stream(method, url, timeout=timeout, follow_redirects=True, headers=headers, **extra) as response:
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > max_bytes:
            raise DownloadTooLarge(f"{url}: {int(declared)} bytes announced, limit {max_bytes}")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > max_bytes:
                raise DownloadTooLarge(f"{url}: more than {max_bytes} bytes, limit reached")
            if time.monotonic() - start > deadline_s:
                raise DownloadTooSlow(f"{url}: still downloading after {deadline_s:.0f} s")
            chunks.append(chunk)
        body = b"".join(chunks)
        encoding = response.encoding or "utf-8"
        try:
            text = body.decode(encoding, errors="replace")
        except LookupError:
            text = body.decode("utf-8", errors="replace")
        return Downloaded(response.status_code, text, str(response.url))
