"""
Test fonctionnel d'un serveur MCP généré par mcp-forge.

Phase 1 — Protocole MCP :
  1. Serveur démarre sans erreur
  2. Handshake MCP (initialize) réussi
  3. tools/list retourne au moins 1 tool
  4. Cohérence tools_count avec VERSION (si présent)
  5. Cohérence avec les @mcp.tool du source

Phase 2 — Appel des tools :
  6. Pour chaque tool en lecture : call_tool avec args de test générés
     depuis le schéma JSON (required params uniquement)
  7. Résultat accepté si pas d'exception MCP (isError=True = warning,
     car c'est une erreur de dépendance externe, pas du code généré)
  8. Tools d'écriture (create_, delete_...) skippés par défaut

Usage programmatique :
    from mcp_forge.validation.functional_test import run_functional_test
    result = run_functional_test("output/my_server", call_tools=True)
    print(result.summary())

Usage CLI :
    mcp-forge functional-test output/my_server
    mcp-forge functional-test output/my_server --no-skip-writes
"""
from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_CHECK_SERVER_START = "Server start"
_CHECK_MCP_INIT    = "MCP initialize"
_CHECK_TOOLS_LIST  = "tools/list"

# Préfixes indiquant un tool d'écriture (skippés par défaut en phase 2)
_WRITE_PREFIXES = (
    "create_", "delete_", "update_", "add_", "remove_",
    "set_", "put_", "post_", "patch_", "insert_", "edit_",
    "register_", "submit_", "send_", "push_", "publish_",
)

# Heuristiques de valeurs de test pour les paramètres string
_STRING_HEURISTICS: list[tuple[tuple[str, ...], str]] = [
    (("code", "country", "continent", "lang"), "EU"),
    (("id", "key", "uuid"),                   "1"),
    (("url", "uri", "link", "href"),           "https://example.com"),
    (("email", "mail"),                        "test@example.com"),
    (("path", "file"),                         "/tmp/test"),
    (("limit", "size", "count", "max"),        "10"),  # parfois string dans certaines APIs
    (("query", "q", "search", "keyword"),      "test"),
]

# Heuristiques pour les paramètres integer
_INT_HEURISTICS: list[tuple[tuple[str, ...], int]] = [
    (("limit", "size", "count", "max"), 10),
    (("page", "offset", "skip"),         0),
]


# ---------------------------------------------------------------------------
# Résultats
# ---------------------------------------------------------------------------

@dataclass
class ToolCallResult:
    name: str
    status: str          # "ok" | "warn" | "fail" | "skip"
    detail: str = ""
    args_used: dict = field(default_factory=dict)


