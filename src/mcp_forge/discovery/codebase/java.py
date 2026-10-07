"""
Parser Java pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .java.

Formats supportés :
  public ReturnType methodName(Type a, Type b)
  public static List<String> methodName(int x) throws IOException
  @Override public void method(String s)

Seules les méthodes public / protected sont extraites (API publique).
"""
from __future__ import annotations

import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Retire les commentaires Java de ligne et bloc (non-Javadoc)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*(?!\*).*?\*/", re.DOTALL)

# Javadoc /** ... */
_JAVADOC_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)

# Détection de méthode Java publique/protégée
# Gère : modificateurs (public, protected, static, final, synchronized, abstract, native)
#        annotations (@Override etc.) avant les modificateurs
#        type de retour (avec génériques)
#        nom de méthode
#        paramètres
#        clause throws (optionnelle)
_METHOD_RE = re.compile(
    r'(?:@\w+(?:\([^)]*\))?\s+)*'              # annotations optionnelles
    r'\b(public|protected)\b'                    # public ou protected (obligatoire)
    r'((?:\s+(?:static|final|synchronized|'
    r'abstract|native|default|strictfp))*)'      # modificateurs optionnels (capturés : "static" y est détecté)
    r'\s+((?:[\w$][\w$.<>\[\], ]*?)\s+)'        # type de retour (avec génériques)
    r'([\w$]+)'                                  # nom de méthode
    r'\s*\(([^)]*)\)'                            # paramètres
    r'(?:\s+throws\s+[\w., ]+)?'                 # throws optionnel
    r'\s*(?:\{|;)',                              # corps { ou ; (méthode abstraite/interface)
    re.MULTILINE,
)

# Noms à ignorer (constructeurs détectés comme méthodes, mots-clés)
_SKIP_NAMES = {
    "if", "for", "while", "switch", "return", "new", "assert", "main",
    "toString", "hashCode", "equals", "clone", "finalize",
}

import keyword as _kw
_PY_KEYWORDS = set(_kw.kwlist + _kw.softkwlist) | {
    # JS builtins problématiques dans les schemas MCP
    "constructor", "prototype", "__proto__",
}

# Mapping types Java >> Python/ctypes
_JAVA_TYPE_MAP: dict[str, ParameterType] = {
    "int": ParameterType.INTEGER,
    "long": ParameterType.INTEGER,
    "short": ParameterType.INTEGER,
    "byte": ParameterType.INTEGER,
    "float": ParameterType.NUMBER,
    "double": ParameterType.NUMBER,
    "boolean": ParameterType.BOOLEAN,
    "bool": ParameterType.BOOLEAN,
    "Integer": ParameterType.INTEGER,
    "Long": ParameterType.INTEGER,
    "Short": ParameterType.INTEGER,
    "Float": ParameterType.NUMBER,
    "Double": ParameterType.NUMBER,
    "Boolean": ParameterType.BOOLEAN,
    "String": ParameterType.STRING,
    "char": ParameterType.STRING,
    "Character": ParameterType.STRING,
}


