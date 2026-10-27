"""
Parser Fortran pour la découverte codebase.
Supporte le format fixe (Fortran 77, .f/.for) et le format libre (Fortran 90+, .f90/.f95/.f03/.f08).

Unités extraites :
  - SUBROUTINE name(params)
  - FUNCTION name(params)
  - MODULE PROCEDURE (interfaces)

Détection du format par extension :
  - Fixe : .f, .for, .f77
  - Libre : .f90, .f95, .f03, .f08, .f18
"""
from __future__ import annotations

import keyword as _kw
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    "constructor", "prototype", "__proto__",
}

# Extensions format fixe
_FIXED_EXTENSIONS = {".f", ".for", ".f77", ".ftn"}
# Extensions format libre
_FREE_EXTENSIONS = {".f90", ".f95", ".f03", ".f08", ".f18", ".f2k"}

# Modificateurs Fortran
_MODIFIERS = r'(?:(?:PURE|ELEMENTAL|RECURSIVE|IMPURE|NON_RECURSIVE)\s+)*'

# Types de retour pour les FUNCTION
_RETURN_TYPES = (
    r'(?:INTEGER(?:\s*\([^)]*\))?|REAL(?:\s*\([^)]*\))?|'
    r'DOUBLE\s+PRECISION|COMPLEX(?:\s*\([^)]*\))?|'
    r'LOGICAL(?:\s*\([^)]*\))?|CHARACTER(?:\s*\([^)]*\))?|'
    r'TYPE\s*\([^)]*\))\s+'
)

# Subroutines
_SUBR_RE = re.compile(
    r'^\s*' + _MODIFIERS +
    r'SUBROUTINE\s+(\w+)\s*(?:\(([^)]*)\))?',
    re.IGNORECASE | re.MULTILINE,
)

# Functions (avec ou sans type de retour explicite)
_FUNC_RE = re.compile(
    r'^\s*' + _MODIFIERS +
    r'(?:' + _RETURN_TYPES + r')?' +
    _MODIFIERS +
    r'FUNCTION\s+(\w+)\s*(?:\(([^)]*)\))?',
    re.IGNORECASE | re.MULTILINE,
)

# Module context
_MODULE_RE = re.compile(
    r'^\s*MODULE\s+(?!PROCEDURE|FUNCTION|SUBROUTINE)(\w+)',
    re.IGNORECASE | re.MULTILINE,
)

_RESERVED_FORTRAN = {
    "PROGRAM", "MODULE", "END", "USE", "IMPLICIT", "NONE",
    "INTEGER", "REAL", "DOUBLE", "COMPLEX", "LOGICAL", "CHARACTER",
    "TYPE", "KIND", "INTENT", "IN", "OUT", "INOUT",
    "ALLOCATABLE", "POINTER", "TARGET", "OPTIONAL", "SAVE",
    "DIMENSION", "PARAMETER", "COMMON", "EQUIVALENCE",
    "IF", "THEN", "ELSE", "ENDIF", "DO", "ENDDO", "WHILE",
    "CALL", "RETURN", "STOP", "PAUSE", "WRITE", "READ",
    "OPEN", "CLOSE", "INQUIRE", "FORMAT", "PRINT",
    "CONTAINS", "INTERFACE", "PURE", "ELEMENTAL", "RECURSIVE",
}


