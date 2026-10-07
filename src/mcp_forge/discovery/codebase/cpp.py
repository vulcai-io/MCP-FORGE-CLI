"""
Parser C++ pour la découverte codebase.
Utilise des expressions régulières sur les fichiers d'en-tête (.h / .hpp).

Formats supportés :
  void functionName(int a, const char* b);
  static int ClassName::method(float x) const;
  ReturnType name(Type param = default);

Priorité aux headers (.h/.hpp) qui définissent l'API publique.
"""
from __future__ import annotations

import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Retire les commentaires C++ de ligne et bloc
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

# Commentaire Doxygen/C juste avant la déclaration (/** ... */ ou //! ... ou /// ...)
_DOC_RE = re.compile(
    r'/\*[*!]\s*(.*?)\s*\*/'       # /** ... */ ou /*! ... */
    r'|//[/!]\s*([^\n]+)',          # /// ... ou //! ...
    re.DOTALL,
)

# Détection de déclaration de fonction C/C++
# Gère : qualificatifs (static, virtual, inline, constexpr, explicit, [[nodiscard]])
#        type de retour (pointeurs, références, namespaces)
#        nom de fonction (avec éventuel ClassName::)
#        paramètres entre parenthèses
#        suffixes const, override, final, noexcept, = 0
_FUNC_DECL_RE = re.compile(
    r'(?:'
    r'(?:static|virtual|inline|explicit|constexpr|extern|__declspec\(\w+\)|__attribute__\(\([^)]*\)\)|\[\[nodiscard\]\])\s+'
    r')*'
    r'((?:(?:const|unsigned|signed|long|short|struct|enum|class)\s+)*'
    r'[\w:<>*& ,]+?)\s+'          # type de retour
    r'(~?[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)'  # nom de fonction (optionnel ClassName::)
    r'\s*\(([^)]*)\)'             # paramètres
    r'(?:\s*const)?(?:\s*noexcept(?:\([^)]*\))?)?'
    r'(?:\s*override)?(?:\s*final)?'
    r'(?:\s*=\s*(?:0|default|delete))?'
    r'\s*(?:;|\{)',                # termine par ; (prototype) ou { (définition, fallback .c/.cpp sans header)
    re.MULTILINE,
)

# Noms à ignorer
_SKIP_NAMES = {
    "if", "for", "while", "switch", "return", "sizeof", "typedef",
    "operator", "delete", "new", "assert", "main",
}
_SKIP_PREFIXES = ("_", "~")

# Types de retour qui signalent un constructeur raté
_NON_RETURN_TYPES = {"class", "struct", "enum", "namespace", "typedef", "template"}

# Extensions considérées : headers en priorité, sources en fallback
HEADER_EXTENSIONS = {".h", ".hpp", ".hxx", ".hh"}
SOURCE_EXTENSIONS = {".cpp", ".cc", ".cxx", ".c"}

import keyword as _kw
_PY_KEYWORDS = set(_kw.kwlist + _kw.softkwlist) | {
    # JS builtins problématiques dans les schemas MCP
    "constructor", "prototype", "__proto__",
}

# Détection des pointeurs de sortie primitifs (int*, uint32_t*, float*...)
# Critère : pointeur vers primitive, sans const >> paramètre de sortie
_OUTPUT_PRIMITIVE_RE = re.compile(
    r'\b(int|uint|uint8_t|uint16_t|uint32_t|uint64_t|'
    r'int8_t|int16_t|int32_t|int64_t|'
    r'float|double|bool|size_t|ptrdiff_t)\b'
)


