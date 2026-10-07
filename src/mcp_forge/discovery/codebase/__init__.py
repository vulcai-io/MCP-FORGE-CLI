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

from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

from mcp_forge.models import DiscoveredTool, DiscoveryResult, ForgeConfig, SourceType
from mcp_forge.discovery.codebase.python import PythonParser
from mcp_forge.discovery.codebase.lua import LuaParser
from mcp_forge.discovery.codebase.js import JSParser
from mcp_forge.discovery.codebase.cpp import CppParser, HEADER_EXTENSIONS
from mcp_forge.discovery.codebase.java import JavaParser
from mcp_forge.discovery.codebase.go import GoParser
from mcp_forge.discovery.codebase.csharp import CSharpParser
from mcp_forge.discovery.codebase.typescript import TypeScriptParser
from mcp_forge.discovery.codebase.rust import RustParser
from mcp_forge.discovery.codebase.php import PhpParser
from mcp_forge.discovery.codebase.ruby import RubyParser
from mcp_forge.discovery.codebase.kotlin import KotlinParser
from mcp_forge.discovery.codebase.swift import SwiftParser
from mcp_forge.discovery.codebase.cobol import CobolParser
from mcp_forge.discovery.codebase.scala import ScalaParser
from mcp_forge.discovery.codebase.dart import DartParser
from mcp_forge.discovery.codebase.elixir import ElixirParser
from mcp_forge.discovery.codebase.r_lang import RParser
from mcp_forge.discovery.codebase.fortran import FortranParser
from mcp_forge.discovery.codebase.bash import BashParser
from mcp_forge.discovery.codebase.powershell import PowerShellParser
from mcp_forge.discovery.codebase.groovy import GroovyParser
from mcp_forge.discovery.codebase.julia import JuliaParser

console = Console()

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
    "cpp":        [".h", ".hpp", ".hxx", ".cpp", ".cc", ".cxx", ".c"],
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

    def discover(self) -> DiscoveryResult:
        if not self.root.is_dir():
            raise ValueError(f"Dossier introuvable : {self.root}")

        language = self._detect_language()
        console.print(f"[bold]>> Analyse du codebase ({language})...[/bold]")

        parser = _PARSERS[language]()
        extensions = _LANGUAGE_EXTENSIONS[language]

        console.print("[dim]  Collecte des fichiers...[/dim]")
        files = self._collect_files(extensions)
        console.print(f"[dim]  {len(files)} fichier(s) {language} trouvé(s)[/dim]")

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
                "  Analyse des fichiers",
                total=len(files),
                current_file="",
            )
            for f in files:
                progress.update(task, current_file=f.name)
                tools += parser.extract(f, self.root)
                progress.advance(task)

        if language == "cobol":
            tools = _drop_call_stubs_shadowed_by_subprograms(tools)

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

        console.print(f"[green][OK] {len(tools)} outil(s) MCP extrait(s)[/green]")

        title = self.root.name
        return DiscoveryResult(
            source_type=SourceType.CODEBASE,
            source_path=str(self.root),
            title=title,
            description=f"Fonctions publiques extraites de {title} ({language})",
            tools=tools,
            metadata={"language": language},
        )

    def _detect_language(self) -> str:
        """
        Détecte le langage dominant en pondérant chaque fichier par sa proximité à la racine.

        Un fichier à la racine vaut 1.0, à 1 niveau de profondeur 0.5, à 2 niveaux 0.33, etc.
        Cela évite qu'un dossier de tests avec 1000 fichiers Python prenne le dessus sur
        10 fichiers C++ au cœur du projet.
        """
        console.print("[dim]  Détection du langage...[/dim]")
        scores: dict[str, float] = dict.fromkeys(_LANGUAGE_EXTENSIONS, 0.0)
        root_depth = len(self.root.parts)

        for lang, exts in _LANGUAGE_EXTENSIONS.items():
            for ext in exts:
                for f in self.root.rglob(f"*{ext}"):
                    # Profondeur relative (0 = à la racine du projet)
                    depth = len(f.parts) - root_depth - 1
                    scores[lang] += 1.0 / (depth + 1)

        for lang, score in scores.items():
            if score:
                console.print(f"[dim]    {lang}: {score:.1f} (score pondéré)[/dim]")
        dominant = max(scores, key=lambda k: scores[k])
        return dominant if scores[dominant] > 0 else "python"

    def _collect_files(self, extensions: list[str]) -> list[Path]:
        files = []
        collected: set[Path] = set()

        # Pour C++ : si des headers existent, on ne prend que les headers
        # (évite le bruit des implémentations)
        if any(ext in HEADER_EXTENSIONS for ext in extensions):
            header_exts = [e for e in extensions if e in HEADER_EXTENSIONS]
            source_exts = [e for e in extensions if e not in HEADER_EXTENSIONS]
            header_files = self._glob_extensions(header_exts)
            if header_files:
                console.print(
                    f"[dim]  >> {len(header_files)} header(s) trouvé(s), "
                    f"sources ignorées (API publique)[/dim]"
                )
                return header_files
            # Pas de headers : fallback sur les sources
            extensions = source_exts

        for ext in extensions:
            for f in sorted(self.root.rglob(f"*{ext}")):
                if f in collected:
                    continue
                if any(part in _IGNORE_DIRS for part in f.parts):
                    continue
                if f.stem.startswith(_IGNORE_FILE_PREFIXES):
                    continue
                collected.add(f)
                files.append(f)
        return files

    def _glob_extensions(self, extensions: list[str]) -> list[Path]:
        files, collected = [], set()
        for ext in extensions:
            for f in sorted(self.root.rglob(f"*{ext}")):
                if f in collected:
                    continue
                if any(part in _IGNORE_DIRS for part in f.parts):
                    continue
                collected.add(f)
                files.append(f)
        return files
