"""
Parser COBOL pour la découverte codebase.
Supporte le format fixe (COBOL 74/85) et le format libre (COBOL 2002+).

Unités extraites comme TOOLS MCP (valeur externe réelle) :
  - Sous-programmes isolés (PROGRAM-ID + PROCEDURE DIVISION USING...) —
    réellement exécutables, voir _extract_subprograms
  - Programmes appelables (CALL 'NOM') — point de contact externe, même
    si le programme appelé n'est pas lui-même dans ce codebase

Unités volontairement PAS extraites comme tools (décision du 2026-10-06,
après test sur un vrai codebase legacy, aws-mainframe-modernization-
carddemo) :
  - Paragraphes et sections de la PROCEDURE DIVISION d'un programme
    monolithique (style COBOL historique, état partagé en WORKING-
    STORAGE) : ce ne sont QUE des points de contrôle INTERNES à un
    programme, jamais exécutables isolément, jamais un point de contact
    externe. Sur du code mainframe réel (pas les fixtures synthétiques
    modernes), ils représentent l'écrasante majorité des unités
    trouvées (194 sur 195 dans ce test) et ne produisent que des tools
    MCP qui renvoient toujours la même erreur statique — du bruit pur,
    aucune valeur pour un agent qui a justement besoin de "toucher" des
    entrées/sorties externes, pas la plomberie interne d'un programme.
    FUNCTION-ID (COBOL moderne) reste extrait : une fonction nommée est
    conceptuellement un point d'entrée, même si ses paramètres ne sont
    pas encore isolés.

Détection automatique du format :
  - Fixed : colonne 7 contient *, D, -, / sur une fraction des lignes
  - Free  : pas de contrainte de colonnes
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

# Seuil : si plus de 20% des lignes ont un caractère valide en col 7 >> fixed
_FIXED_THRESHOLD = 0.20


class CobolParser:
    """Extrait les points de contact externes (sous-programmes isolés,
    FUNCTION-ID, CALL externes) de fichiers COBOL — pas les paragraphes/
    sections internes d'un programme monolithique, voir le docstring du
    module."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")
        program_name = _detect_program_name(source) or path.stem

        fmt = _detect_format(source)
        normalized = _normalize(source, fmt)

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        prefix = _SLUG_RE.sub("_", program_name.lower()).strip("_")

        # FUNCTION-ID (COBOL moderne) — point d'entrée nommé, gardé même si
        # ses paramètres ne sont pas encore isolés. Les paragraphes/sections
        # de la PROCEDURE DIVISION ne sont PAS extraits comme tools — voir
        # la décision architecturale dans le docstring en tête de fichier.
        for m in re.finditer(r'^\s*FUNCTION-ID\.\s+([\w-]+)', normalized, re.IGNORECASE | re.MULTILINE):
            _add_paragraph(m.group(1), "user-defined function", prefix, relative_path, seen, tools)

        # Sous-programmes modernes, isolés, avec paramètres+sortie explicites
        # (voir _extract_subprograms) — seule catégorie réellement exécutable
        # (routée vers server_codebase_cobol.py.j2).
        # Préfixe par le nom de FICHIER, pas le premier PROGRAM-ID du
        # fichier (`prefix` ci-dessus) : un fichier moderne contient
        # typiquement PLUSIEURS sous-programmes indépendants (un par
        # fonction), chacun avec son propre nom déjà significatif —
        # préfixer "FACTORIAL" par "IS_PRIME" (le premier PROGRAM-ID du
        # fichier) serait trompeur.
        file_prefix = _SLUG_RE.sub("_", path.stem.lower()).strip("_")
        tools += _extract_subprograms(normalized, file_prefix, relative_path, seen, fmt)

        # CALL externes (programmes appelés)
        for m in re.finditer(
            r'\bCALL\s+[\'"]?([\w-]+)[\'"]?',
            normalized, re.IGNORECASE,
        ):
            called = m.group(1)
            if called.upper() not in {"SYSTEM", "CBL_COPY_FILE", "CBL_DELETE_FILE"}:
                slug = f"call_{_SLUG_RE.sub('_', called.lower()).strip('_')}"
                if slug not in seen:
                    seen.add(slug)
                    tools.append(DiscoveredTool(
                        name=slug,
                        description=f"CALL '{called}' — programme externe appelé",
                        parameters=_parse_using_clause(normalized, m.end()),
                        tags=["codebase", relative_path, "external-call"],
                        metadata={
                            "file": relative_path,
                            "function": called,
                            "type": "call",
                            "language": "cobol",
                        },
                    ))

        return tools