class CppParser:
    """Extrait les fonctions publiques de fichiers C/C++ via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")
        is_header = path.suffix.lower() in HEADER_EXTENSIONS

        # Neutralise les commentaires (remplacés par des espaces/retours à
        # la ligne de MÊME LONGUEUR, PAS retirés) pour faciliter le parsing
        # des déclarations SANS décaler les positions de caractères — tout
        # le reste du fichier (`_detect_class_context`, `_extract_doc`,
        # recherche des docstrings Doxygen...) continue de travailler sur
        # `source` original en utilisant les positions (`m.start()`)
        # trouvées dans `cleaned`. Une substitution qui change la longueur
        # (l'ancien comportement : bloc remplacé par un seul espace, ligne
        # retirée entièrement) désynchronise ces deux textes dès qu'un
        # commentaire précède le code pertinent — trouvé sur un vrai moteur
        # C++ (ocgcore, progressivebuffer.h, qui commence par un bloc de
        # licence de 4 lignes) : `_find_class_at_pos` retombait sur une
        # classe vide pour `ProgressiveBuffer::clear()`, laissant passer
        # une méthode de classe comme une fonction libre.
        def _blank(m: re.Match) -> str:
            return "".join(c if c == "\n" else " " for c in m.group(0))

        cleaned = _BLOCK_COMMENT_RE.sub(_blank, source)
        cleaned = _LINE_COMMENT_RE.sub(_blank, cleaned)

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        # Cherche le contexte de classe courant pour les méthodes — sur
        # `cleaned`, PAS `source` : `_FUNC_DECL_RE.finditer(cleaned)`
        # ci-dessous donne des positions (`m.start()`) qui sont des offsets
        # dans `cleaned`, un texte plus court que `source` dès qu'un
        # commentaire a été retiré avant la classe (licence en-tête de
        # fichier, Doxygen...). Chercher le contexte de classe dans
        # `source` avec ces offsets de `cleaned` les désynchronise
        # silencieusement — trouvé sur un vrai moteur C++ (ocgcore,
        # progressivebuffer.h, qui commence par un bloc de licence de 4
        # lignes) : `_find_class_at_pos` retombait sur class="" pour
        # `ProgressiveBuffer::clear()`, laissant passer une méthode de
        # classe comme si c'était une fonction libre.
        class_context = _detect_class_context(cleaned)

        for m in _FUNC_DECL_RE.finditer(cleaned):
            return_type = m.group(1).strip()
            raw_name = m.group(2).strip()
            raw_params = m.group(3).strip()

            # Filtre
            if not raw_name or raw_name.lower() in _SKIP_NAMES:
                continue
            # Trouvé en testant sur un vrai moteur C++ (ocgcore) : une
            # liste d'initialisation de constructeur ("noexcept : s(x) {")
            # peut se faire capturer comme "mot mot(params) {" avec le ":"
            # de l'initializer-list avalé dans le groupe "type de retour"
            # (qui autorise ":" pour les types qualifiés, ex: std::string)
            # — "s" devient alors un faux nom de fonction. Un export C
            # réel n'a quasiment jamais un nom d'une seule lettre.
            if len(raw_name.split("::")[-1]) < 2:
                continue
            if any(raw_name.startswith(p) for p in _SKIP_PREFIXES):
                continue
            if any(kw in return_type.split() for kw in _NON_RETURN_TYPES):
                continue
            # Ignore les macros (tout en majuscules)
            if raw_name.isupper():
                continue
            # "if constexpr(...) { ... }" (ou "for"/"while"/"switch" suivis
            # d'une parenthèse puis d'une accolade) a exactement la forme
            # structurelle d'une déclaration de fonction ("mot mot(params) {")
            # — `_SKIP_NAMES` ne filtre que quand le mot-clé de contrôle est
            # capturé comme NOM (groupe 2), pas quand il atterrit dans le
            # groupe "type de retour" (groupe 1), ce qui arrive justement
            # pour "if constexpr(...)" : "if" -> groupe 1, "constexpr" ->
            # groupe 2 (capturé comme nom de fonction). Trouvé en testant
            # sur un vrai moteur C++ (ocgcore) : un faux tool "constexpr"
            # généré depuis `if constexpr(LuaFunction<...>::initialized)`.
            return_type_words = return_type.split()
            if return_type_words and return_type_words[-1].lower() in _SKIP_NAMES:
                continue
            # Les fonctions template ("template<typename T> ... foo(T val)")
            # n'ont, comme les méthodes de classe, aucun symbole exporté
            # stable sous leur nom tel quel — chaque instanciation génère
            # son propre code, souvent inliné, jamais sous le nom brut
            # "foo". Trouvé sur un vrai moteur C++ (ocgcore, bit.h) :
            # `template<typename T> constexpr inline uint8_t popcnt(T val)`
            # — en plus de n'être pas dispatchable, le paramètre type `T`
            # (un paramètre de template, pas un type concret) retombait
            # sur le défaut `str`/c_char_p du mapping de types, pour une
            # fonction qui attend en réalité un entier.
            # "template<...>" peut soit précéder le match sur sa propre
            # ligne (cas multi-ligne, cherché en arrière via
            # `_is_template_declaration`), soit se faire avaler DANS le
            # groupe "type de retour" lui-même quand tout est sur une
            # seule ligne ("template<typename T> T identity(...)" — le
            # groupe retour, qui autorise `<>` pour les types qualifiés,
            # capture "template<typename T> T" en entier).
            if "template" in return_type.lower() or _is_template_declaration(cleaned, m.start()):
                continue
            # Nom de tool (slug)
            class_name = raw_name.split("::")[0] if "::" in raw_name else ""
            if not class_name:
                # Cherche si la position du match correspond à une classe
                class_name = _find_class_at_pos(class_context, m.start())

            # Les méthodes de classe (définies hors-classe avec "ClassName::",
            # OU déclarées à l'intérieur du corps d'une classe/struct dans un
            # header) ne sont QUASIMENT jamais dispatchables via ctypes : nom
            # mangled en C++ (pas de symbole exporté sous ce nom tel quel),
            # et il manque le pointeur "this" même quand un symbole existe.
            # Trouvé en testant sur un vrai moteur C++ (ocgcore, moteur du
            # jeu Yu-Gi-Oh!) : 486 des 652 tools extraits (74%) étaient des
            # méthodes de classe garanties non-fonctionnelles — l'ancien
            # filtre ne couvrait que les définitions QUALIFIÉES hors-classe
            # ("ClassName::method() {" dans un .cpp), pas les déclarations
            # NON qualifiées à l'intérieur du corps de la classe dans un
            # header ("void method();" entre les accolades de `class X {`),
            # pourtant déjà détectées par `_find_class_at_pos` ci-dessus
            # sans jamais être utilisées pour filtrer.
            if class_name:
                continue

            slug = _SLUG_RE.sub("_", raw_name.lower()).strip("_")
            if slug in seen:
                continue
            seen.add(slug)

            # Description : cherche un commentaire Doxygen juste avant dans le source original
            pos = m.start()
            description = _extract_doc(source, pos) or f"{return_type} {raw_name}(...)"

            input_params, full_params = _parse_params(raw_params)
            tools.append(DiscoveredTool(
                name=slug,
                description=description,
                parameters=input_params,
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": raw_name,
                    "class": class_name,
                    "return_type": return_type,
                    "language": "cpp",
                    "is_header": is_header,
                    "cpp_params_full": full_params,
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_params(raw: str) -> tuple[list[ToolParameter], list[dict]]:
    """Convertit une liste de paramètres C++ en (input_params, full_ordered_params).

    full_ordered_params contient tous les params dans l'ordre original (y compris
    les pointeurs de sortie) avec les clés : name, c_type, is_output, ctypes_type.
    input_params ne contient que les params exposés dans la signature MCP.
    """
    if not raw.strip() or raw.strip() == "void":
        return [], []
    input_params: list[ToolParameter] = []
    full_params: list[dict] = []
    for part in _split_params(raw):
        part = part.strip()
        if not part:
            continue
        # Retire la valeur par défaut
        part = re.sub(r"\s*=\s*[^,]*$", "", part).strip()
        # Retire les qualificatifs (sauf const qui sert à détecter les pointeurs de sortie)
        part_no_qual = re.sub(r"\b(volatile|mutable|register|restrict)\b", "", part).strip()
        # Extrait le nom : dernier mot (avant les éventuels [])
        name_match = re.search(r"([A-Za-z_]\w*)(?:\s*\[\s*\])?\s*$", part_no_qual)
        if not name_match:
            continue
        param_name = name_match.group(1)
        if param_name in ("void",):
            continue
        # Type C++ brut (avec const, *, & encore présents pour analyse)
        c_type_raw = part_no_qual[:name_match.start()].strip()
        # Détecte si c'est un pointeur de sortie primitif
        is_out = _is_output_pointer(c_type_raw)
        is_in_array = not is_out and _is_input_array_pointer(c_type_raw)
        is_mutable_buffer = not is_out and not is_in_array and _is_mutable_char_buffer(c_type_raw)
        ctypes_type = _ctypes_out_type(c_type_raw) if is_out else _ctypes_input_type(c_type_raw)

        slug = re.sub(r"[^a-z0-9_]", "_", param_name.lower()).strip("_") or "param"
        if slug in _PY_KEYWORDS:
            slug = slug + "_"

        full_params.append({
            "name": slug,
            "c_type": c_type_raw,
            "is_output": is_out,
            "is_input_array": is_in_array,
            "is_mutable_buffer": is_mutable_buffer,
            "ctypes_type": ctypes_type,
        })

        # Pour le type Python, retire const/qualificatifs pour le calcul
        c_type_clean = re.sub(r"\b(const|volatile|mutable|register|restrict)\b", "", c_type_raw).strip()
        items_type = None
        if not is_out:
            if is_in_array:
                py_type = ParameterType.ARRAY
                # Type de l'élément (ex: `const double*` >> NUMBER) : permet au
                # générateur de rendre `list[float]` plutôt qu'un `list` nu.
                items_type = _c_type_to_param_type(c_type_clean.replace("*", "").strip())
            else:
                py_type = _c_type_to_param_type(c_type_clean)
            input_params.append(ToolParameter(
                name=slug,
                type=py_type,
                items_type=items_type,
                description=c_type_raw,
                required=True,
            ))
    return input_params, full_params


def _split_params(raw: str) -> list[str]:
    """Divise les paramètres en gérant les templates imbriqués (A<B, C>)."""
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


def _is_output_pointer(c_type: str) -> bool:
    """True si le type est un pointeur vers une primitive sans const >> paramètre de sortie.

    Exemples : int* >> True, uint32_t* >> True, void* >> False, const char* >> False.
    """
    if '*' not in c_type or 'const' in c_type:
        return False
    base = c_type.replace('*', '').lower()
    return bool(_OUTPUT_PRIMITIVE_RE.search(base))


def _is_mutable_char_buffer(c_type: str) -> bool:
    """True pour un `char*` non-const : idiome C très courant où la fonction
    modifie la chaîne EN PLACE (ex: `void reverse_string(char *s)`).

    Root cause du bug corrigé ici : ctypes reçoit une COPIE immutable
    (bytes) pour un argtype `c_char_p` passé normalement — toute mutation
    faite côté C est invisible pour Python ensuite, donc une fonction void
    de ce type renvoyait systématiquement une chaîne vide. Un
    `ctypes.create_string_buffer(...)` donne un buffer mutable que ctypes
    gère spécialement : les écritures C y sont bien visibles après l'appel.
    """
    base = c_type.replace(" ", "")
    return base in ("char*", "unsignedchar*") and "const" not in c_type


def _is_input_array_pointer(c_type: str) -> bool:
    """True si le type est un pointeur const vers une primitive (tableau en
    lecture seule, ex: `const double*`, `const int numbers[]`).

    Root cause du bug corrigé ici : sans cette détection, un paramètre comme
    `const double *numbers` était typé comme un simple NUMBER (un seul
    float) au lieu d'une liste — le ctypes argtype généré ensuite
    (`ctypes.c_char_p`, fallback générique pour tout ce qui n'est pas
    int/float/bool) ne correspondait à rien de valide pour un tableau.
    """
    if '*' not in c_type or 'const' not in c_type:
        return False
    base = c_type.replace('*', '').replace('const', '').strip().lower()
    return bool(_OUTPUT_PRIMITIVE_RE.search(base))


def _ctypes_out_type(c_type: str) -> str:
    """Type ctypes pour un paramètre de sortie pointeur vers primitive."""
    base = c_type.replace('*', '').lower()
    if re.search(r'\buint|size_t', base):
        return 'ctypes.c_uint32'
    if 'double' in base:
        return 'ctypes.c_double'
    if 'float' in base:
        return 'ctypes.c_float'
    if 'bool' in base:
        return 'ctypes.c_bool'
    return 'ctypes.c_int'


def _ctypes_input_type(c_type: str) -> str:
    """Type ctypes pour un paramètre d'entrée."""
    c = c_type.lower()
    if any(t in c for t in ('int', 'long', 'short', 'uint', 'size_t', 'ptrdiff')):
        return 'ctypes.c_int'
    if 'double' in c:
        return 'ctypes.c_double'
    if 'float' in c:
        return 'ctypes.c_float'
    if 'bool' in c:
        return 'ctypes.c_bool'
    if 'void' in c:
        return 'ctypes.c_void_p'
    return 'ctypes.c_char_p'


