"""
Discovery à partir d'un dossier de code source.

Langages supportés :
  - Python           >> python.py  (AST)
  - Lua              >> lua.py     (regex)
  - JavaScript / TypeScript >> js.py (regex)
  - C / C++          >> cpp.py     (regex sur headers .h/.hpp)
  - Java             >> java.py    (regex, méthodes public/protected)

Ce module détecte le langage dominant du projet,
puis délègue l'extraction au parser approprié.
"""
from __future__ import annotations

import os
from pathlib import Path

from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

from mcp_forge.console import EngineConsole
from mcp_forge.discovery.codebase.bash import BashParser
from mcp_forge.discovery.codebase.cobol import CobolParser
from mcp_forge.discovery.codebase.cpp import HEADER_EXTENSIONS, CppParser
from mcp_forge.discovery.codebase.csharp import CSharpParser
from mcp_forge.discovery.codebase.dart import DartParser
from mcp_forge.discovery.codebase.elixir import ElixirParser
from mcp_forge.discovery.codebase.fortran import FortranParser
from mcp_forge.discovery.codebase.go import GoParser
from mcp_forge.discovery.codebase.groovy import GroovyParser
from mcp_forge.discovery.codebase.java import JavaParser
from mcp_forge.discovery.codebase.js import JSParser
from mcp_forge.discovery.codebase.julia import JuliaParser
from mcp_forge.discovery.codebase.kotlin import KotlinParser
from mcp_forge.discovery.codebase.lua import LuaParser
from mcp_forge.discovery.codebase.php import PhpParser
from mcp_forge.discovery.codebase.powershell import PowerShellParser
from mcp_forge.discovery.codebase.python import PythonParser
from mcp_forge.discovery.codebase.r_lang import RParser
from mcp_forge.discovery.codebase.ruby import RubyParser
from mcp_forge.discovery.codebase.rust import RustParser
from mcp_forge.discovery.codebase.scala import ScalaParser
from mcp_forge.discovery.codebase.swift import SwiftParser
from mcp_forge.discovery.codebase.typescript import TypeScriptParser
from mcp_forge.models import DiscoveredTool, DiscoveryResult, ForgeConfig, SourceType

console = EngineConsole()  # requête des URL masquée (mcp_forge/console.py)

_IGNORE_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "env", "node_modules",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
}
_IGNORE_FILE_PREFIXES = ("test_", "conftest", "setup", "migrations")

_LANGUAGE_EXTENSIONS: dict[str, list[str]] = {
    "python":     [".py"],
    "lua":        [".lua"],
    "javascript": [".js", ".mjs"],
    "typescript": [".ts", ".tsx", ".d.ts"],
    # C++ : tous les fichiers détectés, mais le parser priorise les headers
    "cpp":        [".h", ".hpp", ".hxx", ".hh", ".cpp", ".cc", ".cxx", ".c"],
    "java":       [".java"],
    "go":         [".go"],
    "csharp":     [".cs"],
    "rust":       [".rs"],
    "php":        [".php"],
    "ruby":       [".rb"],
    "kotlin":     [".kt", ".kts"],
    "swift":      [".swift"],
    "cobol":      [".cbl", ".cob", ".cobol", ".cpy"],
    "scala":      [".scala"],
    "dart":       [".dart"],
    "elixir":     [".ex", ".exs"],
    "r":          [".R", ".r"],
    "fortran":    [".f", ".for", ".f77", ".ftn", ".f90", ".f95", ".f03", ".f08", ".f18"],
    "bash":       [".sh", ".bash"],
    "powershell": [".ps1", ".psm1"],
    "groovy":     [".groovy", ".gradle"],
    "julia":      [".jl"],
}

# Extension (en minuscules) → langage. Les extensions sont comparées sans tenir compte de la
# casse sur tous les systèmes (lot C, 2026-11-17) : sous Linux et macOS, `rglob("*.f90")`
# ignorait `.F90`, `.CBL`, `.CPY`… que Windows trouvait.
_EXT_TO_LANGUAGE: dict[str, str] = {}
for _lang, _exts in _LANGUAGE_EXTENSIONS.items():
    for _ext in _exts:
        _EXT_TO_LANGUAGE.setdefault(_ext.lower(), _lang)


def _suffix(name: str) -> str:
    return os.path.splitext(name)[1].lower()