# ------------------------------------------------------------------
# Format detection & normalization
# ------------------------------------------------------------------

def _detect_format(source: str) -> str:
    """Retourne 'fixed' ou 'free' selon le contenu du fichier."""
    lines = source.splitlines()
    if not lines:
        return "free"
    fixed_indicators = sum(
        1 for line in lines
        if len(line) >= 7 and line[6] in ("*", "D", "d", "-", "/", " ")
        and len(line) > 10
    )
    ratio = fixed_indicators / max(len(lines), 1)
    return "fixed" if ratio >= _FIXED_THRESHOLD else "free"


def _normalize(source: str, fmt: str) -> str:
    """Normalise le source en retirant les artefacts du format fixe."""
    if fmt == "free":
        # Retire les commentaires *> style libre
        source = re.sub(r'\*>.*', '', source)
        return source

    # Format fixe : traite ligne par ligne
    result = []
    for line in source.splitlines():
        # Ligne trop courte >> gardée telle quelle
        if len(line) < 7:
            result.append(line)
            continue
        indicator = line[6]
        # Commentaire (* ou /) >> ligne vide
        if indicator in ("*", "/"):
            result.append("")
            continue
        # Continuation (-) >> colle à la ligne précédente
        if indicator == "-":
            code = line[11:72].rstrip() if len(line) > 11 else ""
            if result:
                result[-1] = result[-1].rstrip() + " " + code.lstrip("\"'")
            continue
        # Code normal : colonnes 7-72 (Area A+B)
        code = line[6:72].rstrip() if len(line) > 6 else ""
        result.append(code)

    return "\n".join(result)


# ------------------------------------------------------------------
# Extraction helpers
# ------------------------------------------------------------------

def _detect_program_name(source: str) -> str:
    """Extrait le PROGRAM-ID ou FUNCTION-ID."""
    m = re.search(r'\b(?:PROGRAM-ID|FUNCTION-ID)\.\s+([\w-]+)', source, re.IGNORECASE)
    return m.group(1) if m else ""


_RESERVED_COBOL_WORDS = {
    "END", "STOP", "EXIT", "GOBACK", "CONTINUE", "NEXT",
    "SENTENCE", "IF", "ELSE", "WHEN", "PERFORM", "MOVE",
    "COMPUTE", "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE",
    "EVALUATE", "SEARCH", "READ", "WRITE", "REWRITE",
    "DELETE", "START", "OPEN", "CLOSE", "DISPLAY", "ACCEPT",
    "CALL", "SET", "INITIALIZE", "INSPECT", "STRING",
    "UNSTRING", "SORT", "MERGE", "RELEASE", "RETURN",
    "DECLARATIVES", "DIVISION", "SECTION",
    # Scope terminators composés (END-xxx) — capturés en un seul token par
    # `[\w-]+` (le tiret fait partie de la classe), donc pas couverts par
    # les mots simples ci-dessus (ex: "END" seul ne matche pas "END-PERFORM").
    # Trouvé en testant sur du vrai code legacy (aws-mainframe-modernization
    # -carddemo) : une ligne isolée "END-PERFORM." était prise pour un nom de
    # paragraphe, polluant les tools générés (end_perform, end_if, end_read...).
    "END-ACCEPT", "END-ADD", "END-CALL", "END-COMPUTE", "END-DELETE",
    "END-DISPLAY", "END-DIVIDE", "END-EVALUATE", "END-IF", "END-INITIALIZE",
    "END-INSPECT", "END-INVOKE", "END-JSON", "END-MERGE", "END-MULTIPLY",
    "END-PERFORM", "END-READ", "END-RECEIVE", "END-RELEASE", "END-RETURN",
    "END-REWRITE", "END-SEARCH", "END-SEND", "END-SET", "END-SORT",
    "END-START", "END-STRING", "END-SUBTRACT", "END-UNSTRING", "END-WRITE",
    "END-XML",
    # Terminateurs de bloc EXEC (EXEC SQL/CICS/DLI ... END-EXEC[2]) — PAS un
    # verbe COBOL, une construction distincte, donc pas couverte par la
    # liste ci-dessus. Trouvé sur le même codebase (aws-mainframe-
    # modernization-carddemo) : "END-EXEC." seul sur sa ligne apparaît des
    # dizaines de fois (un par bloc EXEC CICS/SQL), générant un flot de
    # faux "paragraphes" dupliqués (call_cob_end_exec, _2, _3... jusqu'à
    # _10+) qui polluent le serveur MCP généré.
    "END-EXEC", "END-EXEC2",
}