@dataclass
class FunctionalTestResult:
    server_dir: str
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    tools_listed: list[str] = field(default_factory=list)
    tool_calls: list[ToolCallResult] = field(default_factory=list)
    tools_expected: int | None = None

    def add(self, label: str, ok: bool, detail: str = "") -> None:
        self.checks.append((label, ok, detail))

    @property
    def success(self) -> bool:
        # Les warnings (isError côté outil) ne font pas échouer le test
        return (
            all(ok for _, ok, _ in self.checks)
            and all(c.status != "fail" for c in self.tool_calls)
        )

    @property
    def errors(self) -> list[str]:
        errs = [f"{label}: {detail}" for label, ok, detail in self.checks if not ok and detail]
        errs += [f"call {c.name}: {c.detail}" for c in self.tool_calls if c.status == "fail"]
        return errs

    def summary(self) -> str:
        """Résumé ASCII (compatible tous terminaux, CI/CD)."""
        lines = ["Phase 1 -- Protocole MCP :"]
        for label, ok, detail in self.checks:
            icon = "[OK]  " if ok else "[FAIL]"
            suffix = f" -- {detail}" if detail else ""
            lines.append(f"  {icon} {label}{suffix}")

        if self.tool_calls:
            lines.append("\nPhase 2 -- Appel des tools :")
            icons = {"ok": "[OK]  ", "warn": "[WARN]", "fail": "[FAIL]", "skip": "[SKIP]"}
            for tc in self.tool_calls:
                icon = icons.get(tc.status, "[?]   ")
                args_str = f"  args={tc.args_used}" if tc.args_used else ""
                suffix = f" -- {tc.detail}" if tc.detail else ""
                lines.append(f"  {icon} {tc.name}{args_str}{suffix}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Point d'entrée synchrone
# ---------------------------------------------------------------------------

def run_functional_test(
    server_dir: str | Path,
    timeout: float = 15.0,
    call_tools: bool = True,
    skip_writes: bool = True,
) -> FunctionalTestResult:
    """
    Lance le test fonctionnel sur un serveur MCP généré.

    Args:
        timeout:     Délai max (secondes) par étape de communication.
        call_tools:  Si True, appelle chaque tool avec des args de test (phase 2).
        skip_writes: Si True, skippe les tools dont le nom suggère une écriture.
    """
    server_dir = Path(server_dir)
    result = FunctionalTestResult(server_dir=str(server_dir))

    server_path = server_dir / "server.py"
    if not server_path.exists():
        result.add(_CHECK_SERVER_START, False, f"server.py not found in {server_dir}")
        return result

    # tools_count depuis VERSION
    version_path = server_dir / "VERSION"
    if version_path.exists():
        for line in version_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("tools_count:"):
                try:
                    result.tools_expected = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass

    try:
        asyncio.run(_Runner(timeout, call_tools, skip_writes).run(server_path, result))
    except KeyboardInterrupt:
        result.add("Test interrompu", False, "KeyboardInterrupt")

    return result


# ---------------------------------------------------------------------------
# Runner — regroupe timeout + options pour éviter la cascade de paramètres
# ---------------------------------------------------------------------------

class _Runner:
    """Porte le timeout et les options comme attributs pour éviter de les
    passer en cascade à chaque coroutine (règle SonarLint S7483)."""

    def __init__(self, timeout: float, call_tools: bool, skip_writes: bool) -> None:
        self._t = timeout
        self._call_tools = call_tools
        self._skip_writes = skip_writes

    async def run(self, server_path: Path, result: FunctionalTestResult) -> None:
        from mcp.client.stdio import stdio_client, StdioServerParameters
        from mcp import ClientSession

        server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(server_path)],
        )

        # --- Démarrage ---
        try:
            cm = stdio_client(server_params)
            async with asyncio.timeout(self._t):
                read, write = await cm.__aenter__()
            result.add(_CHECK_SERVER_START, True)
        except TimeoutError:
            result.add(_CHECK_SERVER_START, False, f"timeout after {self._t:.0f}s")
            return
        except Exception as e:
            result.add(_CHECK_SERVER_START, False, str(e))
            return

        try:
            await self._run_session(ClientSession(read, write), result)
        finally:
            await cm.__aexit__(None, None, None)

    async def _run_session(self, session_cm, result: FunctionalTestResult) -> None:
        # --- Initialize ---
        try:
            async with asyncio.timeout(self._t):
                session = await session_cm.__aenter__()
                init_result = await session.initialize()
            server_name = getattr(getattr(init_result, "serverInfo", None), "name", "?")
            result.add(_CHECK_MCP_INIT, True, f"server: {server_name}")
        except TimeoutError:
            result.add(_CHECK_MCP_INIT, False, f"timeout after {self._t:.0f}s")
            return
        except Exception as e:
            result.add(_CHECK_MCP_INIT, False, str(e))
            return

        try:
            await self._run_tools(session, result)
        finally:
            await session_cm.__aexit__(None, None, None)

    async def _run_tools(self, session, result: FunctionalTestResult) -> None:
        # --- tools/list ---
        try:
            async with asyncio.timeout(self._t):
                tools_result = await session.list_tools()
            tools = tools_result.tools or []
            result.tools_listed = [t.name for t in tools]
            if not tools:
                result.add(_CHECK_TOOLS_LIST, False, "server returned 0 tools")
                return
            result.add(_CHECK_TOOLS_LIST, True, f"{len(tools)} tool(s) returned")
        except TimeoutError:
            result.add(_CHECK_TOOLS_LIST, False, f"timeout after {self._t:.0f}s")
            return
        except Exception as e:
            result.add(_CHECK_TOOLS_LIST, False, str(e))
            return

        # --- Cohérence VERSION ---
        if result.tools_expected is not None:
            n = len(result.tools_listed)
            ok = n == result.tools_expected
            msg = "match" if ok else f"!= expected {result.tools_expected}"
            result.add("VERSION coherence", ok, f"{n} tools {msg}")

        # --- Cohérence @mcp.tool source ---
        source = Path(result.server_dir, "server.py").read_text(encoding="utf-8")
        decorators_count = len(re.findall(r"^@mcp\.tool\b", source, re.MULTILINE))
        if decorators_count > 0:
            n = len(result.tools_listed)
            ok = n == decorators_count
            msg = f"{decorators_count} @mcp.tool match" if ok else f"source={decorators_count}, server={n}"
            result.add("Decorator coherence", ok, msg)

        # --- Phase 2 ---
        if self._call_tools:
            await self._call_all_tools(session, tools, result)

    async def _call_all_tools(self, session, tools, result: FunctionalTestResult) -> None:
        """Phase 2 : appelle chaque tool avec des arguments de test générés depuis son schéma."""
        for tool in tools:
            name = tool.name
            schema = tool.inputSchema or {}

            if self._skip_writes and _is_write_tool(name):
                result.tool_calls.append(ToolCallResult(
                    name=name, status="skip",
                    detail="write operation (use --no-skip-writes to force)",
                ))
                continue

            args = _generate_test_args(schema)

            try:
                async with asyncio.timeout(self._t):
                    call_result = await session.call_tool(name, args)

                if call_result.isError:
                    detail = _extract_error_text(call_result.content)
                    result.tool_calls.append(ToolCallResult(
                        name=name, status="warn",
                        detail=f"tool error (external dependency?): {detail[:80]}",
                        args_used=args,
                    ))
                else:
                    result.tool_calls.append(ToolCallResult(name=name, status="ok", args_used=args))

            except TimeoutError:
                result.tool_calls.append(ToolCallResult(
                    name=name, status="fail",
                    detail=f"timeout after {self._t:.0f}s",
                    args_used=args,
                ))
            except Exception as e:
                result.tool_calls.append(ToolCallResult(
                    name=name, status="fail",
                    detail=str(e)[:120],
                    args_used=args,
                ))


