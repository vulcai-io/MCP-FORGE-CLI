"""
Parser Julia pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .jl.

Formats supportés :
  function functionName(param1, param2) ... end
  function functionName(param::Type, param2::Type = default) ... end
  functionName(param) = expr   (forme courte)

Les fonctions publiques (pas de préfixe _) sont extraites.
Extrait les docstrings \"\"\"...\"\"\" précédant la déclaration.
"""
from __future__ import annotations

import keyword as _kw
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Commentaires Julia : # et #= ... =#
_LINE_COMMENT_RE = re.compile(r"#(?!=).*")
_BLOCK_COMMENT_RE = re.compile(r"#=.*?=#", re.DOTALL)

# Docstring Julia : """...""" avant une déclaration
_DOCSTRING_RE = re.compile(r'"""(.*?)"""', re.DOTALL)

# Forme longue : function name(params) ... end
_FUNC_LONG_RE = re.compile(
    r'(?:^|\n)'
    r'[ \t]*'
    r'(?:export\s+)?'                       # export optionnel
    r'function[ \t]+'
    r'([a-zA-Z_\u00C0-\u024F!][\w!.]*)'    # nom (Julia supporte Unicode et !)
    r'[ \t]*(?:\{[^}]*\})?'                # type params optionnels
    r'[ \t]*\(([^)]*)\)',                   # paramètres
    re.MULTILINE,
)

# Forme courte : name(params) = expr (sur une ligne)
_FUNC_SHORT_RE = re.compile(
    r'(?:^|\n)'
    r'[ \t]*'
    r'([a-zA-Z_\u00C0-\u024F][a-zA-Z0-9_!.]*)'  # nom
    r'[ \t]*\(([^)]*)\)'
    r'[ \t]*=[ \t]*(?!>)',                  # = mais pas =>
    re.MULTILINE,
)

# Module context
_MODULE_RE = re.compile(
    r'\bmodule\s+(\w+)',
    re.MULTILINE | re.IGNORECASE,
)

_SKIP_NAMES = {
    "show", "print", "display", "length", "size", "eltype",
    "iterate", "getindex", "setindex!", "push!", "pop!",
}
_SKIP_KEYWORDS = {
    "if", "else", "elseif", "for", "while", "begin",
    "end", "return", "let", "do", "try", "catch",
    "finally", "import", "using", "export", "module",
    "struct", "mutable", "abstract", "primitive", "type",
}

_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    "constructor", "prototype", "__proto__",
}

# Mapping types Julia >> ParameterType
_JULIA_TYPE_MAP: dict[str, ParameterType] = {
    "Int": ParameterType.INTEGER,
    "Int8": ParameterType.INTEGER,
    "Int16": ParameterType.INTEGER,
    "Int32": ParameterType.INTEGER,
    "Int64": ParameterType.INTEGER,
    "Integer": ParameterType.INTEGER,
    "UInt": ParameterType.INTEGER,
    "UInt64": ParameterType.INTEGER,
    "Float32": ParameterType.NUMBER,
    "Float64": ParameterType.NUMBER,
    "AbstractFloat": ParameterType.NUMBER,
    "Number": ParameterType.NUMBER,
    "Bool": ParameterType.BOOLEAN,
    "String": ParameterType.STRING,
    "AbstractString": ParameterType.STRING,
    "Char": ParameterType.STRING,
    "Symbol": ParameterType.STRING,
}


