"""
Parser Rust pour la découverte codebase.
Utilise des expressions régulières sur les fichiers .rs.

Formats supportés :
  pub fn function_name(param: Type) -> ReturnType
  pub async fn function_name(params) -> ReturnType
  pub fn method(&self, param: Type) -> ReturnType   (impl block)
  pub(crate) fn function_name(params) -> ReturnType

Seules les fonctions pub / pub(crate) sont extraites.
"""
from __future__ import annotations

import keyword as _kw
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

# Rustdoc : /// lignes consécutives juste avant la déclaration
_RUSTDOC_RE = re.compile(r'(?:[ \t]*///[^\n]*\n)+')

# Fonction Rust publique
_FUNC_RE = re.compile(
    r'\bpub(?:\([^)]*\))?\s+'       # pub ou pub(crate), pub(super)...
    r'(?:async\s+)?'                # async optionnel
    r'(?:unsafe\s+)?'              # unsafe optionnel
    r'(?:extern\s+"[^"]*"\s+)?'    # extern "C" optionnel
    r'fn\s+'                       # fn obligatoire
    r'([\w$]+)'                    # nom de la fonction
    r'(?:<[^>]*>)?'                # generics optionnels <T: Trait>
    r'\s*\(([^)]*)\)',             # paramètres
    re.MULTILINE,
)

# Détecte le contexte impl pour récupérer le nom du type
_IMPL_RE = re.compile(r'\bimpl(?:<[^>]*>)?\s+([\w:]+)', re.MULTILINE)

_SKIP_NAMES = {"main", "new", "default", "clone", "drop", "fmt"}
_SKIP_PREFIXES = ("_",)

_RESERVED = set(_kw.kwlist + _kw.softkwlist) | {
    # JS builtins problématiques dans les schemas MCP
    "constructor", "prototype", "__proto__",
}

# Mapping types Rust >> ParameterType
_RUST_TYPE_MAP: dict[str, ParameterType] = {
    "i8": ParameterType.INTEGER,
    "i16": ParameterType.INTEGER,
    "i32": ParameterType.INTEGER,
    "i64": ParameterType.INTEGER,
    "i128": ParameterType.INTEGER,
    "isize": ParameterType.INTEGER,
    "u8": ParameterType.INTEGER,
    "u16": ParameterType.INTEGER,
    "u32": ParameterType.INTEGER,
    "u64": ParameterType.INTEGER,
    "u128": ParameterType.INTEGER,
    "usize": ParameterType.INTEGER,
    "f32": ParameterType.NUMBER,
    "f64": ParameterType.NUMBER,
    "bool": ParameterType.BOOLEAN,
    "str": ParameterType.STRING,
    "String": ParameterType.STRING,
    "char": ParameterType.STRING,
}


