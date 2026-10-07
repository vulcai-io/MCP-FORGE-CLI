"""
Parser Groovy pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .groovy / .gradle.

Formats supportés :
  def methodName(param1, param2) { ... }
  ReturnType methodName(Type param) { ... }
  public static methodName(Type param) { ... }
  void methodName(Type param1, Type param2 = default) { ... }

Les méthodes publiques sont extraites (public par défaut en Groovy).
Les méthodes private/protected sont ignorées.
Extrait les GroovyDoc /** */ comme description.
"""
from __future__ import annotations

import keyword as _kw
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*(?!\*).*?\*/", re.DOTALL)
_GROOVYDOC_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)

# Méthode Groovy publique (par défaut ou explicitement public/static)
_FUNC_RE = re.compile(
    r'(?:^|\n)'
    r'[ \t]*'
    r'(?![ \t]*(?:private|protected)\b)'        # pas private/protected
    r'(?:(?:public|static|final|abstract|'
    r'synchronized|@\w+(?:\([^)]*\))?)\s+)*'    # modificateurs/annotations
    r'(?:def|void|'                              # def ou type de retour
    r'(?:boolean|int|long|float|double|String|'
    r'List|Map|Set|Object|[\w<>\[\]]+))\s+'
    r'([a-zA-Z_]\w*)'                           # nom
    r'\s*\(([^)]*)\)',                           # paramètres
    re.MULTILINE,
)

# Contexte de classe
_CLASS_RE = re.compile(
    r'\b(?:class|interface|trait|enum)\s+(\w+)',
    re.MULTILINE,
)

_SKIP_NAMES = {
    "main", "run", "call", "println", "print",
    "toString", "hashCode", "equals", "clone",
}
_SKIP_KEYWORDS = {
    "if", "else", "for", "while", "switch", "return",
    "throw", "try", "catch", "finally", "new", "def",
    "void", "class", "interface", "import", "package",
}

_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    "constructor", "prototype", "__proto__",
}

_GROOVY_TYPE_MAP: dict[str, ParameterType] = {
    "int": ParameterType.INTEGER,
    "long": ParameterType.INTEGER,
    "Integer": ParameterType.INTEGER,
    "Long": ParameterType.INTEGER,
    "float": ParameterType.NUMBER,
    "double": ParameterType.NUMBER,
    "Float": ParameterType.NUMBER,
    "Double": ParameterType.NUMBER,
    "boolean": ParameterType.BOOLEAN,
    "Boolean": ParameterType.BOOLEAN,
    "String": ParameterType.STRING,
    "GString": ParameterType.STRING,
    "char": ParameterType.STRING,
}


class GroovyParser:
    """Extrait les méthodes publiques de fichiers Groovy via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        if any(x in path.name for x in ("Test", "Spec", "test_", "_test")):
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

            if func_name in _SKIP_NAMES or func_name.lower() in _SKIP_KEYWORDS:
                continue
            if func_name.startswith("_"):
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

            description = _extract_groovydoc(source, m.start()) or f"def {func_name}(...)"
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
                    "language": "groovy",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _build_class_contexts(cleaned: str) -> list[tuple[int, int, str]]:
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


def _extract_groovydoc(source: str, pos: int) -> str:
    """Extrait le GroovyDoc /** */ précédant la déclaration."""
    preceding = source[max(0, pos - 600):pos]
    matches = list(_GROOVYDOC_RE.finditer(preceding))
    if not matches:
        return ""
    last = matches[-1]
    after = preceding[last.end():]
    if re.search(r'[;{}]', after):
        return ""
    text = last.group(1)
    text = re.sub(r"\n\s*\*\s?", " ", text)
    text = re.sub(r"@\w+[^\n]*", "", text)
    return re.sub(r"\s+", " ", text).strip()[:200]


def _parse_params(raw: str) -> list[ToolParameter]:
    """Parse les paramètres Groovy : `Type name`, `def name`, `name`, `name = default`."""
    if not raw.strip():
        return []

    params: list[ToolParameter] = []
    for part in _split_params(raw):
        part = part.strip()
        if not part:
            continue

        # Retire les annotations @...
        part = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", part).strip()
        # Retire la valeur par défaut
        has_default = "=" in part
        part = part.split("=")[0].strip()

        tokens = part.split()
        if not tokens:
            continue

        # `Type name` ou `def name` >> nom = dernier token
        # `name` seul >> nom = token unique
        if len(tokens) >= 2:
            param_name = tokens[-1]
            groovy_type = tokens[-2] if tokens[-2] != "def" else "String"
        else:
            param_name = tokens[0]
            groovy_type = "String"

        if not param_name or param_name.startswith("_"):
            continue
        if param_name.lower() in _SKIP_KEYWORDS:
            continue

        slug = _SLUG_RE.sub("_", param_name.lower()).strip("_") or "param"
        if slug in _RESERVED:
            slug = slug + "_"

        py_type = _GROOVY_TYPE_MAP.get(groovy_type, ParameterType.STRING)

        params.append(ToolParameter(
            name=slug,
            type=py_type,
            description=groovy_type,
            required=not has_default,
        ))

    return params


def _split_params(raw: str) -> list[str]:
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