def _is_valid_paragraph(name: str) -> bool:
    """Vérifie qu'un nom est un paragraphe valide (pas un mot réservé COBOL)."""
    upper = name.upper()
    if upper in _RESERVED_COBOL_WORDS:
        return False
    if re.match(r'^\d', name):
        return False
    if len(name) < 2:
        return False
    return bool(re.match(r'^[\w-]+$', name))


def _add_paragraph(
    name: str,
    kind: str,
    prefix: str,
    relative_path: str,
    seen: set[str],
    tools: list[DiscoveredTool],
) -> None:
    func_slug = _SLUG_RE.sub("_", name.lower()).strip("_") or "para"
    slug = f"{prefix}_{func_slug}" if prefix else func_slug
    if slug in seen:
        return
    seen.add(slug)
    tools.append(DiscoveredTool(
        name=slug,
        description=f"COBOL {kind} : {name.upper()}",
        parameters=[],
        tags=["codebase", relative_path, kind],
        metadata={
            "file": relative_path,
            "function": name.upper(),
            "type": kind,
            "language": "cobol",
        },
    ))


# ------------------------------------------------------------------
# Sous-programmes modernes (isolés, paramètres + sortie explicites)
# ------------------------------------------------------------------

# Un 01-level item typique de LINKAGE SECTION : "01 LS-N PIC 9(4)."
_LINKAGE_ITEM_RE = re.compile(
    r'^\s*01\s+([\w-]+)\s+PIC\s+([\w()V.,+-]+)\s*\.',
    re.IGNORECASE | re.MULTILINE,
)

_PROCEDURE_USING_RE = re.compile(
    r'\bPROCEDURE\s+DIVISION\s+USING\s+([\w\s,-]+?)\s*\.',
    re.IGNORECASE,
)


def _pic_to_type(pic: str) -> tuple[ParameterType, int | None]:
    """Déduit un ParameterType depuis une clause PIC COBOL.
    Retourne aussi la longueur max pour les champs alphanumériques
    (PIC X(n)) — nécessaire pour tronquer une valeur trop longue avant de
    la passer en littéral au driver généré (sinon erreur de compilation :
    un littéral VALUE plus long que le champ PIC cible est invalide)."""
    upper = pic.upper()
    if "X" in upper:
        m = re.search(r'X\((\d+)\)', upper)
        return ParameterType.STRING, (int(m.group(1)) if m else 1)
    if "V" in upper or "COMP" in upper or "." in upper:
        return ParameterType.NUMBER, None
    return ParameterType.INTEGER, None


def _cobol_name_to_slug(name: str) -> str:
    """LS-N -> n ; LS-RESULT -> result (retire le préfixe LS-/WS- usuel
    pour un nom de paramètre Python plus lisible que le nom COBOL brut)."""
    stripped = re.sub(r'^(LS|WS)-', '', name, flags=re.IGNORECASE)
    slug = _SLUG_RE.sub("_", stripped.lower()).strip("_") or "param"
    if slug in _RESERVED:
        slug = slug + "_"
    return slug


