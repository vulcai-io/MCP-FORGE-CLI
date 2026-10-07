"""
Parser PHP pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .php.

Formats supportés :
  public function methodName(Type $param): ReturnType
  public static function methodName($param): ReturnType
  function functionName(string $param, int $x): ReturnType
  public function method(?string $param, int|float $x): void

Extrait les fonctions globales et les méthodes public/protected.
"""
from __future__ import annotations

import keyword as _kw
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_LINE_COMMENT_RE = re.compile(r"//[^\n]*|#[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*(?!\*).*?\*/", re.DOTALL)
_PHPDOC_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)

# Méthode de classe public/protected
_METHOD_RE = re.compile(
    r'^\s*(?:(?:public|protected|static|abstract|final|readonly)\s+)*'
    r'(?:public|protected)\s+'
    r'(?:static\s+)?'
    r'function\s+'
    r'([\w]+)'                      # nom
    r'\s*\(([^)]*)\)'              # paramètres
    r'(?:\s*:\s*[\w\\|?]+)?',      # type de retour optionnel
    re.MULTILINE,
)

# Fonction globale (hors classe)
_GLOBAL_FUNC_RE = re.compile(
    r'^function\s+'
    r'([\w]+)'                      # nom
    r'\s*\(([^)]*)\)'              # paramètres
    r'(?:\s*:\s*[\w\\|?]+)?',      # type de retour optionnel
    re.MULTILINE,
)

# Méthodes magiques à ignorer
_SKIP_NAMES = {
    "__construct", "__destruct", "__call", "__callStatic",
    "__get", "__set", "__isset", "__unset", "__sleep",
    "__wakeup", "__serialize", "__unserialize", "__toString",
    "__invoke", "__set_state", "__clone", "__debugInfo",
}
_SKIP_PREFIXES = ("_",)

_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    "constructor", "prototype", "__proto__",
}

# Mapping types PHP >> ParameterType
_PHP_TYPE_MAP: dict[str, ParameterType] = {
    "int": ParameterType.INTEGER,
    "integer": ParameterType.INTEGER,
    "float": ParameterType.NUMBER,
    "double": ParameterType.NUMBER,
    "bool": ParameterType.BOOLEAN,
    "boolean": ParameterType.BOOLEAN,
    "string": ParameterType.STRING,
    "str": ParameterType.STRING,
}


class PhpParser:
    """Extrait les fonctions/méthodes publiques de fichiers PHP via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        if "test" in path.name.lower() or "spec" in path.name.lower():
            return []
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")
        class_name = _detect_class_name(source)

        cleaned = _BLOCK_COMMENT_RE.sub(" ", source)
        cleaned = _LINE_COMMENT_RE.sub("", cleaned)

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        class_slug = _SLUG_RE.sub("_", class_name.lower()).strip("_") if class_name else ""

        # Méthodes de classe
        for m in _METHOD_RE.finditer(cleaned):
            tool = _build_tool(m, class_slug, source, relative_path, seen, class_name)
            if tool:
                tools.append(tool)

        # Fonctions globales (seulement si pas dans une classe)
        if not class_name:
            for m in _GLOBAL_FUNC_RE.finditer(cleaned):
                module_slug = _SLUG_RE.sub("_", path.stem.lower()).strip("_")
                tool = _build_tool(m, module_slug, source, relative_path, seen, "")
                if tool:
                    tools.append(tool)

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _build_tool(
    m: re.Match,
    prefix: str,
    source: str,
    relative_path: str,
    seen: set[str],
    class_name: str,
) -> DiscoveredTool | None:
    func_name = m.group(1)
    raw_params = m.group(2).strip()

    if func_name in _SKIP_NAMES:
        return None
    if any(func_name.startswith(p) for p in _SKIP_PREFIXES):
        return None

    func_slug = _SLUG_RE.sub("_", func_name.lower()).strip("_") or "func"
    slug = f"{prefix}_{func_slug}" if prefix else func_slug

    if slug in seen:
        return None
    seen.add(slug)

    description = _extract_phpdoc(source, m.start()) or f"function {func_name}(...)"
    return DiscoveredTool(
        name=slug,
        description=description,
        parameters=_parse_params(raw_params),
        tags=["codebase", relative_path],
        metadata={
            "file": relative_path,
            "function": func_name,
            "class": class_name,
            "language": "php",
        },
    )


def _detect_class_name(source: str) -> str:
    """Extrait le nom de la classe principale du fichier PHP."""
    cleaned = _PHPDOC_RE.sub(" ", source)
    cleaned = _BLOCK_COMMENT_RE.sub(" ", cleaned)
    cleaned = _LINE_COMMENT_RE.sub("", cleaned)
    for m in re.finditer(r'\b(?:class|interface|trait|enum)\s+([\w]+)', cleaned):
        name = m.group(1)
        if len(name) >= 2:
            return name
    return ""


def _extract_phpdoc(source: str, pos: int) -> str:
    """Extrait le PHPDoc précédant la déclaration."""
    preceding = source[max(0, pos - 800):pos]
    matches = list(_PHPDOC_RE.finditer(preceding))
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
    # Remplace les backslashes (namespaces PHP) pour éviter les SyntaxWarning Python
    text = text.replace("\\", "/")
    return text[:200]


def _parse_params(raw: str) -> list[ToolParameter]:
    """Parse les paramètres PHP : `Type $name`, `?Type $name = default`."""
    if not raw.strip():
        return []
    return [p for part in _split_params(raw) if (p := _parse_single_param(part)) is not None]


def _parse_single_param(part: str) -> ToolParameter | None:
    """Parse un seul paramètre PHP et retourne un ToolParameter ou None."""
    part = part.strip()
    if not part:
        return None
    part = re.sub(r"#\[[^\]]*\]\s*", "", part).strip()
    part = re.sub(r"\b(readonly|public|private|protected)\s+", "", part).strip()
    part = re.sub(r"\s*=\s*.+$", "", part).strip()
    part = part.lstrip(".")

    tokens = part.split()
    if not tokens:
        return None

    param_name = next((t.lstrip("$").rstrip(",") for t in reversed(tokens) if t.startswith("$")), "")
    if not param_name:
        return None

    php_type = " ".join(t for t in tokens if not t.startswith("$")).lstrip("?")
    base = php_type.split("|")[0].split("\\")[-1].strip()
    py_type = _PHP_TYPE_MAP.get(base, ParameterType.STRING)

    slug = _SLUG_RE.sub("_", param_name.lower()).strip("_") or "param"
    if slug in _RESERVED:
        slug = slug + "_"

    return ToolParameter(name=slug, type=py_type, description=php_type or "mixed", required=True)


def _split_params(raw: str) -> list[str]:
    """Divise les paramètres en gérant les types union et tableaux."""
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
