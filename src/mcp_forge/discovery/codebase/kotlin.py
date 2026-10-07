"""
Parser Kotlin pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .kt / .kts.

Formats supportés :
  fun functionName(param: Type): ReturnType
  suspend fun functionName(param: Type, param2: Type = default): ReturnType
  fun TypeName.extensionFun(param: Type): ReturnType
  override fun methodName(param: Type): ReturnType

Les fonctions sont publiques par défaut en Kotlin.
Seules les fonctions private/protected sont ignorées.
"""
from __future__ import annotations

import keyword as _kw
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*(?!\*).*?\*/", re.DOTALL)
_KDOC_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)

# Fonction Kotlin (publique par défaut, ou explicitement public/internal)
# Ignore private et protected
_FUNC_RE = re.compile(
    r'(?:^|\n)'
    r'[ \t]*'
    r'(?!.*\b(?:private|protected)\b)'      # pas private/protected
    r'(?:(?:public|internal|override|operator|infix|inline|'
    r'suspend|external|actual|expect|tailrec|crossinline|noinline)\s+)*'
    r'fun\s+'
    r'(?:<[^>]*>\s*)?'                       # type params optionnels
    r'(?:([\w.]+)\.)?' 			             # receiver optionnel (extension)
    r'([\w`]+)'                              # nom de fonction (backtick possible)
    r'\s*(?:<[^>]*>)?\s*'                   # type params de méthode
    r'\(([^)]*)\)',                          # paramètres
    re.MULTILINE,
)

# Contexte de classe/object/interface
_CLASS_RE = re.compile(
    r'\b(?:class|object|interface|companion\s+object)\s+([\w`]+)?',
    re.MULTILINE,
)

_SKIP_NAMES = {"main", "init", "equals", "hashCode", "toString", "copy"}
_SKIP_PREFIXES = ("_",)

_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    "constructor", "prototype", "__proto__",
}

# Mapping types Kotlin >> ParameterType
_KT_TYPE_MAP: dict[str, ParameterType] = {
    "Int": ParameterType.INTEGER,
    "Long": ParameterType.INTEGER,
    "Short": ParameterType.INTEGER,
    "Byte": ParameterType.INTEGER,
    "UInt": ParameterType.INTEGER,
    "ULong": ParameterType.INTEGER,
    "Float": ParameterType.NUMBER,
    "Double": ParameterType.NUMBER,
    "Boolean": ParameterType.BOOLEAN,
    "String": ParameterType.STRING,
    "Char": ParameterType.STRING,
    "Int?": ParameterType.INTEGER,
    "Long?": ParameterType.INTEGER,
    "Float?": ParameterType.NUMBER,
    "Double?": ParameterType.NUMBER,
    "Boolean?": ParameterType.BOOLEAN,
    "String?": ParameterType.STRING,
}


class KotlinParser:
    """Extrait les fonctions publiques de fichiers Kotlin via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        if "Test" in path.name or "Spec" in path.name or path.name.endswith("Test.kt"):
            return []
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")

        cleaned = _BLOCK_COMMENT_RE.sub(" ", source)
        cleaned = _LINE_COMMENT_RE.sub("", cleaned)

        impl_contexts = _build_class_contexts(cleaned)

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        for m in _FUNC_RE.finditer(cleaned):
            receiver = m.group(1) or ""
            func_name = m.group(2).strip("`")
            raw_params = m.group(3).strip()

            if func_name in _SKIP_NAMES:
                continue
            if any(func_name.startswith(p) for p in _SKIP_PREFIXES):
                continue

            # Détermine le préfixe : receiver > classe englobante > module
            if receiver:
                prefix = _SLUG_RE.sub("_", receiver.lower()).strip("_")
            else:
                class_name = _find_class_at_pos(impl_contexts, m.start())
                prefix = _SLUG_RE.sub("_", class_name.lower()).strip("_") if class_name else \
                         _SLUG_RE.sub("_", path.stem.lower()).strip("_")

            func_slug = _SLUG_RE.sub("_", func_name.lower()).strip("_") or "func"
            slug = f"{prefix}_{func_slug}" if prefix else func_slug

            if slug in seen:
                continue
            seen.add(slug)

            description = _extract_kdoc(source, m.start()) or f"fun {func_name}(...)"
            params = _parse_params(raw_params)

            tools.append(DiscoveredTool(
                name=slug,
                description=description,
                parameters=params,
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": func_name,
                    "receiver": receiver,
                    "language": "kotlin",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _build_class_contexts(cleaned: str) -> list[tuple[int, int, str]]:
    """Retourne une liste (start, end, class_name) pour chaque bloc classe/object."""
    contexts = []
    for m in _CLASS_RE.finditer(cleaned):
        name = (m.group(1) or "").strip("`")
        if not name:
            continue
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
    """Retourne le nom de la classe englobant la position."""
    for start, end, name in contexts:
        if start < pos < end:
            return name
    return ""


def _extract_kdoc(source: str, pos: int) -> str:
    """Extrait le commentaire KDoc précédant la déclaration."""
    preceding = source[max(0, pos - 600):pos]
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
    text = re.sub(r"\s+", " ", text).strip()
    return text[:200]


def _parse_params(raw: str) -> list[ToolParameter]:
    """Parse les paramètres Kotlin : `name: Type`, `name: Type = default`."""
    if not raw.strip():
        return []

    params: list[ToolParameter] = []
    for part in _split_params(raw):
        part = part.strip()
        if not part:
            continue

        # Retire les annotations @...
        part = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", part).strip()
        # Retire vararg
        part = re.sub(r"^vararg\s+", "", part).strip()
        # Retire la valeur par défaut
        part = part.split("=")[0].strip()

        if ":" not in part:
            continue

        param_name, kt_type = part.split(":", 1)
        param_name = param_name.strip()
        kt_type = kt_type.strip()

        if not param_name:
            continue

        slug = _SLUG_RE.sub("_", param_name.lower()).strip("_") or "param"
        if slug in _RESERVED:
            slug = slug + "_"

        # Type de base (sans génériques ni nullable)
        base = re.sub(r"<[^>]*>", "", kt_type).strip()
        py_type = _KT_TYPE_MAP.get(base, ParameterType.STRING)

        optional = kt_type.endswith("?")
        params.append(ToolParameter(
            name=slug,
            type=py_type,
            description=kt_type,
            required=not optional,
        ))

    return params


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
