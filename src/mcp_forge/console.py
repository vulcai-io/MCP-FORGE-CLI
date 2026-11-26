"""
Console des modules du moteur (découverte, génération, enrichissement, évaluation).

Ces modules écrivent leur progression sur la sortie standard : en local, c'est l'écran du CLI ;
sur l'API, c'est le journal de production. Deux garanties (décision du PO du 2026-11-21) :

- `mask_url_queries` : toute URL écrite garde son schéma, son hôte et son chemin, mais sa
  requête et son fragment sont remplacés par « ?… ». Un jeton passé dans une URL (?token=,
  ?api_key=…) n'arrive donc jamais dans le journal, pour le bac à sable comme pour les comptes.
- `quiet()` : dans le contexte courant (fil de l'aperçu du bac à sable), plus rien n'est écrit ;
  le bac à sable écrit sa propre ligne, sans URL complète (api/services/sandbox.py). Les autres
  fils (générations des comptes) ne sont pas touchés : variable de contexte, pas d'état global.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from rich.console import Console

_QUIET: ContextVar[bool] = ContextVar("mcp_forge_console_quiet", default=False)
# Une URL http(s) suivie d'une requête ou d'un fragment. L'hôte et le chemin s'arrêtent à un
# blanc, un guillemet, un chevron, un crochet ou une barre oblique inverse (échappement rich).
_URL_WITH_QUERY = re.compile(r"(https?://[^\s?#'\"<>\[\]\\]+)[?#][^\s'\"<>\[\]\\]*")


def mask_url_queries(text: str) -> str:
    """« https://h/p?token=x#f » -> « https://h/p?… » ; le reste du texte est inchangé."""
    return _URL_WITH_QUERY.sub(r"\1?…", text)


def _masked(objects: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(mask_url_queries(o) if isinstance(o, str) else o for o in objects)


class EngineConsole(Console):
    """Console rich qui masque la requête des URL et se tait dans un contexte `quiet()`."""

    def print(self, *objects: Any, **kwargs: Any) -> None:  # noqa: A003 (nom de rich)
        if _QUIET.get():
            return
        super().print(*_masked(objects), **kwargs)

    def log(self, *objects: Any, **kwargs: Any) -> None:
        if _QUIET.get():
            return
        super().log(*_masked(objects), **kwargs)


@contextmanager
def quiet() -> Iterator[None]:
    """Fait taire les consoles du moteur dans le contexte courant (et lui seul)."""
    token = _QUIET.set(True)
    try:
        yield
    finally:
        _QUIET.reset(token)
