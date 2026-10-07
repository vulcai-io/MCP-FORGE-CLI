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
            _add_unit(name, "subroutine", raw_params, prefix, relative_path, seen, tools, real_module)

        # Functions
        for m in _FUNC_RE.finditer(normalized):
            name = m.group(1)
            raw_params = m.group(2) or ""
            if not name:
                continue
            _add_unit(name, "function", raw_params, prefix, relative_path, seen, tools, real_module)

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


def _add_unit(
    name: str,
    kind: str,
    raw_params: str,
    prefix: str,
    relative_path: str,
    seen: set[str],
    tools: list[DiscoveredTool],
    module_name: str = "",
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

    params = _parse_params(raw_params)

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


def _parse_params(raw: str) -> list[ToolParameter]:
    """Parse les arguments Fortran (noms seulement, pas de types dans la signature)."""
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

        params.append(ToolParameter(
            name=slug,
            type=ParameterType.STRING,
            description=part.upper(),
            required=True,
        ))

    return params[:16]  # limite raisonnable
