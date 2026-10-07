"""
Parser Bash/Shell pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .sh / .bash.

Formats supportés :
  function_name() { ... }
  function function_name { ... }
  function function_name() { ... }

Extrait les fonctions publiques (pas de préfixe _ ou __).
Extrait les commentaires # précédant la déclaration comme description.
"""
from __future__ import annotations

import keyword as _kw
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Commentaires # consécutifs (description)
_COMMENT_RE = re.compile(r'(?:[ \t]*#[^\n]*\n)+')

# Déclaration de fonction Bash
_FUNC_RE = re.compile(
    r'(?:^|\n)'
    r'[ \t]*'
    r'(?:function[ \t]+)?'          # mot-clé function optionnel
    r'([a-zA-Z_][a-zA-Z0-9_:-]*)'  # nom (peut contenir : et -)
    r'[ \t]*\(\)',                  # parenthèses vides obligatoires ou
    re.MULTILINE,
)

# Forme alternative : function name { sans ()
_FUNC_KW_RE = re.compile(
    r'(?:^|\n)'
    r'[ \t]*function[ \t]+'
    r'([a-zA-Z_][a-zA-Z0-9_:-]*)'
    r'[ \t]*\{',
    re.MULTILINE,
)

_SKIP_PREFIXES = ("_", "__")
_SKIP_NAMES = {"main", "usage", "help", "version"}

_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    "constructor", "prototype", "__proto__",
}


class BashParser:
    """Extrait les fonctions publiques de fichiers Bash/Shell via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        # Vérifie que c'est bien un script shell (shebang ou extension)
        if not _is_shell_script(source, path):
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")
        module_name = _SLUG_RE.sub("_", path.stem.lower()).strip("_")

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        # Collecte toutes les fonctions des deux patterns
        matches: list[tuple[int, str]] = []
        for m in _FUNC_RE.finditer(source):
            matches.append((m.start(), m.group(1)))
        for m in _FUNC_KW_RE.finditer(source):
            matches.append((m.start(), m.group(1)))

        for pos, func_name in sorted(matches):
            if any(func_name.startswith(p) for p in _SKIP_PREFIXES):
                continue
            if func_name.lower() in _SKIP_NAMES:
                continue

            func_slug = _SLUG_RE.sub("_", func_name.lower()).strip("_") or "func"
            slug = f"{module_name}_{func_slug}" if module_name else func_slug

            if slug in seen:
                continue
            seen.add(slug)

            description = _extract_comment(source, pos) or f"{func_name}()"
            # Extrait les arguments documentés dans le corps
            params = _extract_params_from_body(source, pos)

            tools.append(DiscoveredTool(
                name=slug,
                description=description,
                parameters=params,
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": func_name,
                    "language": "bash",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _is_shell_script(source: str, path: Path) -> bool:
    """Vérifie que le fichier est bien un script shell."""
    if path.suffix.lower() in (".sh", ".bash"):
        return True
    first_line = source.split("\n", 1)[0] if source else ""
    return bool(re.match(r'^#!.*(bash|sh|zsh|dash)', first_line))


def _extract_comment(source: str, pos: int) -> str:
    """Extrait le commentaire # précédant la déclaration."""
    preceding = source[max(0, pos - 500):pos]
    m = _COMMENT_RE.search(preceding)
    if not m:
        return ""
    after = preceding[m.end():]
    if re.search(r'\S', after):
        return ""
    text = m.group(0)
    text = re.sub(r'^[ \t]*#\s?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+', ' ', text).strip()
    # Ignore les séparateurs (####...)
    if re.match(r'^[#=\-]+$', text):
        return ""
    return text[:200]


def _extract_params_from_body(source: str, func_pos: int) -> list[ToolParameter]:
    """
    Extrait les paramètres nommés depuis le corps de la fonction.

    Deux conventions bash courantes, toutes deux prises en charge :
      1. `local varname=$1` / `local varname="${1}"` — nom descriptif.
      2. `$1`/`$2`/... référencés directement dans le corps sans alias
         (ex: `echo "$1" | rev`) — nommés positionnellement `arg1`, `arg2`...
    Plus `"$@"`/`"$*"` (fonction variadique, ex: `for n in "$@"`), traduit en
    un unique paramètre de type liste si aucun `$N` positionnel n'est trouvé.
    """
    # Trouve l'accolade ouvrante
    body_start = source.find("{", func_pos)
    if body_start == -1:
        return []
    body = source[body_start:body_start + 600]

    named: dict[int, str] = {}
    for m in re.finditer(
        r'\blocal\b\s+([a-zA-Z_]\w*)\s*=\s*["\']?\$\{?(\d+)',
        body,
    ):
        pos_idx = int(m.group(2))
        param_name = m.group(1)
        if pos_idx not in named and not param_name.startswith("_"):
            named[pos_idx] = param_name

    numbered_refs = {int(n) for n in re.findall(r'\$\{?(\d+)\}?', body)}
    all_positions = set(named) | numbered_refs

    params: list[ToolParameter] = []
    for pos_idx in sorted(all_positions):
        param_name = named.get(pos_idx, f"arg{pos_idx}")
        slug = _SLUG_RE.sub("_", param_name.lower()).strip("_") or "param"
        if slug in _RESERVED:
            slug = slug + "_"
        params.append(ToolParameter(
            name=slug,
            type=ParameterType.STRING,
            description=f"${pos_idx}",
            required=True,
        ))

    if not params and re.search(r'"\$@"|\$@|"\$\*"|\$\*', body):
        params.append(ToolParameter(
            name="args",
            type=ParameterType.ARRAY,
            description="Arguments (\"$@\")",
            required=True,
        ))

    return params[:8]
