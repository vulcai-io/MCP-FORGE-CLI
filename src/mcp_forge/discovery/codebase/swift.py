"""
Parser Swift pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .swift.

Formats supportés :
  public func functionName(param: Type) -> ReturnType
  open func methodName(label param: Type) -> ReturnType
  public static func methodName(_ param: Type) -> ReturnType
  public mutating func methodName(a: Type, b: Type = default)

Toute visibilité est extraite SAUF private/fileprivate (public, open,
internal implicite — i.e. sans modificateur — inclus).
Gère les argument labels Swift (externalLabel internalParam: Type).
"""
from __future__ import annotations

import keyword as _kw
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*(?!\*).*?\*/", re.DOTALL)
# DocC : /// lignes consécutives
_DOCC_RE = re.compile(r'(?:[ \t]*///[^\n]*\n)+')

# Fonction Swift — toute visibilité SAUF private/fileprivate (voir filtre
# dans extract() ci-dessous). `public`/`open` ne sont donc plus obligatoires :
# un module Swift à fichier unique (script, utilitaire) n'a généralement
# aucun modificateur de visibilité explicite — Swift utilise `internal` par
# défaut, qui n'a pas de mot-clé propre. Exiger public/open laissait
# passer 0 fonction pour ce cas très courant.
_FUNC_RE = re.compile(
    r'(?:@\w+(?:\([^)]*\))?\s+)*'          # attributs optionnels (@discardableResult...)
    r'((?:\b(?:public|open|internal|private|fileprivate|static|class|'
    r'mutating|nonmutating|override|required|convenience|final|dynamic|lazy)\b\s+)*)'
    r'func\s+'
    r'([\w`]+)'                             # nom
    r'(?:<[^>]*>)?'                         # generics
    r'\s*\(([^)]*)\)',                      # paramètres
    re.MULTILINE,
)

# Contexte de classe/struct/extension
_TYPE_RE = re.compile(
    r'\b(?:class|struct|enum|actor|extension)\s+([\w.]+)',
    re.MULTILINE,
)

_SKIP_NAMES = {"init", "deinit"}
_SKIP_PREFIXES = ("_",)

_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    "constructor", "prototype", "__proto__",
}

# Mapping types Swift >> ParameterType
_SWIFT_TYPE_MAP: dict[str, ParameterType] = {
    "Int": ParameterType.INTEGER,
    "Int8": ParameterType.INTEGER,
    "Int16": ParameterType.INTEGER,
    "Int32": ParameterType.INTEGER,
    "Int64": ParameterType.INTEGER,
    "UInt": ParameterType.INTEGER,
    "UInt8": ParameterType.INTEGER,
    "UInt16": ParameterType.INTEGER,
    "UInt32": ParameterType.INTEGER,
    "UInt64": ParameterType.INTEGER,
    "Float": ParameterType.NUMBER,
    "Double": ParameterType.NUMBER,
    "Float80": ParameterType.NUMBER,
    "Bool": ParameterType.BOOLEAN,
    "String": ParameterType.STRING,
    "Character": ParameterType.STRING,
    "Substring": ParameterType.STRING,
}


class SwiftParser:
    """Extrait les fonctions public/open de fichiers Swift via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        if "Test" in path.name or "Spec" in path.name or "Mock" in path.name:
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
            modifiers = m.group(1)
            func_name = m.group(2).strip("`")
            raw_params = m.group(3).strip()

            if func_name in _SKIP_NAMES:
                continue
            if any(func_name.startswith(p) for p in _SKIP_PREFIXES):
                continue
            if re.search(r'\b(private|fileprivate)\b', modifiers):
                continue

            type_name = _find_type_at_pos(type_contexts, m.start())
            prefix = _SLUG_RE.sub("_", type_name.lower()).strip("_") if type_name else \
                     _SLUG_RE.sub("_", path.stem.lower()).strip("_")

            func_slug = _SLUG_RE.sub("_", func_name.lower()).strip("_") or "func"
            slug = f"{prefix}_{func_slug}" if prefix else func_slug

            if slug in seen:
                continue
            seen.add(slug)

            description = _extract_docc(source, m.start()) or f"func {func_name}(...)"
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
                    "language": "swift",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _build_type_contexts(cleaned: str) -> list[tuple[int, int, str]]:
    """Retourne (start, end, type_name) pour chaque bloc class/struct/extension."""
    contexts = []
    for m in _TYPE_RE.finditer(cleaned):
        name = m.group(1).split(".")[-1]
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


def _extract_docc(source: str, pos: int) -> str:
    """Extrait le commentaire DocC (///) précédant la déclaration."""
    preceding = source[max(0, pos - 600):pos]
    m = _DOCC_RE.search(preceding)
    if not m:
        # Fallback : /** */
        from mcp_forge.discovery.codebase.kotlin import _KDOC_RE  # même format
        matches = list(_KDOC_RE.finditer(preceding))
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

    after = preceding[m.end():]
    if re.search(r'[;{}]', after):
        return ""
    text = m.group(0)
    text = re.sub(r'^\s*///\s?', '', text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", text).strip()[:200]


def _parse_params(raw: str) -> list[ToolParameter]:
    """
    Parse les paramètres Swift avec argument labels.
    `externalLabel internalParam: Type` >> nom = externalLabel (ou internalParam si _ )
    """
    if not raw.strip():
        return []

    params: list[ToolParameter] = []
    for part in _split_params(raw):
        part = part.strip()
        if not part:
            continue

        # Retire les attributs @...
        part = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", part).strip()
        # Retire inout
        part = re.sub(r"\binout\s+", "", part).strip()
        # Retire la valeur par défaut
        part = part.split("=")[0].strip()

        if ":" not in part:
            continue

        label_and_name, swift_type = part.split(":", 1)
        swift_type = swift_type.strip()
        tokens = label_and_name.strip().split()

        if not tokens:
            continue

        # Détermine le nom du paramètre MCP
        if len(tokens) == 1:
            # Pas de label externe >> nom = token
            param_name = tokens[0]
        else:
            # external internal : Type >> utilise external (sauf si _)
            external, internal = tokens[0], tokens[1]
            param_name = internal if external == "_" else external

        if not param_name or param_name == "_":
            continue

        slug = _SLUG_RE.sub("_", param_name.lower()).strip("_") or "param"
        if slug in _RESERVED:
            slug = slug + "_"

        optional = swift_type.endswith("?")
        base = re.sub(r"<[^>]*>", "", swift_type).rstrip("?").strip()
        items_type = None
        # Syntaxe tableau Swift : `[Double]`, pas de générique `Array<Double>`
        # — sans ce cas, un paramètre comme `_ numbers: [Double]` tombait
        # dans le défaut STRING (le lookup sur "[Double]" tel quel échoue).
        if base.startswith("[") and base.endswith("]"):
            py_type = ParameterType.ARRAY
            items_type = _SWIFT_TYPE_MAP.get(base[1:-1].strip())
        else:
            py_type = _SWIFT_TYPE_MAP.get(base, ParameterType.STRING)

        params.append(ToolParameter(
            name=slug,
            type=py_type,
            items_type=items_type,
            description=swift_type,
            required=not optional,
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
