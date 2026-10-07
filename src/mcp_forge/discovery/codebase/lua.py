"""
Parser Lua pour la découverte codebase.
Utilise des expressions régulières pour extraire les fonctions publiques.

Formats supportés :
  function name(a, b)
  function Module.name(a, b)
  local function name(a, b)
"""
from __future__ import annotations

import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Capture : commentaire optionnel sur la ligne précédente, nom, paramètres
_FUNC_RE = re.compile(
    r'(?:^[ \t]*--[ \t]*([^\n]+)\n)?'           # commentaire optionnel (groupe 1)
    r'[ \t]*(?:local[ \t]+)?function[ \t]+'
    r'([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)'  # nom (groupe 2)
    r'[ \t]*\(([^)]*)\)',                         # paramètres (groupe 3)
    re.MULTILINE,
)

# Noms trop génériques à ignorer
_SKIP_SHORT_NAMES = {"init", "new", "create", "callback", "main"}


class LuaParser:
    """Extrait les fonctions publiques de fichiers Lua via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        tools: list[DiscoveredTool] = []
        relative_path = str(path.relative_to(root))
        seen: set[str] = set()

        for m in _FUNC_RE.finditer(source):
            comment = (m.group(1) or "").strip()
            raw_name = m.group(2).strip()
            raw_params = m.group(3).strip()

            short = raw_name.split(".")[-1]
            if short.startswith("_") or short.lower() in _SKIP_SHORT_NAMES:
                continue

            name = _SLUG_RE.sub("_", raw_name.lower()).strip("_")
            if name in seen:
                continue
            seen.add(name)

            tools.append(DiscoveredTool(
                name=name,
                description=comment or raw_name,
                parameters=_parse_params(raw_params),
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": raw_name,
                    "language": "lua",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _parse_params(raw: str) -> list[ToolParameter]:
    if not raw.strip():
        return []
    params = []
    for p in raw.split(","):
        p = p.strip()
        if not p or p in ("self", "..."):
            continue
        clean = re.sub(r"[^a-z0-9_]", "_", p.lower()).strip("_")
        if clean:
            params.append(ToolParameter(
                name=clean,
                type=ParameterType.STRING,
                description="",
                required=True,
            ))
    return params