class FortranParser:
    """Extrait les subroutines et fonctions de fichiers Fortran via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        ext = path.suffix.lower()
        if ext not in _FIXED_EXTENSIONS and ext not in _FREE_EXTENSIONS:
            return []

        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")

        fmt = "fixed" if ext in _FIXED_EXTENSIONS else "free"
        normalized = _normalize(source, fmt)

        # `real_module` reste vide quand le fichier ne définit aucun
        # `module ... end module` — nécessaire pour l'instruction `use` du
        # driver généré, qui échouerait à la compilation si on la générait
        # pour un fichier sans module réel. `prefix` (cosmétique, nom
        # d'outil) peut lui continuer à retomber sur le nom de fichier.
        real_module = _detect_module(normalized)
        prefix = _SLUG_RE.sub("_", (real_module or path.stem).lower()).strip("_")

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        # Subroutines
        for m in _SUBR_RE.finditer(normalized):
            name = m.group(1)
            raw_params = m.group(2) or ""
            _add_unit(name, "subroutine", raw_params, prefix, relative_path, seen, tools, real_module,
                      _declared_types(_unit_body(normalized, m.end())))

        # Functions
        for m in _FUNC_RE.finditer(normalized):
            name = m.group(1)
            raw_params = m.group(2) or ""
            if not name:
                continue
            _add_unit(name, "function", raw_params, prefix, relative_path, seen, tools, real_module,
                      _declared_types(_unit_body(normalized, m.end())))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _normalize(source: str, fmt: str) -> str:
    """Normalise le source Fortran en retirant les commentaires."""
    if fmt == "free":
        # Commentaires : ! jusqu'à fin de ligne
        return re.sub(r'!.*', '', source)

    # Format fixe : col 1 = C ou * >> commentaire ; col 6 = continuation
    result = []
    for line in source.splitlines():
        if not line:
            result.append("")
            continue
        # Commentaire en col 1
        if line[0] in ("C", "c", "*", "!"):
            result.append("")
            continue
        # Continuation en col 6 (index 5)
        if len(line) > 5 and line[5] not in (" ", "0"):
            # Colle à la ligne précédente
            code = line[6:72] if len(line) > 6 else ""
            if result:
                result[-1] = result[-1].rstrip() + " " + code.strip()
            continue
        # Code normal : colonnes 7-72
        code = line[6:72] if len(line) > 6 else ""
        result.append(code)

    return "\n".join(result)


def _detect_module(source: str) -> str:
    """Extrait le nom du MODULE principal."""
    m = _MODULE_RE.search(source)
    return m.group(1) if m else ""


# Fin de l'unité courante (END FUNCTION / END SUBROUTINE / END seul)
_UNIT_END_RE = re.compile(r'^\s*END\s*(?:FUNCTION|SUBROUTINE)?\b', re.IGNORECASE | re.MULTILINE)

# Déclarations de variables. Fortran 90+ : type [(kind/len)] [, attributs]
# :: liste — les attributs peuvent eux-mêmes contenir ':' (dimension(:)).
# Fortran 77 : type[*n] liste, sans '::'.
_TYPE_KEYWORD = r'(INTEGER|REAL|DOUBLE\s+PRECISION|LOGICAL|CHARACTER|COMPLEX)'
_KIND = r'(?:\s*\*\s*\d+|\s*\([^)]*\))?'
_DECL_RE = re.compile(
    r'^\s*' + _TYPE_KEYWORD + _KIND + r'\s*(?:,\s*(.*?))?\s*::\s*(\S.*)$',
    re.IGNORECASE | re.MULTILINE,
)
_DECL_F77_RE = re.compile(
    r'^\s*' + _TYPE_KEYWORD + _KIND + r'\s+([A-Za-z_](?:(?!::).)*)$',
    re.IGNORECASE | re.MULTILINE,
)

_FORTRAN_TYPES = {
    "INTEGER": ParameterType.INTEGER,
    "REAL": ParameterType.NUMBER,
    "DOUBLE PRECISION": ParameterType.NUMBER,
    "LOGICAL": ParameterType.BOOLEAN,
    "CHARACTER": ParameterType.STRING,
}


def _unit_body(source: str, start: int) -> str:
    """Texte de l'unité qui commence à `start`, jusqu'à son END."""
    end = _UNIT_END_RE.search(source, start)
    return source[start:end.start() if end else len(source)]


def _split_top_level(text: str) -> list[str]:
    """Découpe sur les virgules hors parenthèses (`a(:), b, c(2, 3)`)."""
    parts, depth, current = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def _declared_types(body: str) -> dict[str, tuple[ParameterType, ParameterType | None, str]]:
    """{NOM: (type MCP, type des éléments si tableau, déclaration)} lus dans
    les déclarations de l'unité. Fortran ne type pas les arguments dans la
    signature : sans ça, tous les paramètres retombaient sur `str` et le
    pilote généré passait `IS_PRIME("42")` à une fonction qui attend un
    INTEGER (relevé le 2026-10-13 en régénérant l'exemple Fortran ; seul
    l'enrichissement LLM corrigeait parfois les types, de façon aléatoire)."""
    types: dict[str, tuple[ParameterType, ParameterType | None, str]] = {}
    matches = [(m.group(1), m.group(2), m.group(3)) for m in _DECL_RE.finditer(body)]
    matches += [(m.group(1), "", m.group(2)) for m in _DECL_F77_RE.finditer(body)]
    for type_word, attributes, names in matches:
        base_name = re.sub(r"\s+", " ", type_word.upper())
        base = _FORTRAN_TYPES.get(base_name)
        if base is None:
            continue
        attrs = (attributes or "").upper()
        for var in _split_top_level(names):
            var_name = re.match(r"(\w+)", var)
            if not var_name:
                continue
            is_array = "DIMENSION" in attrs or "(" in var
            if base is ParameterType.STRING and "(" in var and "DIMENSION" not in attrs:
                is_array = False  # CHARACTER s(*) : longueur, pas un tableau
            declared = f"{base_name} {var.strip()}"
            if is_array:
                types[var_name.group(1).upper()] = (ParameterType.ARRAY, base, declared)
            else:
                types[var_name.group(1).upper()] = (base, None, declared)
    return types


def _add_unit(
    name: str,
    kind: str,
    raw_params: str,
    prefix: str,
    relative_path: str,
    seen: set[str],
    tools: list[DiscoveredTool],
    module_name: str = "",
    declared: dict | None = None,
) -> None:
    if name.upper() in _RESERVED_FORTRAN:
        return
    if len(name) < 2:
        return

    func_slug = _SLUG_RE.sub("_", name.lower()).strip("_") or kind
    slug = f"{prefix}_{func_slug}" if prefix else func_slug
    if slug in seen:
        return
    seen.add(slug)

    params = _parse_params(raw_params, declared or {})

    tools.append(DiscoveredTool(
        name=slug,
        description=f"Fortran {kind} : {name.upper()}",
        parameters=params,
        tags=["codebase", relative_path, kind],
        metadata={
            "file": relative_path,
            "function": name.upper(),
            "type": kind,
            "module": module_name,
            "language": "fortran",
        },
    ))


def _parse_params(raw: str, declared: dict | None = None) -> list[ToolParameter]:
    """Parse les arguments Fortran : noms dans la signature, types dans les
    déclarations de l'unité (`declared`, voir _declared_types) ; chaîne par
    défaut quand aucune déclaration n'est trouvée."""
    declared = declared or {}
    if not raw.strip():
        return []

    params = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if part.upper() in _RESERVED_FORTRAN:
            continue
        if not re.match(r'^\w+$', part):
            continue

        slug = _SLUG_RE.sub("_", part.lower()).strip("_") or "arg"
        if slug in _RESERVED:
            slug = slug + "_"

        ptype, items_type, declaration = declared.get(part.upper(), (ParameterType.STRING, None, part.upper()))
        params.append(ToolParameter(
            name=slug,
            type=ptype,
            items_type=items_type,
            description=declaration,
            required=True,
        ))

    return params[:16]  # limite raisonnable
