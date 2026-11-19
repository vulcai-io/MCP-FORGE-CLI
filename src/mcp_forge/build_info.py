"""
Version écrite dans le fichier VERSION des serveurs générés (PO, 2026-11-15).

Avant : `version("mcp-forge")`, un nom de distribution qui n'existe pas
(le paquet s'appelle vulcai-mcp-forge-cli) ; toutes les générations, locales
comme par l'API, écrivaient `mcp_forge_version: dev`.

Maintenant :
  - génération locale (CLI) : version du paquet vulcai-mcp-forge-cli ;
  - génération par l'API : version du paquet installé dans l'image de
    l'API, plus le commit de l'image (FORGE_BUILD_COMMIT, passé au build
    par .github/workflows/deploy-api.yml).
Ce qui n'est pas connu s'écrit `unknown`, jamais une valeur inventée.
"""
from __future__ import annotations

import os
import re
from importlib.metadata import PackageNotFoundError, version

DISTRIBUTION = "vulcai-mcp-forge-cli"
UNKNOWN = "unknown"
_COMMIT_RE = re.compile(r"[0-9a-f]{7,40}")


def package_version() -> str:
    try:
        return version(DISTRIBUTION)
    except PackageNotFoundError:
        return UNKNOWN


def build_commit() -> str:
    """Commit de l'image de l'API (7 caractères), `unknown` sans valeur valable."""
    commit = os.environ.get("FORGE_BUILD_COMMIT", "").strip().lower()
    return commit[:7] if _COMMIT_RE.fullmatch(commit) else UNKNOWN


def version_lines(generated_by: str) -> str:
    """Lignes du fichier VERSION qui disent qui a généré le serveur."""
    if generated_by == "api":
        return f"mcp_forge_version: {package_version()}\ngenerated_by: api\napi_commit: {build_commit()}\n"
    return f"mcp_forge_version: {package_version()}\ngenerated_by: cli\n"
