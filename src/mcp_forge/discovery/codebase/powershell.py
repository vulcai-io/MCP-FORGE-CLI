"""
Parser PowerShell pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .ps1 / .psm1 / .psd1.

Formats supportés :
  function Verb-Noun { ... }
  function Verb-Noun([Type]$param) { ... }
  function Verb-Noun {
      param([Type]$param1, [Type]$param2)
      ...
  }

Extrait les fonctions publiques (pas de préfixe _).
Extrait le comment-based help (.SYNOPSIS / .DESCRIPTION).
"""
from __future__ import annotations

import keyword as _kw
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Comment-based help PowerShell (<# ... #>)
_BLOCK_HELP_RE = re.compile(r'<#(.*?)#>', re.DOTALL)

# Déclaration de fonction PowerShell
_FUNC_RE = re.compile(
    r'(?:^|\n)'
    r'[ \t]*'
    r'(?:function|filter)[ \t]+'
    r'([a-zA-Z][a-zA-Z0-9_-]*)'    # nom (Verb-Noun convention)
    r'[ \t]*'
    r'(?:\(([^)]*)\))?'             # paramètres inline optionnels
    r'[ \t\n]*\{',                  # accolade ouvrante (même ligne ou suivante)
    re.MULTILINE | re.IGNORECASE,
)

# Début d'un bloc param()
_PARAM_BLOCK_START_RE = re.compile(r'\bparam\s*\(', re.IGNORECASE)

_SKIP_PREFIXES = ("_",)

_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    "constructor", "prototype", "__proto__",
}

# Mapping types PowerShell >> ParameterType
_PS_TYPE_MAP: dict[str, ParameterType] = {
    "int": ParameterType.INTEGER,
    "int32": ParameterType.INTEGER,
    "int64": ParameterType.INTEGER,
    "long": ParameterType.INTEGER,
    "double": ParameterType.NUMBER,
    "float": ParameterType.NUMBER,
    "decimal": ParameterType.NUMBER,
    "bool": ParameterType.BOOLEAN,
    "switch": ParameterType.BOOLEAN,
    "string": ParameterType.STRING,
    "char": ParameterType.STRING,
}


class PowerShellParser:
    """Extrait les fonctions publiques de fichiers PowerShell via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        if path.name.startswith("_") or ".Tests." in path.name:
            return []
        try:
            source = path.read_text(encoding="utf-8-sig", errors="ignore")  # BOM possible
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")
        module_name = _SLUG_RE.sub("_", path.stem.lower()).strip("_")

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        for m in _FUNC_RE.finditer(source):
            func_name = m.group(1)
            if any(func_name.startswith(p) for p in _SKIP_PREFIXES):
                continue

            func_slug = _SLUG_RE.sub("_", func_name.lower()).strip("_") or "func"
            slug = f"{module_name}_{func_slug}" if module_name else func_slug
            if slug in seen:
                continue
            seen.add(slug)

            description = _extract_help(source, m.start()) or f"function {func_name}"
            params = _resolve_params(source, m.group(2) or "", m.end())

            tools.append(DiscoveredTool(
                name=slug,
                description=description,
                parameters=params,
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": func_name,
                    "language": "powershell",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _resolve_params(source: str, inline: str, body_start: int) -> list[ToolParameter]:
    """Retourne les paramètres inline ou depuis le bloc param() dans le corps."""
    if inline.strip():
        return _parse_ps_params(inline)
    body = source[body_start:body_start + 1200]
    pb = _PARAM_BLOCK_START_RE.search(body)
    if not pb:
        return []
    raw = _extract_balanced(body, pb.end())
    return _parse_ps_params(raw)


def _extract_balanced(text: str, start: int) -> str:
    """Extrait le contenu entre parenthèses équilibrées à partir de `start`."""
    depth, pos = 1, start
    while pos < len(text) and depth > 0:
        if text[pos] == "(":
            depth += 1
        elif text[pos] == ")":
            depth -= 1
        pos += 1
    return text[start:pos - 1]


def _extract_help(source: str, pos: int) -> str:
    """Extrait le comment-based help (<# .SYNOPSIS / .DESCRIPTION #>) précédant la fonction."""
    preceding = source[max(0, pos - 800):pos]
    matches = list(_BLOCK_HELP_RE.finditer(preceding))
    if not matches:
        return ""
    last = matches[-1]
    if re.search(r'\S', preceding[last.end():].strip()):
        return ""
    return _parse_help_block(last.group(1))


def _parse_help_block(block: str) -> str:
    """Extrait .SYNOPSIS ou .DESCRIPTION d'un bloc comment-based help."""
    for tag in (".SYNOPSIS", ".DESCRIPTION"):
        m = re.search(rf'{re.escape(tag)}\s*\n(.*?)(?:\n\s*\.|$)', block, re.DOTALL | re.IGNORECASE)
        if m:
            text = re.sub(r'\s+', ' ', m.group(1)).strip()
            if text:
                return text[:200]
    return ""


def _parse_ps_params(raw: str) -> list[ToolParameter]:
    """
    Parse les paramètres PowerShell :
    [Parameter(Mandatory)][Type]$name
    [Type]$name = default
    [switch]$flag
    """
    if not raw.strip():
        return []

    params: list[ToolParameter] = []
    for part in _split_params(raw):
        param = _parse_single_ps_param(part.strip())
        if param:
            params.append(param)
    return params


def _parse_single_ps_param(part: str) -> ToolParameter | None:
    """Parse un paramètre PowerShell individuel."""
    if not part:
        return None

    mandatory = bool(re.search(r'Mandatory', part, re.IGNORECASE))

    # Retire les attributs [Parameter(...)] avec parenthèses équilibrées
    part = re.sub(r'\[Parameter\b[^\]]*\]\s*', '', part, flags=re.IGNORECASE).strip()

    has_default = "=" in part
    part = part.split("=")[0].strip()

    # Le type peut être un tableau (`[double[]]$Numbers`) : le `[]` de fin de
    # type ne doit pas être confondu avec le crochet fermant du type lui-même.
    type_match = re.match(r'\[([^\[\]]+(?:\[\])?)\]\s*\$(\w+)', part, re.IGNORECASE)
    if type_match:
        ps_type = type_match.group(1).lower()
        param_name = type_match.group(2)
    else:
        name_match = re.match(r'\$(\w+)', part)
        if not name_match:
            return None
        param_name = name_match.group(1)
        ps_type = "string"

    if param_name.startswith("_"):
        return None

    slug = _SLUG_RE.sub("_", param_name.lower()).strip("_") or "param"
    if slug in _RESERVED:
        slug = slug + "_"

    items_type = None
    if ps_type.endswith("[]"):
        param_type = ParameterType.ARRAY
        items_type = _PS_TYPE_MAP.get(ps_type[:-2])
    else:
        param_type = _PS_TYPE_MAP.get(ps_type, ParameterType.STRING)

    return ToolParameter(
        name=slug,
        type=param_type,
        items_type=items_type,
        description=f"[{ps_type}]",
        required=mandatory or not has_default,
    )


def _split_params(raw: str) -> list[str]:
    """Divise les paramètres en gérant les crochets et parenthèses imbriqués."""
    parts, depth, current = [], 0, []
    for ch in raw:
        if ch in ("(", "[", "{"):
            depth += 1
            current.append(ch)
        elif ch in (")", "]", "}"):
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return parts
