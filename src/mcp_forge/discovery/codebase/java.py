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
from collections import Counter
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
    r'\s*(\{|;)',                                # corps { ou ; (méthode abstraite/interface) — CAPTURÉ
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

    def __init__(self) -> None:
        # Index des types du projet, construit une fois par racine et par
        # instance (une instance = une découverte) — voir _project_type_index.
        self._type_index: dict[str, dict[str, bool]] = {}
        # Opérations écartées, par raison : transmises à l'évaluateur
        # (chiffres de couverture, voir CodebaseDiscovery.discover).
        self.exclusions: Counter = Counter()

    def _unbuildable_param(self, root: Path, java_types: list[str]) -> str:
        """Premier type de paramètre déclaré dans le projet mais impossible
        à construire depuis une chaîne ("" si aucun)."""
        key = str(root)
        if key not in self._type_index:
            self._type_index[key] = _project_type_index(key)
        index = self._type_index[key]
        for jtype in java_types:
            # Tableau (`JSONPair[]`) : chaque élément est converti comme le
            # type de base — même verdict.
            base = jtype.split("<", 1)[0].replace("[]", "").strip()
            if base in index and not index[base]:
                return base
            if base not in index and base.split(".")[-1] in _JDK_UNBUILDABLE:
                return base
        return ""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")
        # Sources de test Maven/Gradle (`src/test/...`) : des tests JUnit,
        # pas une API — ils exigent JUnit/Mockito et un environnement de
        # test initialisé, et échouent systématiquement hors de ce cadre
        # (relevé par l'évaluateur sur une vraie API Java de plugins). Chemin RELATIF à
        # la racine analysée : le projet peut lui-même vivre sous un
        # dossier nommé "test".
        if re.search(r"(^|/)src/test/", relative_path):
            self.exclusions["test source files (src/test/), not counted as operations"] += 1
            return []
        class_name = _detect_class_name(source)
        source_root = _detect_source_root(source, relative_path)
        package_match = _PACKAGE_RE.search(source)
        package_name = package_match.group(1) if package_match else ""

        # Retire les commentaires non-Javadoc pour le parsing des méthodes
        cleaned = _BLOCK_COMMENT_RE.sub(" ", source)
        cleaned = _LINE_COMMENT_RE.sub("", cleaned)
        cleaned = _implicit_public_interface_members(cleaned, class_name)

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()
        instantiable = _is_instantiable(cleaned, class_name)

        for m in _METHOD_RE.finditer(cleaned):
            is_static = "static" in m.group(2)
            return_type = m.group(3).strip()
            method_name = m.group(4).strip()
            raw_params = m.group(5).strip()
            has_body = m.group(6) == "{"

            # Filtres
            if method_name in _SKIP_NAMES:
                continue
            # Une méthode terminée par ";" (pas de corps) n'a aucune
            # implémentation à appeler — déclaration abstraite ou méthode
            # d'interface (le modificateur "abstract" est même optionnel
            # dans une interface, implicite). Trouvé en testant sur un vrai
            # projet Java majoritairement en interfaces (une vraie API Java de plugins,
            # ~1980 fichiers) : la quasi-totalité des "méthodes" extraites
            # n'avaient tout simplement rien à exécuter.
            if not has_body:
                self.exclusions["abstract or interface methods (no body to execute)"] += 1
                continue
            # Une méthode d'instance s'appelle via `new Classe().m(...)`
            # (voir server_codebase_java.py.j2) : impossible si la classe
            # est abstraite, une interface (méthode `default`), un enum, ou
            # n'a pas de constructeur public sans argument. Relevé par
            # l'évaluateur sur une vraie API Java de plugins comme défaut "majeur et
            # systématique" : ces tools échouaient tous à la compilation.
            if not is_static and not instantiable:
                self.exclusions["instance methods of types that cannot be instantiated with new X()"] += 1
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
            params = _parse_params(raw_params)
            # Paramètre d'un type du projet qu'aucune chaîne ne peut produire
            # (interface implémentée à l'exécution par l'application hôte,
            # ex: `Plugin`, `Player`) : l'appel échouerait à coup sûr. Testé
            # AVANT de réserver le nom : une autre surcharge du même nom,
            # appelable, peut suivre.
            if self._unbuildable_param(root, [p.description for p in params]):
                self.exclusions["methods with a parameter type that cannot be built from a tool argument"] += 1
                continue
            seen.add(slug)

            # Javadoc juste avant dans le source original
            pos = m.start()
            summary, param_docs, return_doc = _parse_javadoc(cleaned, pos)
            owner = f"{class_name}.{method_name}" if class_name else method_name
            signature = f"{owner}({', '.join(p.description for p in params)})"
            description = summary or f"Calls the Java method {signature}."
            # Les types Java bruts sont dupliqués ici (pas uniquement sur
            # `param.description`, voir `_parse_params`) : l'étape
            # d'enrichissement LLM réécrit `param.description` en texte
            # humain pour la doc (`param.description = enriched[...]`,
            # mcp_forge/enrichment/llm.py) — un pilote d'exécution qui s'y
            # fierait recevrait une phrase descriptive au lieu du vrai type
            # Java ("int", "double[]"...) dès que l'enrichissement tourne.
            java_param_types = [p.description for p in params]
            # Doc lisible des paramètres (`@param` du Javadoc), le type Java
            # restant visible — sans Javadoc, le type seul comme avant.
            docs_by_slug = {name.lower(): doc for name, doc in param_docs.items()}
            for p, jtype in zip(params, java_param_types):
                doc = docs_by_slug.get(p.name.rstrip("_"))
                # Paramètre de type générique ("T") : rien ne permet de le
                # construire autrement — la valeur est transmise telle
                # quelle (chaîne Java, ou nombre), T étant inféré d'après elle.
                if re.fullmatch(r"[A-Z]", jtype.strip()):
                    jtype = f"{jtype}, generic: the value is passed as-is (String or number)"
                p.description = f"{doc} (Java: {jtype})" if doc else f"Java {jtype}"
            if return_type == "void":
                response_description = "Nothing (void method): an empty result means success."
            elif return_doc:
                response_description = f"{return_doc} (Java {return_type}, as text)"
            else:
                response_description = f"The Java {return_type} returned, as text (toString())."

            tools.append(DiscoveredTool(
                name=slug,
                description=description,
                response_description=response_description,
                parameters=params,
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": method_name,
                    "class": class_name,
                    "return_type": return_type,
                    "is_static": is_static,
                    "java_param_types": java_param_types,
                    "java_source_root": source_root,
                    "java_package": package_name,
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
        # `byte @NotNull [] message` (annotation de type dans le tableau,
        # vu sur une vraie API Java de plugins) laisse "byte []" une fois l'annotation
        # retirée : on recolle les crochets ("byte[]").
        java_type = re.sub(r"\s+\[", "[", " ".join(tokens[:-1]))
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


_INLINE_TAG_RE = re.compile(r"\{@(\w+)\s*([^{}]*)\}")
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_DOC_LIMIT = 400


def _inline_tag(m: re.Match) -> str:
    """`{@link Foo#bar(int) label}` → "label" (ou "Foo.bar"), `{@code x}` → "x"."""
    tag, body = m.group(1), m.group(2).strip()
    if tag in ("link", "linkplain"):
        parts = body.split(None, 1)
        if len(parts) == 2:
            return parts[1]
        return re.sub(r"\(.*\)$", "", parts[0] if parts else "").replace("#", ".").lstrip(".")
    return body


def _clean_doc_text(text: str) -> str:
    text = _INLINE_TAG_RE.sub(_inline_tag, text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def _truncate_doc(text: str, limit: int = _DOC_LIMIT) -> str:
    """Coupe à la dernière fin de phrase avant `limit` plutôt qu'au milieu
    d'un mot (ou à la limite brute s'il n'y en a pas)."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = cut.rfind(". ")
    return cut[:end + 1] if end > limit // 3 else cut.rstrip() + "…"


def _parse_javadoc(source: str, pos: int) -> tuple[str, dict[str, str], str]:
    """Javadoc juste avant `pos` → (résumé, {param: description}, retour).

    2026-10-13 — l'ancienne version, mesurée sur une vraie API Java de plugins (note
    "docs" de l'évaluateur à 5,5), supprimait tout depuis le premier `@`
    jusqu'à la fin du texte — donc aussi les tags EN LIGNE `{@link X}`,
    d'où des descriptions tronquées comme "Creates a typed key for {" —
    et laissait l'astérisque de la première ligne ("* Creates...").
    `@param` / `@return` alimentent maintenant la doc des paramètres et
    du retour au lieu d'être jetés."""
    preceding = source[max(0, pos - 3000):pos]
    matches = list(_JAVADOC_RE.finditer(preceding))
    if not matches:
        return "", {}, ""
    last = matches[-1]
    # Vérifie que le Javadoc est juste avant (pas séparé par du code)
    if re.search(r'[;{}]', _JAVADOC_RE.sub("", preceding[last.end():])):
        return "", {}, ""
    lines = [re.sub(r"^\s*\*?\s?", "", line) for line in last.group(1).splitlines()]
    # Découpe en blocs : la description, puis un bloc par tag (@param...).
    blocks: list[list[str]] = [[]]
    for line in lines:
        if re.match(r"@\w+", line.strip()):
            blocks.append([line.strip()])
        else:
            blocks[-1].append(line)
    summary = _truncate_doc(_clean_doc_text(" ".join(blocks[0])))
    params: dict[str, str] = {}
    returns = ""
    for block in blocks[1:]:
        text = " ".join(block)
        m = re.match(r"@param\s+<?([\w$]+)>?\s*(.*)", text, re.DOTALL)
        if m:
            params[m.group(1)] = _truncate_doc(_clean_doc_text(m.group(2)), 200)
            continue
        m = re.match(r"@return\s*(.*)", text, re.DOTALL)
        if m:
            returns = _truncate_doc(_clean_doc_text(m.group(1)), 200)
    return summary, params, returns


def _extract_javadoc(source: str, pos: int) -> str:
    """Résumé seul du Javadoc précédant pos (voir _parse_javadoc)."""
    return _parse_javadoc(source, pos)[0]


_PACKAGE_RE = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.MULTILINE)


def _detect_source_root(source: str, relative_path: str) -> str:
    """Calcule le dossier racine du classpath pour CE fichier, en
    comparant sa déclaration `package` à son chemin relatif réel.

    Exemple : `relative_path` = "src/generated/java/org/example/plugin/
    registry/keys/BannerPatternKeys.java", `package org.example.plugin.
    registry.keys;` → racine = "src/generated/java" (le chemin moins le
    sous-chemin du package et le nom de fichier).

    Nécessaire pour `-sourcepath` (voir server_codebase_java.py.j2) :
    javac exige que la racine passée à `-sourcepath` corresponde EXACTEMENT
    au dossier juste au-dessus du premier segment du package — un projet
    multi-modules (ex: une vraie API Java de plugins, "src/main/java/..." ET
    "src/generated/java/..." comme DEUX racines distinctes dans le même
    projet) a plusieurs racines différentes selon le fichier ; une seule
    racine fixe (ex: le dossier du projet tout entier) ne permet de
    résoudre AUCUNE référence inter-fichiers."""
    m = _PACKAGE_RE.search(source)
    if not m:
        return ""
    pkg_parts = m.group(1).split(".")
    path_parts = relative_path.split("/")
    # Le fichier doit se terminer par .../pkg/part/.../ClassName.java —
    # les N derniers segments de dossier (N = nb de parties du package)
    # doivent correspondre au chemin de package déclaré.
    dir_parts = path_parts[:-1]
    if len(dir_parts) < len(pkg_parts) or dir_parts[-len(pkg_parts):] != pkg_parts:
        return ""
    root_parts = dir_parts[:len(dir_parts) - len(pkg_parts)]
    return "/".join(root_parts)


def _is_instantiable(cleaned: str, class_name: str) -> bool:
    """`new ClassName()` compile-t-il depuis le pilote (paquet par défaut) ?

    Oui seulement pour une classe publique, non abstraite, qui n'a soit
    aucun constructeur déclaré (constructeur par défaut implicite), soit
    un constructeur `public` sans argument. Interfaces, enums, records et
    classes abstraites ne le sont jamais. Classe non identifiée : on ne
    filtre rien (comportement antérieur), faute de pouvoir trancher."""
    if not class_name:
        return True
    decl = re.search(
        r'\b((?:(?:public|protected|private|abstract|final|sealed|non-sealed|static|strictfp)\s+)*)'
        r'(class|interface|enum|record)\s+' + re.escape(class_name) + r'\b',
        cleaned,
    )
    if not decl or decl.group(2) != "class":
        return False
    modifiers = decl.group(1).split()
    if "public" not in modifiers or "abstract" in modifiers:
        return False
    ctor_re = re.compile(r'\b' + re.escape(class_name) + r'\s*\(([^)]*)\)\s*(?:throws\s+[\w.,\s]+)?\{')
    ctors = []
    for c in ctor_re.finditer(cleaned):
        # `new ClassName() { ... }` (classe anonyme) n'est pas une déclaration
        if re.search(r'\bnew\s+$', cleaned[max(0, c.start() - 10):c.start()]):
            continue
        ctors.append(c)
    if not ctors:
        return True
    return any(
        not c.group(1).strip() and re.search(r'\bpublic\s+$', cleaned[max(0, c.start() - 30):c.start()])
        for c in ctors
    )


# Interfaces / types abstraits du JDK qu'aucune chaîne ne peut produire
# (pas de fabrique String) — hors projet, donc absents de
# _project_type_index. Les collections Java (List, Set...) ne sont pas
# ici : elles sont reçues comme tableaux (ParameterType.ARRAY).
_JDK_UNBUILDABLE = {
    "Map", "HashMap", "LinkedHashMap", "TreeMap", "SortedMap", "NavigableMap", "ConcurrentMap",
    "Iterator", "Spliterator", "Stream", "IntStream", "LongStream", "DoubleStream",
    "Function", "BiFunction", "Supplier", "Consumer", "BiConsumer", "Predicate", "BiPredicate",
    "UnaryOperator", "BinaryOperator", "Runnable", "Callable", "Executor", "ExecutorService",
    "Comparator", "Thread", "ClassLoader", "InputStream", "OutputStream", "Reader", "Writer",
    "Logger", "Future", "CompletableFuture", "Optional",
}

_TYPE_DECL_RE = re.compile(
    r'\b((?:(?:public|protected|private|abstract|final|sealed|non-sealed|static|strictfp)\s+)*)'
    r'(class|interface|enum|record|@interface)\s+([\w$]+)'
)
_STRING_ARG = r'\(\s*(?:final\s+)?(?:@[\w.]+(?:\([^)]*\))?\s+)*(?:java\.lang\.)?String\s+[\w$]+\s*\)'


def _buildable_from_string(cleaned: str, kind: str, modifiers: list[str], name: str) -> bool:
    """McpForgeConvert (voir server_codebase_java.py.j2) peut-il produire
    un `name` à partir d'une chaîne ? Enum : oui. Sinon il faut une
    fabrique statique `name xxx(String)` ou, pour une classe concrète, un
    constructeur `public name(String)`."""
    if kind == "enum":
        return True
    n = re.escape(name)
    factory = re.compile(r'\bstatic\s+(?:<[^>]*>\s+)?(?:@[\w.]+\s+)*' + n + r'(?:<[^>]*>)?\s+[\w$]+\s*' + _STRING_ARG)
    if factory.search(cleaned):
        return True
    if kind == "class" and "abstract" not in modifiers:
        return re.search(r'\bpublic\s+' + n + r'\s*' + _STRING_ARG, cleaned) is not None
    return False


def _project_type_index(root: str) -> dict[str, bool]:
    """Types déclarés dans le projet (nom simple du type principal de
    chaque fichier .java) → constructible depuis une chaîne ?

    2026-10-13 — relevé par l'évaluateur sur une vraie API Java de plugins (robustesse
    5,5) : des tools prenant `Plugin`, `CommandSender`, `World`,
    `Player`... (interfaces implémentées par le serveur en cours
    d'exécution) étaient exposés alors qu'aucune chaîne ne peut produire
    un tel objet — échec garanti à chaque appel. Seuls les types DU PROJET
    sont jugés ; un type externe (JDK, bibliothèque) est laissé à
    McpForgeConvert. Homonymes dans des paquets différents : constructible
    si l'un d'eux l'est."""
    index: dict[str, bool] = {}
    for path in Path(root).rglob("*.java"):
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        cleaned = _LINE_COMMENT_RE.sub("", _BLOCK_COMMENT_RE.sub(" ", _JAVADOC_RE.sub(" ", source)))
        m = _TYPE_DECL_RE.search(cleaned)
        if not m or m.group(3) != path.stem:
            continue
        ok = _buildable_from_string(cleaned, m.group(2), m.group(1).split(), m.group(3))
        index[m.group(3)] = index.get(m.group(3), False) or ok
    return index


# Javadoc (`{@link ...}` contient des accolades) et littéraux
_LITERAL_RE = re.compile(r'/\*\*.*?\*/|""".*?"""|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])+\'', re.DOTALL)
_LEADING_ANNOTATIONS_RE = re.compile(r'\s*(?:@[\w$.]+(?:\s*\((?:[^()]|\([^()]*\))*\))?\s*)*')


def _implicit_public_interface_members(cleaned: str, class_name: str) -> str:
    """Ajoute `public` devant les méthodes de l'interface principale qui
    l'omettent : dans une interface, les méthodes sont implicitement
    publiques et c'est l'écriture la plus courante. Mesuré sur une vraie
    API Java de plugins (2026-10-14) : 4550 méthodes ainsi écrites étaient invisibles pour
    _METHOD_RE, dont ~190 méthodes `static` avec corps, appelables.

    Seuls les membres de premier niveau du corps sont touchés (pas ceux
    des types imbriqués, appelés via un autre nom). Javadoc et littéraux
    sont masqués pour le comptage des accolades ; les positions restent
    celles de `cleaned`."""
    if not class_name:
        return cleaned
    decl = re.search(r'(?<!@)\binterface\s+' + re.escape(class_name) + r'\b', cleaned)
    if not decl:
        return cleaned
    masked = _LITERAL_RE.sub(lambda m: " " * len(m.group(0)), cleaned)
    start = masked.find("{", decl.end())
    if start < 0:
        return cleaned
    inserts: list[int] = []

    def visit(seg_start: int, seg_end: int) -> None:
        segment = masked[seg_start:seg_end]
        # Tête de la déclaration APRÈS les annotations (`@Deprecated(...)`
        # contient lui-même une parenthèse)
        lead = _LEADING_ANNOTATIONS_RE.match(segment)
        rest = segment[lead.end():]
        head = rest.split("(", 1)[0]
        if ("(" not in rest or "=" in head
                or re.search(r'\b(public|protected|private|class|interface|enum|record)\b', head)):
            return
        pos = seg_start + lead.end()
        if re.match(r'[\w$]', masked[pos:pos + 1]):
            inserts.append(pos)

    depth, seg_start = 0, start + 1
    for i in range(start, len(masked)):
        c = masked[i]
        if c == "{":
            depth += 1
            if depth == 2:
                visit(seg_start, i)
        elif c == "}":
            depth -= 1
            if depth == 1:
                seg_start = i + 1
            elif depth == 0:
                break
        elif c == ";" and depth == 1:
            visit(seg_start, i)
            seg_start = i + 1
    for pos in reversed(inserts):
        cleaned = cleaned[:pos] + "public " + cleaned[pos:]
    return cleaned


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
