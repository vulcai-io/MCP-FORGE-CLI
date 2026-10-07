"""
Parser C# pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .cs.

Formats supportés :
  public ReturnType MethodName(Type param1, Type param2)
  public static async Task<T> MethodName(int x, string y)
  public override void MethodName(params object[] args)

Seules les méthodes public sont extraites (API publique).
"""
from __future__ import annotations

import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

# XML doc comments : /// <summary>...</summary>
_XMLDOC_RE = re.compile(r'(?:[ \t]*///[^\n]*\n)+')

# Déclaration de méthode C# publique
# Gère : public [static] [async] [virtual|override|abstract|sealed|extern|new]* ReturnType Name(params)
_METHOD_RE = re.compile(
    r'^\s*\bpublic\b'                                   # public obligatoire en début de ligne
    r'(?:\s+(?:static|async|virtual|override|abstract|'
    r'sealed|extern|new|partial|unsafe|readonly))*'     # modificateurs
    r'\s+([\w$][\w$.<>\[\]?, ]*?)'                     # type de retour
    r'\s+([\w$]+)'                                      # nom de méthode
    r'\s*\(([^)]*)\)',                                  # paramètres
    re.MULTILINE,
)

_SKIP_NAMES = {
    "ToString", "GetHashCode", "Equals", "Dispose", "Finalize",
    "GetEnumerator", "GetType", "MemberwiseClone",
}
_SKIP_PREFIXES = ("get_", "set_", "add_", "remove_")

# Mots réservés Python + JS builtins
import keyword as _kw
_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    # JS builtins problématiques dans les schemas MCP
    "constructor", "prototype", "__proto__",
}

# Mapping types C# >> ParameterType
_CS_TYPE_MAP: dict[str, ParameterType] = {
    "int": ParameterType.INTEGER,
    "long": ParameterType.INTEGER,
    "short": ParameterType.INTEGER,
    "byte": ParameterType.INTEGER,
    "sbyte": ParameterType.INTEGER,
    "uint": ParameterType.INTEGER,
    "ulong": ParameterType.INTEGER,
    "ushort": ParameterType.INTEGER,
    "Int32": ParameterType.INTEGER,
    "Int64": ParameterType.INTEGER,
    "float": ParameterType.NUMBER,
    "double": ParameterType.NUMBER,
    "decimal": ParameterType.NUMBER,
    "bool": ParameterType.BOOLEAN,
    "Boolean": ParameterType.BOOLEAN,
    "string": ParameterType.STRING,
    "String": ParameterType.STRING,
    "char": ParameterType.STRING,
    "Char": ParameterType.STRING,
}


class CSharpParser:
    """Extrait les méthodes publiques de fichiers C# via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        if path.name.endswith(".Designer.cs") or path.name.endswith(".g.cs"):
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

        for m in _METHOD_RE.finditer(cleaned):
            tool = _build_tool(m, class_name, class_slug, source, relative_path, seen)
            if tool:
                tools.append(tool)

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _build_tool(
    m: re.Match,
    class_name: str,
    class_slug: str,
    source: str,
    relative_path: str,
    seen: set[str],
) -> DiscoveredTool | None:
    return_type = m.group(1).strip()
    method_name = m.group(2).strip()

    if method_name in _SKIP_NAMES:
        return None
    if any(method_name.startswith(p) for p in _SKIP_PREFIXES):
        return None
    if class_name and return_type == class_name:
        return None
    if re.search(r'\b(class|interface|enum|struct|namespace)\b', return_type):
        return None

    method_slug = _SLUG_RE.sub("_", method_name.lower()).strip("_") or "method"
    slug = f"{class_slug}_{method_slug}" if class_slug else method_slug
    if slug in seen:
        return None
    seen.add(slug)

    description = _extract_xmldoc(source, m.start()) or f"{return_type} {method_name}(...)"
    return DiscoveredTool(
        name=slug,
        description=description,
        parameters=_parse_params(m.group(3).strip()),
        tags=["codebase", relative_path],
        metadata={
            "file": relative_path,
            "function": method_name,
            "class": class_name,
            "return_type": return_type,
            "language": "csharp",
        },
    )

def _detect_class_name(source: str) -> str:
    """Extrait le nom de la classe/interface/struct principale du fichier C#."""
    cleaned = _BLOCK_COMMENT_RE.sub(" ", source)
    cleaned = _XMLDOC_RE.sub(" ", cleaned)
    cleaned = _LINE_COMMENT_RE.sub("", cleaned)
    for m in re.finditer(
        r'\b(?:public\s+)?(?:partial\s+)?(?:class|interface|struct|record)\s+([\w$]+)',
        cleaned,
    ):
        name = m.group(1)
        if len(name) >= 2 and name[0].isupper():
            return name
    return ""


def _extract_xmldoc(source: str, pos: int) -> str:
    """Extrait le commentaire XML doc (///) précédant la déclaration."""
    preceding = source[max(0, pos - 800):pos]
    matches = list(_XMLDOC_RE.finditer(preceding))
    if not matches:
        return ""
    last = matches[-1]
    # Vérifie qu'il n'y a pas de code entre le doc et la méthode
    after = preceding[last.end():]
    if re.search(r'[;{}]', after):
        return ""
    text = last.group(0)
    # Retire les /// et les balises XML
    text = re.sub(r'^\s*///\s?', '', text, flags=re.MULTILINE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:200]


def _parse_params(raw: str) -> list[ToolParameter]:
    """Parse les paramètres C# : gère `this`, `ref`, `out`, `params`, valeurs par défaut."""
    if not raw.strip():
        return []

    params: list[ToolParameter] = []
    for part in _split_params(raw):
        part = part.strip()
        if not part:
            continue

        # Retire les attributs [...] (ex: [FromBody] string s) — `+` et non
        # `*` est important : un type tableau (`double[]`) a des crochets
        # VIDES, contrairement à un attribut qui a toujours un contenu ;
        # avec `*` ce regex fusionnait "double[] numbers" en "doublenumbers"
        # (un seul token), faisant disparaître silencieusement le paramètre.
        part = re.sub(r'\[[^\]]+\]\s*', '', part).strip()
        # Retire this, ref, out, in, params
        part = re.sub(r'\b(this|ref|out|in|params)\s+', '', part).strip()
        # Retire la valeur par défaut = ...
        part = re.sub(r'\s*=\s*.+$', '', part).strip()

        tokens = part.split()
        if len(tokens) < 2:
            continue

        param_name = tokens[-1].strip("[]")
        cs_type = " ".join(tokens[:-1]).rstrip("?")  # retire nullable ?
        is_array = "[]" in cs_type or re.match(r'^(List|IList|IEnumerable|ICollection)<', cs_type)
        base_type = re.sub(r'<[^>]*>', '', cs_type).replace("[]", "").strip().split(".")[-1]
        items_py_type = _CS_TYPE_MAP.get(base_type, ParameterType.STRING)
        py_type = ParameterType.ARRAY if is_array else items_py_type

        slug = _SLUG_RE.sub("_", param_name.lower()).strip("_") or "param"
        if slug in _RESERVED:
            slug = slug + "_"

        params.append(ToolParameter(
            name=slug,
            type=py_type,
            items_type=items_py_type if is_array else None,
            description=cs_type,
            required=True,
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