def walk_codebase(root: Path) -> dict[str, list[Path]]:
    """Fichiers de chaque langage sous `root`, en un seul parcours (lot C, recommandation 10 :
    avant, un `rglob` par extension, une quarantaine de parcours, dossiers ignorés compris).

    Dossiers de _IGNORE_DIRS élagués ; extensions sans tenir compte de la casse ; ordre
    déterministe sur tous les systèmes (parties du chemin relatif, sensibles à la casse)."""
    found: dict[str, list[Path]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _IGNORE_DIRS)
        for name in filenames:
            language = _EXT_TO_LANGUAGE.get(_suffix(name))
            if language:
                found.setdefault(language, []).append(Path(dirpath) / name)
    for files in found.values():
        files.sort(key=lambda f: f.relative_to(root).parts)
    return found


_PARSERS = {
    "python":     PythonParser,
    "lua":        LuaParser,
    "javascript": JSParser,
    "typescript": TypeScriptParser,
    "cpp":        CppParser,
    "java":       JavaParser,
    "go":         GoParser,
    "csharp":     CSharpParser,
    "rust":       RustParser,
    "php":        PhpParser,
    "ruby":       RubyParser,
    "kotlin":     KotlinParser,
    "swift":      SwiftParser,
    "cobol":      CobolParser,
    "scala":      ScalaParser,
    "dart":       DartParser,
    "elixir":     ElixirParser,
    "r":          RParser,
    "fortran":    FortranParser,
    "bash":       BashParser,
    "powershell": PowerShellParser,
    "groovy":     GroovyParser,
    "julia":      JuliaParser,
}


def coverage_summary(generated: int, exclusions: dict) -> dict:
    """Chiffres de couverture transmis à l'évaluateur : il juge alors la
    qualité des tools vus au lieu d'en estimer le nombre depuis un extrait
    (mesuré : la couverture d'une vraie API Java (~2000 fichiers) variait de 7,5 à 9,5 d'un passage à
    l'autre). Les fichiers ignorés ne sont pas des opérations."""
    operations = {k: v for k, v in exclusions.items() if "not counted as operations" not in k}
    return {"discovered": generated + sum(operations.values()), "generated": generated, "excluded": exclusions}


def _drop_call_stubs_shadowed_by_subprograms(tools: list[DiscoveredTool]) -> list[DiscoveredTool]:
    """Supprime les stubs CALL externes (`metadata["type"] == "call"`,
    jamais exécutables) quand le programme appelé est AUSSI présent dans
    le même codebase comme sous-programme isolé réellement exécutable
    (`metadata["type"] == "subprogram"`).

    Trouvé en bouclant sur un vrai codebase COBOL (aws-mainframe-
    modernization-carddemo) : `CobolParser.extract()` traite chaque
    fichier isolément et ne peut pas savoir qu'un `CALL 'CSUTLDTC'` dans
    un fichier A référence un sous-programme isolé défini dans un fichier
    B du MÊME codebase — seule l'orchestration globale (ici) voit les
    deux à la fois. Sans ce post-traitement, le programme externe
    apparaît deux fois sous deux tools différents : un stub statique
    toujours en erreur (le CALL) et le vrai outil exécutable (le
    sous-programme) — source de confusion pour un agent (lequel
    utiliser ?) et signalé comme un vrai bug par l'évaluateur qualité.
    """
    subprogram_targets = {
        t.metadata.get("function", "").upper()
        for t in tools
        if t.metadata.get("type") == "subprogram"
    }
    return [
        t for t in tools
        if not (t.metadata.get("type") == "call" and t.metadata.get("function", "").upper() in subprogram_targets)
    ]