def _c_type_to_param_type(c_type: str) -> ParameterType:
    c = c_type.lower()
    if any(t in c for t in ("int", "long", "short", "uint", "size_t", "ptrdiff")):
        return ParameterType.INTEGER
    if any(t in c for t in ("float", "double")):
        return ParameterType.NUMBER
    if "bool" in c:
        return ParameterType.BOOLEAN
    return ParameterType.STRING


def _extract_doc(source: str, pos: int) -> str:
    """Cherche un commentaire Doxygen dans les 10 lignes précédant pos."""
    preceding = source[max(0, pos - 500):pos]
    matches = list(_DOC_RE.finditer(preceding))
    if not matches:
        return ""
    last = matches[-1]
    text = (last.group(1) or last.group(2) or "").strip()
    # Nettoie les * en début de ligne (/** style)
    text = re.sub(r"\n\s*\*\s?", " ", text).strip()
    return text[:200]


def _detect_class_context(source: str) -> list[tuple[int, int, str]]:
    """Détecte les plages de classes dans le source (début, fin, nom)."""
    contexts = []
    class_re = re.compile(r'\b(?:class|struct)\s+([A-Za-z_]\w*)\s*(?::[^{]*)?{', re.MULTILINE)
    for m in class_re.finditer(source):
        name = m.group(1)
        start = m.start()
        # Cherche l'accolade fermante correspondante
        depth, i = 1, m.end()
        while i < len(source) and depth > 0:
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
            i += 1
        contexts.append((start, i, name))
    return contexts


def _find_class_at_pos(contexts: list[tuple[int, int, str]], pos: int) -> str:
    """Retourne le nom de la classe contenant la position, ou chaîne vide."""
    for start, end, name in contexts:
        if start <= pos <= end:
            return name
    return ""


_TEMPLATE_HEADER_RE = re.compile(r'\btemplate\s*<[^;{}]*>\s*$')


def _is_template_declaration(source: str, pos: int) -> bool:
    """Vérifie si une déclaration/définition de fonction à `pos` est
    précédée d'un en-tête "template<...>" (sur la même ligne logique,
    modulo d'éventuels qualificateurs comme constexpr/inline entre les
    deux) — auquel cas ce n'est pas une fonction exportable sous son nom
    brut."""
    window = source[max(0, pos - 300):pos]
    # Retire les qualificateurs usuels qui peuvent s'intercaler entre
    # "template<...>" et le type de retour (ex: "template<typename T>\nconstexpr inline uint8_t popcnt(...")
    stripped = re.sub(
        r'\b(?:constexpr|inline|static|virtual|explicit)\b',
        '', window,
    )
    return bool(_TEMPLATE_HEADER_RE.search(stripped.rstrip()))
