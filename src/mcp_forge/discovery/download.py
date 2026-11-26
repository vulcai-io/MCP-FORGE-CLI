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

Redirections (2026-11-19, en tête du plan du bac à sable) : avec une garde (`url_guard`, la
garde anti-SSRF de l'API), elles sont suivies à la main, au plus MAX_REDIRECTS, et CHAQUE étape
repasse par la garde AVANT sa requête : un serveur public ne peut plus renvoyer vers une adresse
interne (169.254.169.254, réseau privé). Sans garde (CLI : localhost est un usage légitime),
httpx les suit comme avant.

DNS rebinding (2026-11-19, étape 1 du bac à sable) : la garde résolvait le nom, puis httpx le
résolvait de nouveau pour se connecter ; un DNS contrôlé par un attaquant pouvait répondre une
adresse publique à la garde et une adresse interne à la connexion. Quand la garde sait aussi
vérifier une adresse (`url_guard.check_ip`, la garde de l'API), la connexion passe par
_checked_client : résolution, contrôle de TOUTES les adresses obtenues, connexion à une adresse
contrôlée, en une seule étape et pour chaque connexion (redirections comprises). Le TLS garde le
nom d'hôte (SNI et vérification du certificat). Pas de proxy sur ce chemin (`trust_env=False`) :
un proxy résoudrait le nom lui-même, hors de ce contrôle.

Valeurs : spec 32 Mio (la plus grosse spec de l'annuaire APIs.guru du banc fait 4,8 Mo ; GitHub
environ 11 Mo), page 10 Mio, script ou configuration d'une page de doc 512 Kio ; connexion 10 s,
lecture 30 s, durée totale 60 s (spec) ou 30 s (page, script, configuration).
"""
from __future__ import annotations

import socket
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

MiB = 1024 * 1024
SPEC_MAX_BYTES = 32 * MiB
PAGE_MAX_BYTES = 10 * MiB
CONFIG_MAX_BYTES = 512 * 1024
CONNECT_TIMEOUT_S = 10.0
READ_TIMEOUT_S = 30.0
SPEC_DEADLINE_S = 60.0
PAGE_DEADLINE_S = 30.0
MAX_REDIRECTS = 5
# Plafonds plus bas pour un contexte (bac à sable de l'API : 5 Mio, 15 s) : (octets, secondes)
_CAPS: ContextVar[tuple[int, float] | None] = ContextVar("download_caps", default=None)


@contextmanager
def capped(max_bytes: int, deadline_s: float) -> Iterator[None]:
    """Dans ce bloc (et ce fil), chaque téléchargement est borné au plus bas des deux plafonds."""
    token = _CAPS.set((max_bytes, deadline_s))
    try:
        yield
    finally:
        _CAPS.reset(token)
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


class DownloadTooLarge(ValueError):
    """Réponse plus grande que la limite."""


class DownloadTooSlow(ValueError):
    """Réponse plus longue à recevoir que la durée totale permise."""


class RedirectRefused(ValueError):
    """Redirection refusée : vers une adresse que la garde refuse, ou au-delà de MAX_REDIRECTS."""


class AddressRefused(RedirectRefused):
    """Connexion refusée : le nom se résout (au moment de la connexion) vers une adresse que la
    garde refuse. Sous-classe de RedirectRefused : traitée de la même façon par les appelants."""


def _checked_client(check_ip: Callable[[str], None]) -> httpx.Client:
    """Client httpx dont chaque connexion se fait à une adresse contrôlée par `check_ip` : résout
    le nom une seule fois, refuse si UNE des adresses obtenues est refusée, puis se connecte à ces
    adresses-là ; sans proxy. Construit seulement pour une garde qui juge les adresses (l'API) :
    l'import du module n'en dépend pas (le banc des parseurs remplace httpx)."""
    import httpcore

    class _CheckedBackend(httpcore.SyncBackend):
        def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
            try:
                infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            except socket.gaierror as exc:
                raise httpcore.ConnectError(f"{host}: {exc}") from exc
            addresses = list(dict.fromkeys(info[4][0] for info in infos))
            for address in addresses:
                try:
                    check_ip(address)
                except Exception as exc:
                    raise AddressRefused(
                        f"{host} resolves to a refused address at connection time ({exc})") from exc
            last_error: Exception | None = None
            for address in addresses:
                try:
                    return super().connect_tcp(address, port, timeout=timeout, local_address=local_address,
                                               socket_options=socket_options)
                except httpcore.ConnectError as exc:
                    last_error = exc
            raise last_error or httpcore.ConnectError(f"{host}: no address")

    transport = httpx.HTTPTransport(trust_env=False)
    transport._pool = httpcore.ConnectionPool(ssl_context=transport._pool._ssl_context,
                                              network_backend=_CheckedBackend())
    return httpx.Client(transport=transport, trust_env=False)


@dataclass
class Downloaded:
    status_code: int
    text: str
    url: str


def fetch(url: str, *, max_bytes: int, deadline_s: float, headers: dict[str, str] | None = None,
          method: str = "GET", json: Any = None,
          url_guard: Callable[[str], None] | None = None) -> Downloaded:
    """Requête bornée en taille et en durée : GET, ou POST avec un corps JSON (introspection
    GraphQL). Redirections suivies ; avec `url_guard`, chaque étape (l'URL de départ comprise)
    passe par la garde avant sa requête. Lève DownloadTooLarge, DownloadTooSlow, RedirectRefused
    ou une erreur httpx."""
    caps = _CAPS.get()
    if caps is not None:
        max_bytes, deadline_s = min(max_bytes, caps[0]), min(deadline_s, caps[1])
    timeout = httpx.Timeout(READ_TIMEOUT_S, connect=CONNECT_TIMEOUT_S)
    start = time.monotonic()
    if url_guard is None:
        extra = {"json": json} if json is not None else {}
        with httpx.stream(method, url, timeout=timeout, follow_redirects=True, headers=headers,
                          **extra) as response:
            return _read(response, url, max_bytes, deadline_s, start)

    check_ip = getattr(url_guard, "check_ip", None)
    client = _checked_client(check_ip) if check_ip else None
    try:
        return _guarded(client, url, method, json, headers, timeout, url_guard, max_bytes, deadline_s, start)
    finally:
        if client is not None:
            client.close()


def _guarded(client, url, method, json, headers, timeout, url_guard, max_bytes, deadline_s, start) -> Downloaded:
    """Redirections suivies à la main ; chaque étape passe par la garde avant sa requête."""
    stream = client.stream if client is not None else httpx.stream
    current, verb, body = url, method, json
    for _hop in range(MAX_REDIRECTS + 1):
        try:
            url_guard(current)
        except Exception as exc:
            if current == url:
                raise
            raise RedirectRefused(f"{url}: redirect to {current} refused ({exc})") from exc
        extra = {"json": body} if body is not None else {}
        with stream(verb, current, timeout=timeout, follow_redirects=False, headers=headers,
                    **extra) as response:
            location = response.headers.get("location")
            if response.status_code not in _REDIRECT_STATUSES or not location:
                return _read(response, url, max_bytes, deadline_s, start)
        if time.monotonic() - start > deadline_s:
            raise DownloadTooSlow(f"{url}: still redirecting after {deadline_s:.0f} s")
        current = urljoin(current, location)
        # Comme httpx : 303 (et 301/302 après un POST) deviennent un GET sans corps
        if response.status_code == 303 or (response.status_code in (301, 302) and verb == "POST"):
            verb, body = "GET", None
    raise RedirectRefused(f"{url}: more than {MAX_REDIRECTS} redirects")


def _read(response: httpx.Response, url: str, max_bytes: int, deadline_s: float, start: float) -> Downloaded:
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
