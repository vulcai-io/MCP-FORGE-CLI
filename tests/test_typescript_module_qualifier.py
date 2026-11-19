"""
Regression 2026-10-05, the same bug as for Julia: `TypeScriptParser` stored the file name (e.g.
"utils") as the `"module"` metadata, used by the generator to qualify the generated call
(`utils.isPrime(...)`). But an `export function isPrime() {}` function is called directly
(`isPrime(...)`) once the source file is run: `utils` is never defined, which gives a guaranteed
`ReferenceError: utils is not defined` with Node/tsx. Confirmed by running the generated server
against a real `npx tsx`.

The tool NAME prefix (cosmetic, e.g. `utils_isprime`) may stay based on the file name; only the
`"module"` metadata used for the call must stay empty.
"""
from __future__ import annotations

from pathlib import Path

from mcp_forge.discovery.codebase.typescript import TypeScriptParser


def test_file_stem_is_not_used_as_a_module_qualifier(tmp_path: Path) -> None:
    f = tmp_path / "utils.ts"
    f.write_text("export function isPrime(n: number): boolean {\n  return n > 1;\n}\n", encoding="utf-8")

    tools = TypeScriptParser().extract(f, tmp_path)

    assert len(tools) == 1
    assert tools[0].metadata["module"] == ""
    # The cosmetic tool name prefix keeps the file name.
    assert tools[0].name == "utils_isprime"
