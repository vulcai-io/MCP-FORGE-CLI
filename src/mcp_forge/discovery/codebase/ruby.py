"""
Parser Ruby pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .rb.

Formats supportés :
  def method_name(param1, param2)
  def self.method_name(param)
  def method_name(param = default, *args, **opts, &block)

Extrait les méthodes publiques (avant tout marqueur private/protected).
RDoc commentaires # extraits comme description.
"""
from __future__ import annotations

import keyword as _kw
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_COMMENT_RE = re.compile(r"#[^\n]*")

# RDoc : lignes # consécutives juste avant def
_RDOC_RE = re.compile(r'(?:[ \t]*#[^\n]*\n)+')

# Déclaration de méthode Ruby
_METHOD_RE = re.compile(
    r'^\s*def\s+'
    r'(self\.)?' 	                # méthode de classe optionnelle
    r'([\w!?]+)'                    # nom (peut finir par ! ou ?)
    r'(?:\s*\(([^)]*)\))?',        # paramètres optionnels
    re.MULTILINE,
)

# Détecte les marqueurs private/protected (sur leur propre ligne)
_ACCESS_RE = re.compile(r'^\s*(private|protected)\s*$', re.MULTILINE)

_SKIP_NAMES = {
    "initialize", "initialize_copy", "method_missing",
    "respond_to_missing?", "inherited", "included", "extended",
}
_SKIP_PREFIXES = ("_",)

_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    "constructor", "prototype", "__proto__",
}


class RubyParser:
    """Extrait les méthodes publiques de fichiers Ruby via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        if "_test" in path.name or "_spec" in path.name or path.name.startswith("test_"):
            return []
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")
        class_name = _detect_class_name(source)
        module_name = _SLUG_RE.sub("_", path.stem.lower()).strip("_")
        prefix = _SLUG_RE.sub("_", class_name.lower()).strip("_") if class_name else module_name

        # Détermine la position du premier private/protected
        private_pos = _first_private_pos(source)

        cleaned = _COMMENT_RE.sub("", source)

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        for m in _METHOD_RE.finditer(cleaned):
            # Ignore les méthodes après private/protected (sauf self.)
            if private_pos and m.start() > private_pos and not m.group(1):
                continue

            func_name = m.group(2)
            raw_params = m.group(3) or ""

            if func_name in _SKIP_NAMES:
                continue
            if any(func_name.startswith(p) for p in _SKIP_PREFIXES):
                continue

            func_slug = _SLUG_RE.sub("_", func_name.lower()).strip("_") or "method"
            slug = f"{prefix}_{func_slug}" if prefix else func_slug

            if slug in seen:
                continue
            seen.add(slug)

            description = _extract_rdoc(source, m.start()) or f"def {func_name}(...)"
            params = _parse_params(raw_params)

            tools.append(DiscoveredTool(
                name=slug,
                description=description,
                parameters=params,
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": func_name,
                    "class": class_name,
                    "language": "ruby",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _detect_class_name(source: str) -> str:
    """Extrait le nom de la classe/module principale du fichier Ruby."""
    cleaned = _COMMENT_RE.sub("", source)
    for m in re.finditer(r'\b(?:class|module)\s+([\w:]+)', cleaned):
        name = m.group(1).split("::")[-1]
        if len(name) >= 2:
            return name
    return ""


def _first_private_pos(source: str) -> int | None:
    """Retourne la position du premier marqueur private/protected autonome."""
    m = _ACCESS_RE.search(source)
    return m.start() if m else None


def _extract_rdoc(source: str, pos: int) -> str:
    """Extrait le commentaire RDoc (#) précédant la déclaration."""
    preceding = source[max(0, pos - 500):pos]
    m = _RDOC_RE.search(preceding)
    if not m:
        return ""
    after = preceding[m.end():]
    if re.search(r'[;{}]|^\s*def\b', after, re.MULTILINE):
        return ""
    text = m.group(0)
    text = re.sub(r'^\s*#\s?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:200]


def _parse_params(raw: str) -> list[ToolParameter]:
    """Parse les paramètres Ruby : `name`, `name = default`, `*args`, `**opts`, `&block`."""
    if not raw.strip():
        return []

    params: list[ToolParameter] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue

        # Retire la valeur par défaut
        part = part.split("=")[0].strip()

        # Retire les préfixes spéciaux
        if part.startswith("&"):
            continue  # block param >> ignoré
        is_splat = part.startswith("*")
        part = part.lstrip("*").strip()

        if not part:
            continue

        slug = _SLUG_RE.sub("_", part.lower()).strip("_") or "param"
        if slug in _RESERVED:
            slug = slug + "_"

        params.append(ToolParameter(
            name=slug,
            type=ParameterType.STRING,
            description="splat" if is_splat else "",
            required=not is_splat,
        ))

    return params
