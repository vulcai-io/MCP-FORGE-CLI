"""
Parser Elixir pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .ex / .exs.

Formats supportés :
  def function_name(param1, param2) do
  def function_name(param1, param2), do: expr
  defmacro macro_name(param) do

Seules les fonctions publiques (def/defmacro) sont extraites.
Les fonctions privées (defp/defmacrop) sont ignorées.
Gère les contextes defmodule pour le préfixe.
Extrait les @doc comme description.
"""
from __future__ import annotations

import keyword as _kw
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_COMMENT_RE = re.compile(r"#[^\n]*")

# @doc "..." ou @doc """..."""
_DOC_RE = re.compile(
    r'@doc\s+(?:"""(.*?)"""|(\"[^\"]*\"))',
    re.DOTALL,
)

# def ou defmacro (publiques) — ignore defp / defmacrop
_FUNC_RE = re.compile(
    r'^\s*def(?:macro)?\s+'
    r'([a-z_]\w*[?!]?)'         # nom (peut finir par ? ou !)
    r'\s*\(([^)]*)\)',           # paramètres
    re.MULTILINE,
)

# defmodule pour le contexte
_MODULE_RE = re.compile(
    r'\bdefmodule\s+([\w.]+)',
    re.MULTILINE,
)

_SKIP_NAMES = {
    "init", "start", "stop", "terminate", "handle_call",
    "handle_cast", "handle_info", "handle_event",
    "code_change", "format_status",
}

_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    "constructor", "prototype", "__proto__",
}


class ElixirParser:
    """Extrait les fonctions publiques de fichiers Elixir via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        if any(x in path.name for x in ("_test.exs", "test_helper", "mix.exs")):
            return []
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")

        cleaned = _COMMENT_RE.sub("", source)

        module_name = _detect_module(cleaned)
        prefix = _SLUG_RE.sub("_", module_name.split(".")[-1].lower()).strip("_") if module_name else \
                 _SLUG_RE.sub("_", path.stem.lower()).strip("_")

        # Pré-calcule les positions des @doc
        doc_map = _build_doc_map(source)

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        for m in _FUNC_RE.finditer(cleaned):
            func_name = m.group(1)
            raw_params = m.group(2).strip()

            if func_name in _SKIP_NAMES:
                continue

            func_slug = _SLUG_RE.sub("_", func_name.lower()).strip("_") or "func"
            # Retire les ? et ! du slug
            func_slug = func_slug.rstrip("_")
            slug = f"{prefix}_{func_slug}" if prefix else func_slug

            if slug in seen:
                continue
            seen.add(slug)

            description = _find_doc_before(doc_map, m.start()) or f"def {func_name}(...)"
            params = _parse_params(raw_params)

            tools.append(DiscoveredTool(
                name=slug,
                description=description,
                parameters=params,
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": func_name,
                    "module": module_name,
                    "language": "elixir",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _detect_module(cleaned: str) -> str:
    """Extrait le nom du module principal du fichier."""
    m = _MODULE_RE.search(cleaned)
    return m.group(1) if m else ""


def _build_doc_map(source: str) -> list[tuple[int, str]]:
    """Retourne une liste (end_pos, doc_text) pour chaque @doc."""
    result = []
    for m in _DOC_RE.finditer(source):
        text = m.group(1) or m.group(2) or ""
        text = text.strip().strip('"')
        text = re.sub(r"\s+", " ", text).strip()[:200]
        result.append((m.end(), text))
    return result


def _find_doc_before(doc_map: list[tuple[int, str]], pos: int) -> str:
    """Retourne le dernier @doc avant la position donnée (dans un rayon de 300 chars)."""
    best = ""
    for end_pos, text in doc_map:
        if end_pos < pos and (pos - end_pos) < 300:
            best = text
    return best


def _parse_params(raw: str) -> list[ToolParameter]:
    """
    Parse les paramètres Elixir.
    En Elixir le typage est dynamique ; on extrait juste les noms.
    Gère : param, param \\ default, {key, value}, _ignored
    """
    if not raw.strip():
        return []

    params: list[ToolParameter] = []
    for part in _split_params(raw):
        part = part.strip()
        if not part:
            continue

        # Retire la valeur par défaut (\\ default)
        part = part.split("\\\\")[0].strip()

        # Ignore les paramètres anonymes ou de pattern matching complexe
        if part.startswith("_") or part.startswith("{") or part.startswith("%"):
            continue

        # Extrait le nom simple (premier mot)
        name_match = re.match(r'^([a-z_]\w*)', part)
        if not name_match:
            continue

        param_name = name_match.group(1)
        if param_name.startswith("_"):
            continue

        slug = _SLUG_RE.sub("_", param_name.lower()).strip("_") or "param"
        if slug in _RESERVED:
            slug = slug + "_"

        params.append(ToolParameter(
            name=slug,
            type=ParameterType.STRING,
            description="",
            required=True,
        ))

    return params


def _split_params(raw: str) -> list[str]:
    """Divise les paramètres en gérant les tuples et maps imbriqués."""
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