class RustParser:
    """Extrait les fonctions publiques de fichiers Rust via regex."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        if path.name.endswith("_test.rs") or path.name == "build.rs":
            return []
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        # Ignore les modules de test (#[cfg(test)])
        if _is_test_module(source):
            return []

        relative_path = str(path.relative_to(root)).replace("\\", "/")
        module_name = _detect_module_name(path)

        cleaned = _BLOCK_COMMENT_RE.sub(" ", source)
        cleaned = _LINE_COMMENT_RE.sub("", cleaned)

        # Construit une map position >> impl type pour les méthodes
        impl_contexts = _build_impl_contexts(cleaned)

        tools: list[DiscoveredTool] = []
        seen: set[str] = set()

        for m in _FUNC_RE.finditer(cleaned):
            func_name = m.group(1)
            raw_params = m.group(2).strip()

            if func_name in _SKIP_NAMES:
                continue
            if any(func_name.startswith(p) for p in _SKIP_PREFIXES):
                continue

            # Détermine le préfixe : type impl si méthode, sinon module
            impl_type = _find_impl_at_pos(impl_contexts, m.start())
            prefix = _SLUG_RE.sub("_", impl_type.lower()).strip("_") if impl_type else module_name

            func_slug = _SLUG_RE.sub("_", func_name.lower()).strip("_") or "func"
            slug = f"{prefix}_{func_slug}" if prefix else func_slug

            if slug in seen:
                continue
            seen.add(slug)

            description = _extract_rustdoc(source, m.start()) or f"pub fn {func_name}(...)"
            params = _parse_params(raw_params)

            tools.append(DiscoveredTool(
                name=slug,
                description=description,
                parameters=params,
                tags=["codebase", relative_path],
                metadata={
                    "file": relative_path,
                    "function": func_name,
                    # `module_name` (nom de fichier) n'est qu'un préfixe
                    # COSMÉTIQUE pour le nom d'outil (slug ci-dessus) — pas
                    # un vrai module Rust. Compiler+exécuter directement un
                    # fichier .rs autonome (`rustc file.rs`) ne crée aucun
                    # module implicite nommé d'après le fichier : qualifier
                    # l'appel avec (ex: `utils::is_prime(...)`) échouerait à
                    # la compilation (même bug que Julia/TypeScript).
                    "module": "",
                    "impl_type": impl_type,
                    "language": "rust",
                },
            ))

        return tools


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _detect_module_name(path: Path) -> str:
    name = path.stem
    if name == "mod" or name == "lib" or name == "main":
        name = path.parent.name
    return _SLUG_RE.sub("_", name.lower()).strip("_")


def _is_test_module(source: str) -> bool:
    """Vérifie si tout le fichier est un module de test."""
    return bool(re.search(r'#\[cfg\(test\)\]', source))


def _build_impl_contexts(cleaned: str) -> list[tuple[int, int, str]]:
    """Retourne une liste (start, end, type_name) pour chaque bloc impl {}."""
    contexts = []
    for m in _IMPL_RE.finditer(cleaned):
        type_name = m.group(1).split("::")[-1]
        # Cherche l'accolade ouvrante après le match
        brace_start = cleaned.find("{", m.end())
        if brace_start == -1:
            continue
        # Trouve l'accolade fermante correspondante
        depth, pos = 1, brace_start + 1
        while pos < len(cleaned) and depth > 0:
            if cleaned[pos] == "{":
                depth += 1
            elif cleaned[pos] == "}":
                depth -= 1
            pos += 1
        contexts.append((brace_start, pos, type_name))
    return contexts


def _find_impl_at_pos(contexts: list[tuple[int, int, str]], pos: int) -> str:
    """Retourne le nom du type impl contenant la position donnée."""
    for start, end, type_name in contexts:
        if start < pos < end:
            return type_name
    return ""


def _extract_rustdoc(source: str, pos: int) -> str:
    """Extrait le commentaire Rustdoc (///) précédant la déclaration."""
    preceding = source[max(0, pos - 600):pos]
    m = _RUSTDOC_RE.search(preceding)
    if not m:
        return ""
    # Vérifie qu'il n'y a que des attributs #[...] entre le doc et la fn
    after = preceding[m.end():]
    if re.search(r'[;{}]', after):
        return ""
    text = m.group(0)
    text = re.sub(r'^\s*///\s?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:200]


def _parse_params(raw: str) -> list[ToolParameter]:
    """Parse les paramètres Rust : `name: Type`, `&self`, `mut name: Type`."""
    if not raw.strip():
        return []

    params: list[ToolParameter] = []
    for part in _split_params(raw):
        part = part.strip()
        if not part:
            continue

        # Ignore self, &self, &mut self
        if re.match(r'^&?(?:mut\s+)?self$', part):
            continue

        # Retire mut
        part = re.sub(r'^mut\s+', '', part)

        if ":" not in part:
            continue

        param_name, rust_type = part.split(":", 1)
        param_name = param_name.strip()
        rust_type = rust_type.strip()

        if not param_name or param_name.startswith("_"):
            continue

        slug = _SLUG_RE.sub("_", param_name.lower()).strip("_") or "param"
        if slug in _RESERVED:
            slug = slug + "_"

        # Type de base : retire &, &mut, lifetime, generics
        base = re.sub(r"'[\w]+\s*", "", rust_type)       # lifetimes
        base = re.sub(r"&(?:mut\s+)?", "", base)          # références
        base = re.sub(r"<[^>]*>", "", base)               # generics
        base = re.sub(r"\[.*?\]", "", base)               # slices
        base = base.strip().split("::")[-1]               # module path

        py_type = _RUST_TYPE_MAP.get(base, ParameterType.STRING)

        params.append(ToolParameter(
            name=slug,
            type=py_type,
            description=rust_type,
            required=True,
        ))

    return params


def _split_params(raw: str) -> list[str]:
    """Divise les paramètres en gérant les génériques et closures imbriqués."""
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