class JuliaParser:
    """Extrait les fonctions publiques de fichiers Julia via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        if any(x in path.name for x in ("test_", "_test", "runtests", "benchmark")):
            return []
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")

        cleaned = _BLOCK_COMMENT_RE.sub(" ", source)
        cleaned = _LINE_COMMENT_RE.sub("", cleaned)

        # `detected_module` n'est renseigné que si le fichier définit vraiment
        # un bloc `module X ... end` — `include()` (utilisé par le serveur
        # généré) exécute sinon le fichier dans le scope courant SANS créer
        # de module implicite nommé d'après le fichier : qualifier l'appel
        # avec un nom de module inventé (ex: `utils.is_prime(...)`) produit
        # une UndefVarError Julia garantie. Le préfixe de NOM d'outil, lui,
        # peut continuer à retomber sur le nom de fichier (juste cosmétique).
        detected_module = _detect_module(cleaned)
        prefix = _SLUG_RE.sub("_", (detected_module or path.stem).lower()).strip("_")

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        # Collecte les deux types de fonctions
        matches: list[tuple[int, str, str]] = []
        for m in _FUNC_LONG_RE.finditer(cleaned):
            matches.append((m.start(), m.group(1), m.group(2)))
        for m in _FUNC_SHORT_RE.finditer(cleaned):
            matches.append((m.start(), m.group(1), m.group(2)))

        for pos, func_name, raw_params in sorted(matches):
            if func_name.startswith("_"):
                continue
            if func_name.lower() in _SKIP_KEYWORDS:
                continue
            if func_name in _SKIP_NAMES:
                continue

            func_slug = _SLUG_RE.sub("_", func_name.lower()).strip("_") or "func"
            slug = f"{prefix}_{func_slug}" if prefix else func_slug

            if slug in seen:
                continue
            seen.add(slug)

            description = _extract_docstring(source, pos) or f"function {func_name}(...)"
            params = _parse_params(raw_params.strip())

            tools.append(DiscoveredTool(
                name=slug,
                description=description,
                parameters=params,
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": func_name,
                    "module": detected_module or "",
                    "language": "julia",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _detect_module(cleaned: str) -> str:
    m = _MODULE_RE.search(cleaned)
    return m.group(1) if m else ""


def _extract_docstring(source: str, pos: int) -> str:
    """Extrait la docstring \"\"\"...\"\"\" précédant la déclaration."""
    preceding = source[max(0, pos - 800):pos]
    matches = list(_DOCSTRING_RE.finditer(preceding))
    if not matches:
        return ""
    last = matches[-1]
    after = preceding[last.end():]
    # Seuls des espaces/newlines entre le docstring et la fonction
    if re.search(r'\S', after.strip()):
        return ""
    text = last.group(1).strip()
    return re.sub(r"\s+", " ", text).strip()[:200]


def _parse_params(raw: str) -> list[ToolParameter]:
    """
    Parse les paramètres Julia :
    - `param`
    - `param::Type`
    - `param::Type = default`
    - `param...` (varargs)
    - `;keyword = default` (kwargs)
    """
    if not raw.strip():
        return []

    # Sépare les positionnels des kwargs (séparés par ;)
    if ";" in raw:
        positional_raw, kwargs_raw = raw.split(";", 1)
    else:
        positional_raw, kwargs_raw = raw, ""

    params: list[ToolParameter] = []

    for part, required in [
        *[(p, True) for p in _split_params(positional_raw)],
        *[(p, False) for p in _split_params(kwargs_raw)],
    ]:
        part = part.strip()
        if not part:
            continue

        # Varargs param...
        is_vararg = part.endswith("...")
        part = part.rstrip(".")

        # Valeur par défaut
        has_default = "=" in part
        part = part.split("=")[0].strip()

        # Type annotation param::Type ou param::Type <: Bound
        if "::" in part:
            param_name, julia_type = part.split("::", 1)
            julia_type = julia_type.split("<:")[0].strip()
        else:
            param_name = part
            julia_type = ""

        param_name = param_name.strip()

        if not param_name or param_name.startswith("_"):
            continue
        if param_name.lower() in _SKIP_KEYWORDS:
            continue

        slug = _SLUG_RE.sub("_", param_name.lower()).strip("_") or "param"
        if slug in _RESERVED:
            slug = slug + "_"

        # Type de base (sans génériques)
        base_type = re.sub(r"\{[^}]*\}", "", julia_type).strip()
        py_type = _JULIA_TYPE_MAP.get(base_type, ParameterType.STRING)

        params.append(ToolParameter(
            name=slug,
            type=py_type,
            description=julia_type or ("varargs" if is_vararg else ""),
            required=required and not has_default and not is_vararg,
        ))

    return params


def _split_params(raw: str) -> list[str]:
    parts, depth, current = [], 0, []
    for ch in raw:
        if ch in ("(", "[", "{", "<"):
            depth += 1
            current.append(ch)
        elif ch in (")", "]", "}", ">"):
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