def _extract_subprograms(
    normalized: str,
    prefix: str,
    relative_path: str,
    seen: set[str],
    source_format: str,
) -> list[DiscoveredTool]:
    """Détecte les sous-programmes COBOL modernes, isolés : un PROGRAM-ID
    dont la PROCEDURE DIVISION a une clause USING avec 2+ paramètres, tous
    déclarés dans la LINKAGE SECTION de CE sous-programme (PIC connue). Par
    convention (le RETURNING sur un sous-programme CALL'é n'est pas
    implémenté par GnuCOBOL 3.2 — testé), le DERNIER paramètre de la
    clause USING est la sortie, passée par référence et mutée par le
    sous-programme plutôt que retournée.

    C'est la différence structurelle qui rend ces unités réellement
    exécutables de façon isolée (paramètres + sortie explicites, pas
    d'état global partagé) — contrairement aux paragraphes/sections d'un
    PROCEDURE DIVISION monolithique (voir le reste de ce module), qui
    restent seulement documentés, jamais exécutables."""
    tools: list[DiscoveredTool] = []

    # Découpe le fichier en unités par PROGRAM-ID (un sous-programme par
    # unité, du PROGRAM-ID jusqu'au PROGRAM-ID suivant ou la fin du fichier).
    boundaries = list(re.finditer(r'\bPROGRAM-ID\.\s+([\w-]+)', normalized, re.IGNORECASE))
    for i, m in enumerate(boundaries):
        name = m.group(1)
        start = m.end()
        end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(normalized)
        chunk = normalized[start:end]

        using_match = _PROCEDURE_USING_RE.search(chunk)
        if not using_match:
            continue
        # La virgule entre les noms de la clause USING est une séparation
        # facultative en COBOL ("USING LS-A, LS-B" et "USING LS-A LS-B"
        # sont équivalents) — trouvé sur du vrai code legacy (CSUTLDTC.cbl,
        # aws-mainframe-modernization-carddemo) : un sous-programme isolé
        # avec USING séparé par des virgules n'était jamais détecté
        # (le `.split()` sur espaces seuls gardait la virgule collée au
        # nom précédent, ex. "LS-DATE," au lieu de "LS-DATE").
        param_names = [p for p in re.split(r'[\s,]+', using_match.group(1)) if p]
        if len(param_names) < 2:
            continue  # il faut au moins 1 entrée + 1 sortie

        linkage_pics = {
            lm.group(1).upper(): lm.group(2)
            for lm in _LINKAGE_ITEM_RE.finditer(chunk)
        }
        if not all(p.upper() in linkage_pics for p in param_names):
            continue  # convention non respectée (PIC introuvable) — on ignore

        *input_names, output_name = param_names
        slug = f"{prefix}_{_SLUG_RE.sub('_', name.lower()).strip('_')}" if prefix else _SLUG_RE.sub('_', name.lower()).strip('_')
        if slug in seen:
            continue
        seen.add(slug)

        params: list[ToolParameter] = []
        cobol_params: list[dict] = []
        for pname in input_names:
            pic = linkage_pics[pname.upper()]
            ptype, max_len = _pic_to_type(pic)
            params.append(ToolParameter(
                name=_cobol_name_to_slug(pname),
                type=ptype,
                description=f"{pname.upper()} (PIC {pic})",
                required=True,
            ))
            cobol_params.append({"name": pname.upper(), "pic": pic, "ptype": ptype.value, "max_len": max_len})

        output_pic = linkage_pics[output_name.upper()]
        output_ptype, output_max_len = _pic_to_type(output_pic)

        tools.append(DiscoveredTool(
            name=slug,
            description=f"COBOL subprogram (moderne, isolé) : {name.upper()}",
            parameters=params,
            tags=["codebase", relative_path, "subprogram"],
            metadata={
                "file": relative_path,
                "function": name.upper(),
                "type": "subprogram",
                "language": "cobol",
                "cobol_source_format": source_format,
                "cobol_params": cobol_params,
                "cobol_output": {
                    "name": output_name.upper(), "pic": output_pic,
                    "ptype": output_ptype.value, "max_len": output_max_len,
                },
            },
        ))

    return tools


def _parse_using_clause(source: str, pos: int) -> list[ToolParameter]:
    """Extrait les paramètres d'un CALL ... USING ..."""
    window = source[pos:pos + 200]
    m = re.search(r'\bUSING\b(.*?)(?:\.|BY\s+(?:REFERENCE|VALUE|CONTENT)|\n\n)', window, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    params = []
    for var in re.findall(r'[\w-]+', m.group(1)):
        if var.upper() in _RESERVED_COBOL_WORDS or len(var) < 2:
            continue
        slug = _SLUG_RE.sub("_", var.lower()).strip("_") or "param"
        if slug in _RESERVED:
            slug = slug + "_"
        params.append(ToolParameter(
            name=slug,
            type=ParameterType.STRING,
            description=var.upper(),
            required=True,
        ))
    return params[:8]  # limite raisonnable
