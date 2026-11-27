"""
Emplacement d'un paramètre dans l'appel que fait le serveur généré : une seule règle, pour le
générateur (`MCPGenerator._classify_params`) et pour les faits de la source transmis à
l'évaluateur (`eval_origin.source_facts`). Décision du PO du 2026-11-27, après la régénération
des 28 exemples : les faits disaient `in: query` pour un `slug` que le serveur place dans le
chemin (`/wiki/{slug}`), et `in: query` pour l'argument d'une fonction de codebase.
"""
from __future__ import annotations

import re
from typing import Any

from mcp_forge.models import SourceType

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
# Sources sans requête HTTP : le paramètre est un argument de la fonction ou de la commande
_ARGUMENT_SOURCES = (SourceType.CODEBASE, SourceType.CLI_APP)
ARGUMENT = "argument"


def path_placeholders(endpoint: str | None) -> set[str]:
    return set(_PLACEHOLDER.findall(endpoint or ""))


def http_location(param: Any, endpoint: str | None, http_method: str | None) -> str:
    """path, header, file_upload, body_binary, body ou query : où le serveur généré met ce
    paramètre dans la requête HTTP."""
    param_in = getattr(param, "param_in", "") or ""
    if param.name in path_placeholders(endpoint) or param_in == "path":
        return "path"
    if param_in in ("header", "file_upload", "body_binary"):
        return param_in
    if param_in in ("body_array", "formData", "body"):
        return "body"
    if param_in == "query" or http_method in ("GET", "DELETE", "HEAD", "OPTIONS"):
        return "query"
    return "body"


def fact_location(param: Any, endpoint: str | None, http_method: str | None,
                  source_type: SourceType | None) -> str:
    """Emplacement transmis à l'évaluateur : `argument` pour une codebase ou un outil CLI ;
    sinon celui du serveur généré (formData gardé tel quel, fichiers et corps binaires
    comptés dans le corps)."""
    if source_type in _ARGUMENT_SOURCES:
        return ARGUMENT
    location = http_location(param, endpoint, http_method)
    if location == "body" and getattr(param, "param_in", "") == "formData":
        return "formData"
    return "body" if location in ("file_upload", "body_binary") else location
