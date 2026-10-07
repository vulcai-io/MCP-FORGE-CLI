"""
Parser TypeScript pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .ts / .d.ts.

Formats supportés :
  export function name(param: Type, param2: Type): ReturnType
  export async function name(params): Promise<T>
  export const name = (param: Type): ReturnType => { ... }
  public methodName(param: Type): ReturnType          (classe)
  methodName(param: Type): ReturnType                 (interface)

Priorise les fichiers .d.ts (déclarations publiques) si présents.
"""
from __future__ import annotations

import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*(?!\*).*?\*/", re.DOTALL)
_JSDOC_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)

# Fonctions exportées (function / arrow)
_EXPORT_FUNC_RE = re.compile(
    r'\bexport\s+(?:default\s+)?(?:async\s+)?function\s*\*?\s*'
    r'([\w$]+)'                     # nom
    r'(?:<[^>]*>)?'                 # generics optionnels
    r'\s*\(([^)]*)\)',              # paramètres
    re.MULTILINE,
)

_EXPORT_ARROW_RE = re.compile(
    r'\bexport\s+(?:const|let)\s+([\w$]+)\s*(?::\s*[\w<>\[\]| ,?]+)?\s*='
    r'\s*(?:async\s+)?(?:<[^>]*>\s*)?\(([^)]*)\)\s*(?::\s*[\w<>\[\]| ,?]+)?\s*=>',
    re.MULTILINE,
)

# Méthodes de classe publiques / interface
_METHOD_RE = re.compile(
    r'^\s*(?:(?:public|static|async|abstract|override|readonly)\s+)*'
    r'(?:readonly\s+)?'
    r'([\w$]+)'                     # nom de méthode
    r'(?:<[^>]*>)?'                 # generics
    r'\s*\(([^)]*)\)'              # paramètres
    r'\s*(?::\s*[\w<>\[\]| ,?.]+)?'  # type de retour optionnel
    r'\s*[{;]',                    # corps { ou ; (interface)
    re.MULTILINE,
)

_SKIP_NAMES = {
    "constructor", "toString", "valueOf", "hasOwnProperty",
    "if", "for", "while", "switch", "catch",
}
_SKIP_PREFIXES = ("_", "on", "handle")

# Mots réservés Python + JS builtins
import keyword as _kw
_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    # JS builtins problématiques dans les schemas MCP
    "constructor", "prototype", "__proto__",
}

# Mapping types TypeScript >> ParameterType
_TS_TYPE_MAP: dict[str, ParameterType] = {
    "number": ParameterType.NUMBER,
    "bigint": ParameterType.INTEGER,
    "boolean": ParameterType.BOOLEAN,
    "bool": ParameterType.BOOLEAN,
    "string": ParameterType.STRING,
    "int": ParameterType.INTEGER,
    "float": ParameterType.NUMBER,
    "double": ParameterType.NUMBER,
}

DECLARATION_EXTENSIONS = {".d.ts"}
SOURCE_EXTENSIONS = {".ts", ".tsx"}


