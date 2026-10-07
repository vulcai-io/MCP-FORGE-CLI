"""
Smoke test d'un serveur MCP généré par mcp-forge.

Vérifie :
  1. Syntaxe Python valide  (py_compile)
  2. Import sans erreur     (subprocess isolé, chemin via env var — pas d'injection)
  3. Objet `mcp` présent    (FastMCP instance)
  4. Tools enregistrés      (au moins 1 @mcp.tool détecté)
  5. Cohérence VERSION      (count tools == tools_count si VERSION présent)
  6. requirements.txt présent

Usage programmatique :
    from mcp_forge.validation.smoke_test import run_smoke_test
    result = run_smoke_test("output/my_server")
    print(result.summary())
"""
from __future__ import annotations

import os
import py_compile
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Résultat
# ---------------------------------------------------------------------------

@dataclass
class SmokeTestResult:
    server_dir: str
    checks: list[tuple[str, bool, str]] = field(default_factory=list)  # (label, ok, detail)
    tools_found: int = 0
    tools_expected: int | None = None

    def add(self, label: str, ok: bool, detail: str = "") -> None:
        self.checks.append((label, ok, detail))

    @property
    def success(self) -> bool:
        return all(ok for _, ok, _ in self.checks)

    @property
    def errors(self) -> list[str]:
        return [f"{label}: {detail}" for label, ok, detail in self.checks if not ok and detail]

    def summary(self) -> str:
        """Résumé ASCII (compatible tous terminaux, CI/CD)."""
        lines = []
        for label, ok, detail in self.checks:
            icon = "[OK]  " if ok else "[FAIL]"
            suffix = f" -- {detail}" if detail else ""
            lines.append(f"  {icon} {label}{suffix}")
        return "\n".join(lines)


# Script Python exécuté dans le subprocess isolé.
# Le chemin du serveur est transmis via la variable d'environnement _MCP_SMOKE_PATH
# pour éviter toute injection (guillemets, backslashes, espaces dans le path).
_IMPORT_SCRIPT = (
    "import importlib.util, sys, os; "
    "path = os.environ['_MCP_SMOKE_PATH']; "
    "spec = importlib.util.spec_from_file_location('server', path); "
    "mod = importlib.util.module_from_spec(spec); "
    "spec.loader.exec_module(mod); "
    "assert hasattr(mod, 'mcp'), 'objet mcp absent'; "
    "print('ok')"
)


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------

def run_smoke_test(server_dir: str | Path) -> SmokeTestResult:
    """
    Exécute tous les checks sur un dossier de serveur MCP généré.
    Retourne un SmokeTestResult avec le détail de chaque vérification.
    """
    server_dir = Path(server_dir)
    result = SmokeTestResult(server_dir=str(server_dir))

    server_path = server_dir / "server.py"

    # ------------------------------------------------------------------
    # 0. server.py présent
    # ------------------------------------------------------------------
    if not server_path.exists():
        result.add("server.py present", False, f"not found in {server_dir}")
        return result
    result.add("server.py present", True)

    # ------------------------------------------------------------------
    # 1. Syntaxe Python valide
    # ------------------------------------------------------------------
    try:
        py_compile.compile(str(server_path), doraise=True)
        result.add("Python syntax", True)
    except py_compile.PyCompileError as e:
        result.add("Python syntax", False, str(e))
        return result  # import impossible si syntaxe invalide

    # ------------------------------------------------------------------
    # 2. Import sans erreur (subprocess isolé — chemin via env var)
    # ------------------------------------------------------------------
    env = {**os.environ, "_MCP_SMOKE_PATH": str(server_path)}
    proc = subprocess.run(
        [sys.executable, "-W", "ignore", "-c", _IMPORT_SCRIPT],
        capture_output=True, text=True, timeout=30,
        env=env,
    )
    if proc.returncode != 0:
        err_lines = (proc.stderr or "").strip().splitlines()
        detail = err_lines[-1] if err_lines else "unknown error"
        result.add("Python import", False, detail)
        result.add("mcp object", False, "not checked (import failed)")
        return result

    result.add("Python import", True)
    result.add("mcp object", True)

    # ------------------------------------------------------------------
    # 3. Nombre de tools (regex sur le source — sans dépendance FastMCP)
    # ------------------------------------------------------------------
    source = server_path.read_text(encoding="utf-8")
    # Compte uniquement les occurrences hors commentaires et chaînes de caractères
    tools_found = len(re.findall(r"^@mcp\.tool\b", source, re.MULTILINE))
    result.tools_found = tools_found

    if tools_found == 0:
        result.add("Tools registered", False, "no @mcp.tool found in server.py")
    else:
        result.add("Tools registered", True, f"{tools_found} tool(s) detected")

    # ------------------------------------------------------------------
    # 4. Cohérence avec fichier VERSION (si présent)
    # ------------------------------------------------------------------
    version_path = server_dir / "VERSION"
    if version_path.exists():
        try:
            version_data = _parse_version_file(version_path)
            expected = version_data.get("tools_count")
            if expected is not None:
                result.tools_expected = int(expected)
                if tools_found == result.tools_expected:
                    result.add("VERSION coherence", True,
                               f"tools_count={expected} matches")
                else:
                    result.add("VERSION coherence", False,
                               f"VERSION says {expected} tools, found {tools_found}")
        except Exception as e:
            result.add("VERSION coherence", False, f"cannot read VERSION: {e}")

    # ------------------------------------------------------------------
    # 5. requirements.txt présent
    # ------------------------------------------------------------------
    req_path = server_dir / "requirements.txt"
    if req_path.exists():
        result.add("requirements.txt present", True)
    else:
        result.add("requirements.txt present", False, "file missing")

    return result


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse_version_file(path: Path) -> dict:
    """Parse le fichier VERSION (YAML simple clé: valeur)."""
    data: dict = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            data[k.strip()] = v.strip()
    return data
