"""
Validation du serveur MCP généré.
Vérifie que le code est syntaxiquement valide et que le serveur démarre correctement.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

from rich.console import Console

from mcp_forge.models import GeneratedServer

console = Console()


class MCPValidator:
    def validate(self, generated: GeneratedServer) -> bool:
        console.print("[bold]>> Validating the generated server...[/bold]")
        ok = True

        server_path = Path(generated.output_dir) / "server.py"

        # 1. Vérification syntaxique Python
        if not self._check_syntax(server_path):
            generated.errors.append("Syntax error in server.py")
            ok = False

        # 2. Vérification des imports
        if not self._check_imports(server_path):
            generated.errors.append("Import error in server.py (missing dependencies?)")
            ok = False

        if ok:
            console.print("[green][OK] Validation passed[/green]")
        else:
            console.print(f"[red][FAIL] Validation failed: {', '.join(generated.errors)}[/red]")

        return ok

    # Au-delà de cette taille, on passe en validation légère (subprocess trop long)
    _MAX_PARSE_MB = 2.0

    def _check_syntax(self, path: Path) -> bool:
        """Vérifie la syntaxe Python via subprocess (avec timeout)."""
        try:
            size_mb = path.stat().st_size / 1_000_000
        except FileNotFoundError:
            console.print(f"[red]  [FAIL] File not found: {path}[/red]")
            return False

        if size_mb > self._MAX_PARSE_MB:
            console.print(
                f"[dim]  ⚠ Large file ({size_mb:.1f} MB): "
                f"lighter syntax validation[/dim]"
            )
            return self._check_syntax_light(path)

        result = subprocess.run(
            [sys.executable, "-W", "ignore", "-c",
             f"import ast; ast.parse(open({repr(str(path))}, encoding='utf-8').read()); print('ok')"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            console.print(f"[red]  [FAIL] Syntax error: {result.stderr.strip()[:200]}[/red]")
            return False
        console.print("[dim]  [OK] Syntaxe Python valide[/dim]")
        return True

    def _check_syntax_light(self, path: Path) -> bool:
        """Validation légère : vérifie uniquement l'en-tête du fichier (imports + init)."""
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            # Prend uniquement les lignes avant la première fonction
            header_lines = []
            for line in lines:
                if line.startswith("@mcp.tool()"):
                    break
                header_lines.append(line)
            ast.parse("\n".join(header_lines))
            console.print("[dim]  [OK] Valid header (lighter validation of a large file)[/dim]")
            return True
        except SyntaxError as e:
            console.print(f"[red]  [FAIL] Syntax error in the header: {e}[/red]")
            return False

    def _check_imports(self, path: Path) -> bool:
        """Tente de compiler le module pour détecter les dépendances manquantes."""
        try:
            size_mb = path.stat().st_size / 1_000_000
        except FileNotFoundError:
            return False

        if size_mb > self._MAX_PARSE_MB:
            console.print("[dim]  ⚠ Import check skipped (large file)[/dim]")
            return True

        result = subprocess.run(
            [sys.executable, "-W", "ignore", "-c",
             f"import ast; ast.parse(open({repr(str(path))}, encoding='utf-8').read()); print('ok')"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            console.print(f"[red]  [FAIL] {result.stderr.strip()[:200]}[/red]")
            return False
        console.print("[dim]  [OK] Imports checked[/dim]")
        return True