# ---------------------------------------------------------------------------
# Génération des arguments de test
# ---------------------------------------------------------------------------

def _generate_test_args(schema: dict) -> dict:
    """
    Génère des arguments minimaux depuis un schéma JSON Schema.
    Seuls les paramètres requis sont renseignés.
    """
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    return {
        name: _test_value(name, prop)
        for name, prop in props.items()
        if name in required
    }


def _test_value(name: str, prop: dict) -> Any:
    """Génère une valeur de test depuis une propriété JSON Schema."""
    # anyOf : prend le premier type non-null
    if "anyOf" in prop:
        for variant in prop["anyOf"]:
            if variant.get("type") != "null":
                return _test_value(name, variant)
        return None

    ptype = prop.get("type", "string")

    if ptype == "string":
        return _string_test_value(name.lower())
    if ptype == "integer":
        return _integer_test_value(name.lower())
    if ptype == "number":
        return 1.0
    if ptype == "boolean":
        return False
    if ptype == "array":
        return []
    if ptype == "object":
        return {}
    return "test"


def _string_test_value(name: str) -> str:
    for keywords, value in _STRING_HEURISTICS:
        if any(k in name for k in keywords):
            return value
    return "test"


def _integer_test_value(name: str) -> int:
    for keywords, value in _INT_HEURISTICS:
        if any(k in name for k in keywords):
            return value
    return 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_write_tool(name: str) -> bool:
    """Retourne True si le nom du tool suggère une opération d'écriture."""
    return name.lower().startswith(_WRITE_PREFIXES)


def _extract_error_text(content: list) -> str:
    """Extrait le texte d'erreur depuis le contenu d'un CallToolResult."""
    for item in content or []:
        text = getattr(item, "text", None)
        if text:
            return text
    return "unknown error"
