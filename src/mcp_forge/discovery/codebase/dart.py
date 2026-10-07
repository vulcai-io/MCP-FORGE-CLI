"""
Parser Dart pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .dart.

Formats supportés :
  ReturnType functionName(Type param)
  ReturnType methodName({required Type param, Type param2 = default})
  ReturnType methodName([Type param])
  Future<T> asyncMethod(Type param) async
  static ReturnType staticMethod(Type param)

Convention Dart : les identifiants commençant par _ sont privés.
Seuls les membres publics sont extraits.
Extrait les DartDoc (/// lignes).
"""
from __future__ import annotations

import keyword as _kw
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_LINE_COMMENT_RE = re.compile(r"//(?!/)[^\n]*")   # // mais pas ///
_BLOCK_COMMENT_RE = re.compile(r"/\*(?!\*).*?\*/", re.DOTALL)
_DARTDOC_RE = re.compile(r'(?:[ \t]*///[^\n]*\n)+')

# Fonction/méthode Dart publique (pas de préfixe _)
# Gère : async, static, @override, factory, external
_FUNC_RE = re.compile(
    r'(?:^|\n)'
    r'[ \t]*'
    r'(?:@\w+\s+)*'                          # annotations optionnelles
    r'(?:(?:static|external|abstract|'
    r'covariant|late|const|final|'
    r'override)\s+)*'                         # modificateurs
    r'(?:Future<[^>]*>|Stream<[^>]*>|[\w<>?,\s\[\]]+?)\s+'  # type retour
    r'([a-zA-Z][a-zA-Z0-9_]*)'              # nom PUBLIC (pas de _)
    r'\s*(?:<[^>]*>)?\s*'                    # type params optionnels
    r'\(([^)]*)\)',                           # paramètres
    re.MULTILINE,
)

# Contexte de classe
_CLASS_RE = re.compile(
    r'\b(?:class|mixin|extension|enum)\s+(\w+)',
    re.MULTILINE,
)

_SKIP_NAMES = {
    "main", "toString", "hashCode", "noSuchMethod",
    "runtimeType", "build", "createState",
}
_SKIP_KEYWORDS = {
    "if", "else", "for", "while", "do", "switch", "case",
    "return", "throw", "try", "catch", "finally", "new",
    "await", "yield", "assert", "var", "final", "const",
    "void", "null", "true", "false", "this", "super",
    "import", "export", "library", "part", "show", "hide",
    "as", "is", "in", "extends", "implements", "with",
    "class", "mixin", "enum", "typedef", "external",
    "abstract", "static", "late", "required", "covariant",
    "get", "set", "operator", "factory", "async", "sync",
}

_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    "constructor", "prototype", "__proto__",
}

# Mapping types Dart >> ParameterType
_DART_TYPE_MAP: dict[str, ParameterType] = {
    "int": ParameterType.INTEGER,
    "double": ParameterType.NUMBER,
    "num": ParameterType.NUMBER,
    "bool": ParameterType.BOOLEAN,
    "String": ParameterType.STRING,
}


