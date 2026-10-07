"""
Parser Go pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .go.

Formats supportés :
  func FunctionName(param1 Type1, param2 Type2) ReturnType
  func (r *ReceiverType) MethodName(params) (ReturnType, error)
  func FunctionName(a, b int, c string) (Type1, Type2)

Seules les fonctions exportées (nom commençant par une majuscule) sont extraites.
"""
from __future__ import annotations

import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

# GoDoc : commentaire(s) // juste avant la déclaration
_GODOC_RE = re.compile(r'(?:(?:^|\n)[ \t]*//[^\n]*)+\s*$')

# Déclaration de fonction Go exportée
# Gère : func Name(...) Type
#        func (recv Type) Name(...) (Type, error)
#        func Name[T any](...)  (generics)
_FUNC_RE = re.compile(
    r'\bfunc\s+'
    r'(?:\([^)]*\)\s+)?'            # receiver optionnel : (r *Type)
    r'([A-Z][A-Za-z0-9_]*)'         # nom exporté (commence par majuscule)
    r'(?:\[[^\]]*\])?'              # type parameters generics optionnels [T any]
    r'\s*\(([^)]*)\)',              # paramètres
    re.MULTILINE,
)

# Noms à ignorer (tests, init, main)
_SKIP_NAMES = {"Main", "Init", "TestMain"}
_SKIP_PREFIXES = ("Test", "Benchmark", "Example", "Fuzz")

# Mots réservés Python + JS builtins
import keyword as _kw
_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    # JS builtins problématiques dans les schemas MCP
    "constructor", "prototype", "__proto__",
}

# Mapping types Go >> ParameterType
_GO_TYPE_MAP: dict[str, ParameterType] = {
    "int": ParameterType.INTEGER,
    "int8": ParameterType.INTEGER,
    "int16": ParameterType.INTEGER,
    "int32": ParameterType.INTEGER,
    "int64": ParameterType.INTEGER,
    "uint": ParameterType.INTEGER,
    "uint8": ParameterType.INTEGER,
    "uint16": ParameterType.INTEGER,
    "uint32": ParameterType.INTEGER,
    "uint64": ParameterType.INTEGER,
    "uintptr": ParameterType.INTEGER,
    "byte": ParameterType.INTEGER,
    "rune": ParameterType.INTEGER,
    "float32": ParameterType.NUMBER,
    "float64": ParameterType.NUMBER,
    "complex64": ParameterType.NUMBER,
    "complex128": ParameterType.NUMBER,
    "bool": ParameterType.BOOLEAN,
    "string": ParameterType.STRING,
}


class GoParser:
    """Extrait les fonctions exportées de fichiers Go via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        # Ignore les fichiers de test
        if path.name.endswith("_test.go"):
            return []
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")
        package_name = _detect_package(source)

        cleaned = _BLOCK_COMMENT_RE.sub(" ", source)
        cleaned = _LINE_COMMENT_RE.sub("", cleaned)

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        for m in _FUNC_RE.finditer(cleaned):
            func_name = m.group(1)
            raw_params = m.group(2).strip()

            if func_name in _SKIP_NAMES:
                continue
            if any(func_name.startswith(p) for p in _SKIP_PREFIXES):
                continue

            func_slug = _SLUG_RE.sub("_", func_name.lower()).strip("_") or "func"
            pkg_slug = _SLUG_RE.sub("_", package_name.lower()).strip("_") if package_name else ""
            slug = f"{pkg_slug}_{func_slug}" if pkg_slug else func_slug

            if slug in seen:
                continue
            seen.add(slug)

            # GoDoc dans le source original (avant nettoyage)
            pos = m.start()
            description = _extract_godoc(source, pos) or f"func {func_name}(...)"

            params = _parse_params(raw_params)

            tools.append(DiscoveredTool(
                name=slug,
                description=description,
                parameters=params,
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": func_name,
                    "package": package_name,
                    "language": "go",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _detect_package(source: str) -> str:
    """Extrait le nom du package Go."""
    m = re.search(r'^\s*package\s+(\w+)', source, re.MULTILINE)
    return m.group(1) if m else ""


def _extract_godoc(source: str, pos: int) -> str:
    """Extrait le commentaire GoDoc précédant la déclaration."""
    preceding = source[max(0, pos - 600):pos]
    m = _GODOC_RE.search(preceding)
    if not m:
        return ""
    text = m.group(0).strip()
    # Retire les // de début de chaque ligne
    text = re.sub(r'^\s*//\s?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:200]


def _parse_params(raw: str) -> list[ToolParameter]:
    """Parse les paramètres Go : gère `a, b int`, `args ...Type`, etc."""
    if not raw.strip():
        return []

    params: list[ToolParameter] = []
    # Découpe en groupes (gère les types avec génériques ex: map[string]int)
    groups = _split_params(raw)

    for group in groups:
        group = group.strip()
        if not group:
            continue

        # Retire variadic ...
        is_variadic = "..." in group
        group = group.replace("...", "")

        tokens = group.split()
        if not tokens:
            continue

        # Cas : un seul token = type sans nom (ex: `func(int, string)`)
        if len(tokens) == 1:
            go_type = tokens[0]
            slug = "param"
            py_type = _resolve_type(go_type)
            params.append(ToolParameter(
                name=slug if slug not in _RESERVED else slug + "_",
                type=py_type,
                description=go_type + ("..." if is_variadic else ""),
                required=not is_variadic,
            ))
            continue

        # Dernier token = type Go (peut être *Type, []Type, map[K]V...)
        # Tokens précédents = noms de paramètres
        go_type = tokens[-1]
        names = tokens[:-1]

        # Si le premier token ressemble à un type (commence par *, [, majuscule pour types complexes)
        # et qu'il n'y a qu'un token avant le type >> c'est (name type)
        py_type = _resolve_type(go_type)

        for name in names:
            name = name.rstrip(",")
            if not name or name == "_":
                continue
            slug = _SLUG_RE.sub("_", name.lower()).strip("_") or "param"
            if slug in _RESERVED:
                slug = slug + "_"
            params.append(ToolParameter(
                name=slug,
                type=py_type,
                description=go_type + ("..." if is_variadic else ""),
                required=not is_variadic,
            ))

    return params


def _resolve_type(go_type: str) -> ParameterType:
    """Convertit un type Go en ParameterType."""
    base = go_type.lstrip("*").lstrip("[]").split("[")[0].split(".")[0]
    return _GO_TYPE_MAP.get(base, ParameterType.STRING)


def _split_params(raw: str) -> list[str]:
    """Divise les paramètres en gérant les types imbriqués (map[K]V, func(...))."""
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