class JavaParser:
    """Extrait les méthodes publiques/protégées de fichiers Java via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")
        class_name = _detect_class_name(source)

        # Retire les commentaires non-Javadoc pour le parsing des méthodes
        cleaned = _BLOCK_COMMENT_RE.sub(" ", source)
        cleaned = _LINE_COMMENT_RE.sub("", cleaned)

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        for m in _METHOD_RE.finditer(cleaned):
            is_static = "static" in m.group(2)
            return_type = m.group(3).strip()
            method_name = m.group(4).strip()
            raw_params = m.group(5).strip()

            # Filtres
            if method_name in _SKIP_NAMES:
                continue
            # Ignore si le type de retour ressemble à un nom de classe (constructeur)
            if class_name and return_type.rstrip() == class_name:
                continue
            # Ignore getters/setters triviaux si souhaité (optionnel - on les garde)

            method_slug = _SLUG_RE.sub("_", method_name.lower()).strip("_") or "method"
            class_slug = _SLUG_RE.sub("_", class_name.lower()).strip("_") if class_name else ""
            slug = f"{class_slug}_{method_slug}" if class_slug else method_slug
            if slug in seen:
                continue
            seen.add(slug)

            # Javadoc juste avant dans le source original
            pos = m.start()
            description = _extract_javadoc(source, pos) or f"{return_type} {method_name}(...)"

            params = _parse_params(raw_params)
            # Les types Java bruts sont dupliqués ici (pas uniquement sur
            # `param.description`, voir `_parse_params`) : l'étape
            # d'enrichissement LLM réécrit `param.description` en texte
            # humain pour la doc (`param.description = enriched[...]`,
            # mcp_forge/enrichment/llm.py) — un pilote d'exécution qui s'y
            # fierait recevrait une phrase descriptive au lieu du vrai type
            # Java ("int", "double[]"...) dès que l'enrichissement tourne.
            java_param_types = [p.description for p in params]

            tools.append(DiscoveredTool(
                name=slug,
                description=description,
                parameters=params,
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": method_name,
                    "class": class_name,
                    "return_type": return_type,
                    "is_static": is_static,
                    "java_param_types": java_param_types,
                    "language": "java",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_params(raw: str) -> list[ToolParameter]:
    """Convertit une liste de paramètres Java en ToolParameter."""
    if not raw.strip():
        return []
    params: list[ToolParameter] = []
    for part in _split_params(raw):
        part = part.strip()
        if not part:
            continue
        # Retire les annotations sur le paramètre (@NotNull String name)
        part = re.sub(r"@\w+(?:\([^)]*\))?\s+", "", part).strip()
        # Retire final
        part = re.sub(r"\bfinal\s+", "", part).strip()
        # Varargs : String... args >> String[] args
        part = part.replace("...", "[]")
        # Sépare type et nom : dernier token = nom
        tokens = part.split()
        if len(tokens) < 2:
            continue
        param_name_raw = tokens[-1].rstrip(",")
        param_name = param_name_raw.strip("[]")
        java_type = " ".join(tokens[:-1])
        # Tableau (`double[] numbers` ou style C `double numbers[]`) ou
        # collection générique (`List<Double>`) >> ARRAY, pas le type de
        # l'élément — sinon `double[] numbers` finissait typé NUMBER (un
        # seul float) côté MCP au lieu d'une liste, rendant l'outil
        # inutilisable pour tout appelant qui passe une vraie liste.
        has_brackets = "[]" in java_type or param_name_raw.endswith("[]")
        # Type de base (sans génériques ni tableaux)
        base_type = re.sub(r"<[^>]*>", "", java_type).replace("[]", "").strip().split(".")[-1]
        is_collection = base_type in ("List", "ArrayList", "LinkedList", "Collection", "Set", "HashSet", "Iterable")
        items_type = None
        if has_brackets:
            py_type = ParameterType.ARRAY
            # base_type a déjà perdu son "[]" ci-dessus : c'est directement
            # le type de l'élément (ex: "double" pour `double[] numbers`).
            items_type = _JAVA_TYPE_MAP.get(base_type)
        elif is_collection:
            py_type = ParameterType.ARRAY
            generic_match = re.search(r"<\s*([\w.]+)\s*>", java_type)
            if generic_match:
                items_type = _JAVA_TYPE_MAP.get(generic_match.group(1).split(".")[-1])
        else:
            py_type = _JAVA_TYPE_MAP.get(base_type, ParameterType.STRING)

        slug = re.sub(r"[^a-z0-9_]", "_", param_name.lower()).strip("_") or "param"
        if slug in _PY_KEYWORDS:
            slug = slug + "_"

        params.append(ToolParameter(
            name=slug,
            type=py_type,
            items_type=items_type,
            description=java_type,
            required=True,
        ))
    return params


def _split_params(raw: str) -> list[str]:
    """Divise les paramètres en gérant les génériques imbriqués (List<Map<K,V>>)."""
    parts, depth, current = [], 0, []
    for ch in raw:
        if ch in ("<", "(", "["):
            depth += 1
            current.append(ch)
        elif ch in (">", ")", "]"):
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


def _extract_javadoc(source: str, pos: int) -> str:
    """Cherche un commentaire Javadoc dans les 800 caractères précédant pos."""
    preceding = source[max(0, pos - 800):pos]
    matches = list(_JAVADOC_RE.finditer(preceding))
    if not matches:
        return ""
    last = matches[-1]
    # Vérifie que le Javadoc est juste avant (pas séparé par du code)
    after_javadoc = preceding[last.end():]
    if re.search(r'[;{}]', after_javadoc):
        return ""
    text = last.group(1).strip()
    # Nettoie les * en début de ligne et les tags Javadoc
    text = re.sub(r"\n\s*\*\s?", " ", text)
    text = re.sub(r"@\w+[^\n]*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:200]


def _detect_class_name(source: str) -> str:
    """Extrait le nom de la classe principale du fichier Java."""
    # Retire les Javadoc et commentaires pour éviter les faux positifs dans les exemples de code
    cleaned = _JAVADOC_RE.sub(" ", source)
    cleaned = _BLOCK_COMMENT_RE.sub(" ", cleaned)
    cleaned = _LINE_COMMENT_RE.sub("", cleaned)
    # Cherche toutes les déclarations de classe/interface et prend la première top-level
    for m in re.finditer(r'\b(?:public\s+)?(?:class|interface|enum|record)\s+([\w$]+)', cleaned):
        name = m.group(1)
        # Ignore les noms qui ressemblent à des variables ou sont trop courts
        if len(name) >= 2 and name[0].isupper():
            return name
    return ""
