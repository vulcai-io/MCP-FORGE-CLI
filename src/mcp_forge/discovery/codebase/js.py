"""
Parser JavaScript / TypeScript pour la découverte codebase.
Utilise des expressions régulières pour extraire les fonctions exportées.

Formats supportés :
  function name(a, b) { ... }
  export function name(a, b) { ... }
  export async function name(a, b) { ... }
  const name = (a, b) => { ... }
  export const name = async (a, b) => { ... }
"""
from __future__ import annotations

import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_FUNC_RE = re.compile(
    # function name(...)
    r'(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(([^)]*)\)'
    # const name = (...) =>
    r'|(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*='
    r'\s*(?:async\s+)?\(([^)]*)\)\s*=>',
    re.MULTILINE,
)


class JSParser:
    """Extrait les fonctions publiques de fichiers JS/TS via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        tools: list[DiscoveredTool] = []
        relative_path = str(path.relative_to(root))
        seen: set[str] = set()

        for m in _FUNC_RE.finditer(source):
            raw_name = m.group(1) or m.group(3)
            raw_params = m.group(2) if m.group(1) else (m.group(4) or "")

            if not raw_name or raw_name.startswith("_"):
                continue

            name = _SLUG_RE.sub("_", raw_name.lower()).strip("_")
            if name in seen:
                continue
            seen.add(name)

            tools.append(DiscoveredTool(
                name=name,
                description=raw_name,
                parameters=_parse_params(raw_params),
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": raw_name,
                    "language": "javascript",
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
        # Retire les annotations TypeScript (name: Type = default)
        p = re.sub(r":.*", "", p).split("=")[0].strip()
        p = re.sub(r"[^a-zA-Z0-9_$]", "", p)
        if not p or p == "this":
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
