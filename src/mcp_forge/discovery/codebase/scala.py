"""
Parser Scala pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .scala.

Formats supportés :
  def methodName(param: Type): ReturnType
  def methodName[T](param: T): T
  override def methodName(param: Type): ReturnType
  def methodName(param: Type)(implicit ev: Evidence): ReturnType

Les méthodes publiques (par défaut en Scala) sont extraites.
Les méthodes private/protected sont ignorées.
Gère les contextes class/object/trait/case class.
"""
from __future__ import annotations

import keyword as _kw
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*(?!\*).*?\*/", re.DOTALL)
_SCALADOC_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)

# def en Scala — public par défaut, ignore private/protected
_FUNC_RE = re.compile(
    r'(?:^|\n)'
    r'[ \t]*'
    r'(?![ \t]*(?:private|protected)\b)'    # pas private/protected
    r'(?:(?:override|final|abstract|implicit|'
    r'inline|transparent|given|lazy)[ \t]+)*'
    r'def[ \t]+'
    r'([`\w]+(?:_=)?)'                       # nom (peut finir par _= pour setter)
    r'(?:\[(?:[^\[\]]|\[[^\[\]]*\])*\])?'   # type params optionnels
    r'[ \t]*\(([^)]*)\)',                    # premier groupe de paramètres
    re.MULTILINE,
)

# Contexte class/object/trait/case class/case object
_TYPE_RE = re.compile(
    r'\b(?:case\s+)?(?:class|object|trait)\s+([`\w]+)',
    re.MULTILINE,
)

_SKIP_NAMES = {
    "apply", "unapply", "unapplySeq", "copy", "equals",
    "hashCode", "toString", "canEqual", "productArity",
    "productElement", "productIterator", "productPrefix",
}
_SKIP_PREFIXES = ("_",)

_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    "constructor", "prototype", "__proto__",
}

# Mapping types Scala >> ParameterType
_SCALA_TYPE_MAP: dict[str, ParameterType] = {
    "Int": ParameterType.INTEGER,
    "Long": ParameterType.INTEGER,
    "Short": ParameterType.INTEGER,
    "Byte": ParameterType.INTEGER,
    "BigInt": ParameterType.INTEGER,
    "Float": ParameterType.NUMBER,
    "Double": ParameterType.NUMBER,
    "BigDecimal": ParameterType.NUMBER,
    "Boolean": ParameterType.BOOLEAN,
    "String": ParameterType.STRING,
    "Char": ParameterType.STRING,
}


class ScalaParser:
    """Extrait les méthodes publiques de fichiers Scala via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        if any(x in path.name for x in ("Test", "Spec", "Suite", "Bench")):
            return []
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")

        cleaned = _BLOCK_COMMENT_RE.sub(" ", source)
        cleaned = _LINE_COMMENT_RE.sub("", cleaned)

        type_contexts = _build_type_contexts(cleaned)

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        for m in _FUNC_RE.finditer(cleaned):
            func_name = m.group(1).strip("`")
            raw_params = m.group(2).strip()

            if func_name in _SKIP_NAMES:
                continue
            if any(func_name.startswith(p) for p in _SKIP_PREFIXES):
                continue
            # Ignore les setters (_=)
            if func_name.endswith("_="):
                continue

            type_name = _find_type_at_pos(type_contexts, m.start())
            prefix = _SLUG_RE.sub("_", type_name.lower()).strip("_") if type_name else \
                     _SLUG_RE.sub("_", path.stem.lower()).strip("_")

            func_slug = _SLUG_RE.sub("_", func_name.lower()).strip("_") or "def"
            slug = f"{prefix}_{func_slug}" if prefix else func_slug

            if slug in seen:
                continue
            seen.add(slug)

            description = _extract_scaladoc(source, m.start()) or f"def {func_name}(...)"
            params = _parse_params(raw_params)

            tools.append(DiscoveredTool(
                name=slug,
                description=description,
                parameters=params,
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": func_name,
                    "type": type_name,
                    "language": "scala",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _build_type_contexts(cleaned: str) -> list[tuple[int, int, str]]:
    """Retourne (start, end, type_name) pour chaque bloc class/object/trait."""
    contexts = []
    for m in _TYPE_RE.finditer(cleaned):
        name = m.group(1).strip("`")
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


def _find_type_at_pos(contexts: list[tuple[int, int, str]], pos: int) -> str:
    for start, end, name in contexts:
        if start < pos < end:
            return name
    return ""


def _extract_scaladoc(source: str, pos: int) -> str:
    """Extrait le commentaire ScalaDoc (/** */) précédant la déclaration."""
    preceding = source[max(0, pos - 600):pos]
    matches = list(_SCALADOC_RE.finditer(preceding))
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
    """Parse les paramètres Scala : `name: Type`, `name: Type = default`, `implicit name: Type`."""
    if not raw.strip():
        return []

    params: list[ToolParameter] = []
    for part in _split_params(raw):
        part = part.strip()
        if not part:
            continue

        # Retire implicit / using / given
        part = re.sub(r"^\s*(?:implicit|using|given)\s+", "", part).strip()
        # Retire les annotations @...
        part = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", part).strip()
        # Retire la valeur par défaut
        part = part.split("=")[0].strip()

        if ":" not in part:
            continue

        param_name, scala_type = part.split(":", 1)
        param_name = param_name.strip().strip("`")
        scala_type = scala_type.strip()

        if not param_name or param_name == "_":
            continue

        slug = _SLUG_RE.sub("_", param_name.lower()).strip("_") or "param"
        if slug in _RESERVED:
            slug = slug + "_"

        # Type de base (sans génériques ni Option[])
        optional = scala_type.startswith("Option[") or scala_type.endswith("?")
        base = re.sub(r"Option\[([^\]]+)\]", r"\1", scala_type)
        base = re.sub(r"<[^>]*>|\[[^\]]*\]", "", base).strip()
        py_type = _SCALA_TYPE_MAP.get(base, ParameterType.STRING)

        params.append(ToolParameter(
            name=slug,
            type=py_type,
            description=scala_type,
            required=not optional,
        ))

    return params


def _split_params(raw: str) -> list[str]:
    """Divise les paramètres en gérant les génériques et parenthèses imbriquées."""
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