class CodebaseDiscovery:
    def __init__(self, config: ForgeConfig):
        self.config = config
        self.root = Path(config.source).resolve()
        self._files: dict[str, list[Path]] | None = None

    @property
    def files_by_language(self) -> dict[str, list[Path]]:
        """Résultat du parcours unique, gardé pour la détection et la collecte."""
        if self._files is None:
            self._files = walk_codebase(self.root)
        return self._files

    def discover(self) -> DiscoveryResult:
        if not self.root.is_dir():
            raise ValueError(f"Folder not found: {self.root}")

        language = self._detect_language()
        console.print(f"[bold]>> Analyzing the codebase ({language})...[/bold]")

        parser = _PARSERS[language]()
        extensions = _LANGUAGE_EXTENSIONS[language]

        console.print("[dim]  Collecting the files...[/dim]")
        files = self._collect_files(extensions)
        console.print(f"[dim]  {len(files)} {language} file(s) found[/dim]")

        tools: list[DiscoveredTool] = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("[dim]{task.fields[current_file]}[/dim]"),
            console=console,
        ) as progress:
            task = progress.add_task(
                "  Analyzing the files",
                total=len(files),
                current_file="",
            )
            for f in files:
                progress.update(task, current_file=f.name)
                tools += parser.extract(f, self.root)
                progress.advance(task)

        exclusions = dict(getattr(parser, "exclusions", {}) or {})
        if language == "cobol":
            before = len(tools)
            tools = _drop_call_stubs_shadowed_by_subprograms(tools)
            if before > len(tools):
                exclusions["CALL stubs replaced by the matching subprogram"] = before - len(tools)

        # Déduplication globale : si deux outils ont le même nom, ajoute un suffixe numérique
        seen_global: dict[str, int] = {}
        deduped: list[DiscoveredTool] = []
        for tool in tools:
            if tool.name not in seen_global:
                seen_global[tool.name] = 0
                deduped.append(tool)
            else:
                seen_global[tool.name] += 1
                tool.name = f"{tool.name}_{seen_global[tool.name]}"
                deduped.append(tool)
        tools = deduped

        console.print(f"[green][OK] {len(tools)} MCP tool(s) extracted[/green]")

        # Tous les langages du dépôt (un seul est généré : le dominant)
        languages = {lang: len(files) for lang, files in sorted(self.files_by_language.items())}
        others = {lang: n for lang, n in languages.items() if lang != language}
        if others:
            console.print("[dim]  Other languages present (not generated): "
                          + ", ".join(f"{lang} ({n})" for lang, n in others.items()) + "[/dim]")

        title = self.root.name
        return DiscoveryResult(
            source_type=SourceType.CODEBASE,
            source_path=str(self.root),
            title=title,
            description=f"Public functions extracted from {title} ({language})",
            tools=tools,
            metadata={"language": language, "languages": languages,
                      "coverage": coverage_summary(len(tools), exclusions)},
        )

    def _detect_language(self) -> str:
        """
        Détecte le langage dominant en pondérant chaque fichier par sa proximité à la racine.

        Un fichier à la racine vaut 1.0, à 1 niveau de profondeur 0.5, à 2 niveaux 0.33, etc.
        Cela évite qu'un dossier de tests avec 1000 fichiers Python prenne le dessus sur
        10 fichiers C++ au cœur du projet. Les dossiers ignorés (node_modules, .git, build…)
        ne comptent plus (lot C).
        """
        console.print("[dim]  Detecting the language...[/dim]")
        scores: dict[str, float] = dict.fromkeys(_LANGUAGE_EXTENSIONS, 0.0)
        for lang, files in self.files_by_language.items():
            for f in files:
                depth = len(f.relative_to(self.root).parts) - 1  # 0 = à la racine du projet
                scores[lang] += 1.0 / (depth + 1)

        for lang, score in scores.items():
            if score:
                console.print(f"[dim]    {lang}: {score:.1f} (weighted score)[/dim]")
        dominant = max(scores, key=lambda k: scores[k])
        return dominant if scores[dominant] > 0 else "python"

    def _files_with(self, extensions: list[str]) -> list[Path]:
        """Fichiers du parcours dont l'extension est dans `extensions` (sans tenir compte de la
        casse), groupés dans l'ordre de `extensions` comme l'ancienne boucle de `rglob`."""
        rank: dict[str, int] = {}
        for i, ext in enumerate(extensions):
            rank.setdefault(ext.lower(), i)
        languages = {_EXT_TO_LANGUAGE[e] for e in rank if e in _EXT_TO_LANGUAGE}
        files = [f for lang in languages for f in self.files_by_language.get(lang, [])
                 if _suffix(f.name) in rank]
        return sorted(files, key=lambda f: (rank[_suffix(f.name)], f.relative_to(self.root).parts))

    def _collect_files(self, extensions: list[str]) -> list[Path]:
        # Pour C++ : si des headers existent, on ne prend que les headers
        # (évite le bruit des implémentations)
        if any(ext.lower() in HEADER_EXTENSIONS for ext in extensions):
            header_exts = [e for e in extensions if e.lower() in HEADER_EXTENSIONS]
            source_exts = [e for e in extensions if e.lower() not in HEADER_EXTENSIONS]
            header_files = self._files_with(header_exts)
            if header_files:
                console.print(
                    f"[dim]  >> {len(header_files)} header(s) found, "
                    f"sources skipped (public API)[/dim]"
                )
                return header_files
            # Pas de headers : fallback sur les sources
            extensions = source_exts

        return [f for f in self._files_with(extensions) if not f.stem.startswith(_IGNORE_FILE_PREFIXES)]

    def _glob_extensions(self, extensions: list[str]) -> list[Path]:
        return self._files_with(extensions)
