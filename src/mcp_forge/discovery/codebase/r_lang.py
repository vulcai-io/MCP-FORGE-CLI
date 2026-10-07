"""
Parser R pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .R / .r.

Formats supportés :
  function_name <- function(param1, param2) { ... }
  function_name <- function(param1, param2 = default) { ... }
  function_name = function(param1, ...) { ... }

Extrait les fonctions publiques (pas de préfixe . ou _).
Extrait les commentaires Roxygen2 (#' @title / @description).
"""
from __future__ import annotations

import keyword as _kw
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Roxygen2 : blocs #' consécutifs
_ROXYGEN_RE = re.compile(r'(?:[ \t]*#\'[^\n]*\n)+')

# Déclaration de fonction R
# function_name <- function(...) ou function_name = function(...)
_FUNC_RE = re.compile(
    r'^([a-zA-Z.][a-zA-Z0-9._]*)'   # nom (R autorise . dans les noms)
    r'\s*(?:<-|=)\s*'
    r'function\s*\(([^)]*)\)',       # paramètres
    re.MULTILINE,
)

_SKIP_NAMES = {
    "T", "F",  # alias TRUE/FALSE
    "NA", "NULL", "Inf", "NaN",
}
_SKIP_PREFIXES = (".", "_")  # .hidden en R = privé par convention

_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    "constructor", "prototype", "__proto__",
}

# Mapping types R >> ParameterType (via @param type)
_R_TYPE_MAP: dict[str, ParameterType] = {
    "integer": ParameterType.INTEGER,
    "int": ParameterType.INTEGER,
    "numeric": ParameterType.NUMBER,
    "double": ParameterType.NUMBER,
    "float": ParameterType.NUMBER,
    "logical": ParameterType.BOOLEAN,
    "bool": ParameterType.BOOLEAN,
    "character": ParameterType.STRING,
    "string": ParameterType.STRING,
    "chr": ParameterType.STRING,
}


class RParser:
    """Extrait les fonctions publiques de fichiers R via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        if any(x in path.name for x in ("test-", "-test", "_test", "helper")):
            return []
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")
        module_name = _SLUG_RE.sub("_", path.stem.lower()).strip("_")

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        for m in _FUNC_RE.finditer(source):
            func_name = m.group(1)
            raw_params = m.group(2).strip()

            if func_name in _SKIP_NAMES:
                continue
            if any(func_name.startswith(p) for p in _SKIP_PREFIXES):
                continue

            func_slug = _SLUG_RE.sub("_", func_name.lower()).strip("_") or "func"
            slug = f"{module_name}_{func_slug}" if module_name else func_slug

            if slug in seen:
                continue
            seen.add(slug)

            roxygen = _extract_roxygen(source, m.start())
            description = roxygen.get("description") or roxygen.get("title") or f"{func_name}(...)"
            params = _parse_params(raw_params, roxygen.get("params", {}))

            tools.append(DiscoveredTool(
                name=slug,
                description=description,
                parameters=params,
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": func_name,
                    "language": "r",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_roxygen(source: str, pos: int) -> dict:
    """Extrait le bloc Roxygen2 (#') précédant la déclaration."""
    preceding = source[max(0, pos - 800):pos]
    m = _ROXYGEN_RE.search(preceding)
    if not m:
        return {}

    after = preceding[m.end():]
    # Le bloc doit être juste avant la déclaration (pas de code entre)
    if re.search(r'\S', after):
        return {}

    block = m.group(0)
    # Retire le préfixe #'
    lines = [re.sub(r"^\s*#'\s?", "", l) for l in block.splitlines()]

    result: dict = {"params": {}}
    title_lines = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("@title"):
            result["title"] = line[6:].strip()
        elif line.startswith("@description"):
            result["description"] = line[12:].strip()
        elif line.startswith("@param"):
            parts = line[6:].strip().split(None, 2)
            if len(parts) >= 1:
                pname = parts[0]
                pdesc = parts[1] if len(parts) > 1 else ""
                # Le type peut être entre [] : @param name [type] desc
                type_match = re.match(r'\[([^\]]+)\]\s*(.*)', pdesc)
                if type_match:
                    result["params"][pname] = {
                        "type": type_match.group(1).lower(),
                        "desc": type_match.group(2),
                    }
                else:
                    result["params"][pname] = {"type": "", "desc": pdesc}
        elif not line.startswith("@") and "title" not in result:
            if line:
                title_lines.append(line)
        i += 1

    if title_lines and "title" not in result:
        result["title"] = " ".join(title_lines)[:200]

    return result


def _parse_params(raw: str, roxygen_params: dict) -> list[ToolParameter]:
    """Parse les paramètres R : `name`, `name = default`, `...`."""
    if not raw.strip():
        return []

    params: list[ToolParameter] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue

        # ... (varargs) >> ignoré
        if part == "...":
            continue

        # Retire la valeur par défaut
        has_default = "=" in part
        param_name = part.split("=")[0].strip()

        if not param_name or any(param_name.startswith(p) for p in _SKIP_PREFIXES):
            continue

        slug = _SLUG_RE.sub("_", param_name.lower()).strip("_") or "param"
        if slug in _RESERVED:
            slug = slug + "_"

        # Type depuis Roxygen2
        rox = roxygen_params.get(param_name, {})
        r_type = rox.get("type", "")
        py_type = _R_TYPE_MAP.get(r_type, ParameterType.STRING)
        description = rox.get("desc", "")

        params.append(ToolParameter(
            name=slug,
            type=py_type,
            description=description,
            required=not has_default,
        ))

    return params