class DartParser:
    """Extrait les fonctions/méthodes publiques de fichiers Dart via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        if any(x in path.name for x in ("_test.dart", ".g.dart", ".freezed.dart", ".gr.dart")):
            return []
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")

        cleaned = _BLOCK_COMMENT_RE.sub(" ", source)
        cleaned = _LINE_COMMENT_RE.sub("", cleaned)

        class_contexts = _build_class_contexts(cleaned)

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        for m in _FUNC_RE.finditer(cleaned):
            func_name = m.group(1)
            raw_params = m.group(2).strip()

            # Privé en Dart = commence par _
            if func_name.startswith("_"):
                continue
            if func_name in _SKIP_NAMES or func_name.lower() in _SKIP_KEYWORDS:
                continue

            class_name = _find_class_at_pos(class_contexts, m.start())
            if class_name:
                prefix = _SLUG_RE.sub("_", class_name.lower()).strip("_")
            else:
                prefix = _SLUG_RE.sub("_", path.stem.lower()).strip("_")

            func_slug = _SLUG_RE.sub("_", func_name.lower()).strip("_") or "func"
            slug = f"{prefix}_{func_slug}" if prefix else func_slug

            if slug in seen:
                continue
            seen.add(slug)

            description = _extract_dartdoc(source, m.start()) or f"{func_name}(...)"
            params = _parse_params(raw_params)

            tools.append(DiscoveredTool(
                name=slug,
                description=description,
                parameters=params,
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": func_name,
                    "class": class_name,
                    "language": "dart",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _build_class_contexts(cleaned: str) -> list[tuple[int, int, str]]:
    """Retourne (start, end, class_name) pour chaque bloc classe/mixin."""
    contexts = []
    for m in _CLASS_RE.finditer(cleaned):
        name = m.group(1)
        brace_start = cleaned.find("{", m.end())
        if brace_start == -1:
            continue
        depth, pos = 1, brace_start + 1
        while pos < len(cleaned) and depth > 0:
            if cleaned[pos] == "{":
                depth += 1
            elif cleaned[pos] == "}":
                depth -= 1
            pos += 1
        contexts.append((brace_start, pos, name))
    return contexts


def _find_class_at_pos(contexts: list[tuple[int, int, str]], pos: int) -> str:
    for start, end, name in contexts:
        if start < pos < end:
            return name
    return ""


def _extract_dartdoc(source: str, pos: int) -> str:
    """Extrait le commentaire DartDoc (///) précédant la déclaration."""
    preceding = source[max(0, pos - 600):pos]
    m = _DARTDOC_RE.search(preceding)
    if not m:
        return ""
    after = preceding[m.end():]
    if re.search(r'[;{}]', after):
        return ""
    text = m.group(0)
    text = re.sub(r'^\s*///\s?', '', text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", text).strip()[:200]


def _parse_params(raw: str) -> list[ToolParameter]:
    """
    Parse les paramètres Dart :
    - Positionnels : `Type name`
    - Nommés : `{required Type name, Type name = default}`
    - Positionnels optionnels : `[Type name, Type name = default]`
    """
    if not raw.strip():
        return []

    params: list[ToolParameter] = []

    # Détermine si les params sont nommés {} ou positionnels optionnels []
    named_match = re.search(r'\{([^}]*)\}', raw)
    optional_match = re.search(r'\[([^\]]*)\]', raw)

    # Paramètres positionnels obligatoires (avant {} ou [])
    positional_raw = raw
    if named_match:
        positional_raw = raw[:named_match.start()]
    elif optional_match:
        positional_raw = raw[:optional_match.start()]

    for part in _split_params(positional_raw):
        p = _parse_single_param(part, required=True)
        if p:
            params.append(p)

    # Paramètres nommés {}
    if named_match:
        for part in _split_params(named_match.group(1)):
            is_required = "required" in part
            part = re.sub(r"\brequired\b\s*", "", part).strip()
            p = _parse_single_param(part, required=is_required)
            if p:
                params.append(p)

    # Paramètres positionnels optionnels []
    if optional_match:
        for part in _split_params(optional_match.group(1)):
            p = _parse_single_param(part, required=False)
            if p:
                params.append(p)

    return params


def _parse_single_param(part: str, required: bool) -> ToolParameter | None:
    """Parse un paramètre individuel `Type name` ou `Type name = default`."""
    part = part.strip()
    if not part:
        return None

    # Retire les annotations @...
    part = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", part).strip()
    # Retire covariant
    part = re.sub(r"^\bcovariant\b\s*", "", part).strip()
    # Retire la valeur par défaut
    part = part.split("=")[0].strip()

    # En Dart : `Type name` (type en premier, nom en dernier)
    tokens = part.split()
    if len(tokens) < 2:
        return None

    param_name = tokens[-1]
    dart_type = " ".join(tokens[:-1]).rstrip("?")

    if param_name.startswith("_") or param_name in _SKIP_KEYWORDS:
        return None

    slug = _SLUG_RE.sub("_", param_name.lower()).strip("_") or "param"
    if slug in _RESERVED:
        slug = slug + "_"

    # Nullabilité
    full_type = " ".join(tokens[:-1])
    nullable = full_type.endswith("?")

    base = re.sub(r"<[^>]*>|\?", "", dart_type).strip()
    py_type = _DART_TYPE_MAP.get(base, ParameterType.STRING)

    return ToolParameter(
        name=slug,
        type=py_type,
        description=full_type,
        required=required and not nullable,
    )


def _split_params(raw: str) -> list[str]:
    """Divise les paramètres en gérant les génériques imbriqués."""
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