class TypeScriptParser:
    """Extrait les fonctions/méthodes exportées de fichiers TypeScript via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        if path.name.endswith(".test.ts") or path.name.endswith(".spec.ts"):
            return []
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")
        module_name = _detect_module_name(path)

        cleaned = _BLOCK_COMMENT_RE.sub(" ", source)
        cleaned = _LINE_COMMENT_RE.sub("", cleaned)

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        # 1. Fonctions exportées (export function / export const = =>)
        for m in _EXPORT_FUNC_RE.finditer(cleaned):
            _add_tool(m.group(1), m.group(2), m.start(), module_name,
                      source, relative_path, seen, tools)

        for m in _EXPORT_ARROW_RE.finditer(cleaned):
            _add_tool(m.group(1), m.group(2), m.start(), module_name,
                      source, relative_path, seen, tools)

        # 2. Méthodes de classe/interface publiques
        for m in _METHOD_RE.finditer(cleaned):
            name = m.group(1)
            if not name[0].isupper() and not _is_in_class_or_interface(cleaned, m.start()):
                continue
            _add_tool(name, m.group(2), m.start(), module_name,
                      source, relative_path, seen, tools)

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _add_tool(
    raw_name: str,
    raw_params: str,
    pos: int,
    module_name: str,
    source: str,
    relative_path: str,
    seen: set[str],
    tools: list[DiscoveredTool],
) -> None:
    if not raw_name or raw_name in _SKIP_NAMES:
        return
    if any(raw_name.startswith(p) for p in _SKIP_PREFIXES):
        return

    func_slug = _SLUG_RE.sub("_", raw_name.lower()).strip("_") or "func"
    slug = f"{module_name}_{func_slug}" if module_name else func_slug

    if slug in seen:
        return
    seen.add(slug)

    description = _extract_jsdoc(source, pos) or f"function {raw_name}(...)"
    params = _parse_params(raw_params or "")

    tools.append(DiscoveredTool(
        name=slug,
        description=description,
        parameters=params,
        tags=["codebase", relative_path],
        metadata={
            "file": relative_path,
            "function": raw_name,
            # `module_name` (nom de fichier) n'est qu'un préfixe COSMÉTIQUE
            # pour le nom d'outil (slug ci-dessus) — ce n'est pas un vrai
            # namespace TypeScript. Le qualifier utilisé par le générateur
            # pour construire l'appel doit rester vide : une fonction
            # `export function foo() {}` est appelée directement (`foo(...)`),
            # pas `utils.foo(...)` (même bug que Julia : `UndefVarError`/
            # `ReferenceError: utils is not defined` sinon).
            "module": "",
            "language": "typescript",
        },
    ))


def _detect_module_name(path: Path) -> str:
    """Dérive le nom de module depuis le nom de fichier."""
    name = path.name
    for suffix in (".d.ts", ".ts", ".tsx"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return _SLUG_RE.sub("_", name.lower()).strip("_")


def _is_in_class_or_interface(source: str, pos: int) -> bool:
    """Vérifie grossièrement si la position est dans un corps de classe/interface."""
    preceding = source[:pos]
    return bool(re.search(r'\b(?:class|interface)\b[^{]*\{[^}]*$', preceding, re.DOTALL))


def _extract_jsdoc(source: str, pos: int) -> str:
    """Extrait le commentaire JSDoc précédant la déclaration."""
    preceding = source[max(0, pos - 600):pos]
    matches = list(_JSDOC_RE.finditer(preceding))
    if not matches:
        return ""
    last = matches[-1]
    after = preceding[last.end():]
    if re.search(r'[;{}]', after):
        return ""
    text = last.group(1)
    text = re.sub(r"\n\s*\*\s?", " ", text)
    text = re.sub(r"@\w+[^\n]*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:200]


def _parse_params(raw: str) -> list[ToolParameter]:
    """Parse les paramètres TypeScript : `name: Type`, `name?: Type`, `name = default`."""
    if not raw.strip():
        return []

    params: list[ToolParameter] = []
    for part in _split_params(raw):
        part = part.strip()
        if not part:
            continue

        # Retire les décorateurs @...
        part = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", part).strip()
        # Retire readonly / public / private / protected
        part = re.sub(r"\b(readonly|public|private|protected)\s+", "", part).strip()

        optional = "?" in part
        # Retire la valeur par défaut = ...
        part = part.split("=")[0].strip()
        # Sépare nom et type sur le premier ':'
        if ":" in part:
            param_name, ts_type = part.split(":", 1)
            param_name = param_name.strip().rstrip("?").strip()
            ts_type = ts_type.strip()
        else:
            param_name = part.rstrip("?").strip()
            ts_type = "string"

        # Retire les ... (rest params)
        param_name = param_name.lstrip(".")
        if not param_name or param_name == "this":
            continue

        slug = _SLUG_RE.sub("_", param_name.lower()).strip("_") or "param"
        if slug in _RESERVED:
            slug = slug + "_"

        # Type de base (sans generics ni tableaux)
        base_type = re.sub(r"<[^>]*>", "", ts_type).replace("[]", "").replace("?", "").strip()
        base_type = base_type.split("|")[0].strip()  # union >> premier type
        py_type = _TS_TYPE_MAP.get(base_type, ParameterType.STRING)

        params.append(ToolParameter(
            name=slug,
            type=py_type,
            description=ts_type,
            required=not optional,
        ))

    return params


def _split_params(raw: str) -> list[str]:
    """Divise les paramètres en gérant les génériques et objets imbriqués."""
    parts, depth, current = [], 0, []
    for ch in raw:
        if ch in ("<", "(", "[", "{"):
            depth += 1
            current.append(ch)
        elif ch in (">", ")", "]", "}"):
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
