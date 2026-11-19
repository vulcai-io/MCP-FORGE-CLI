"""
Regression 2026-10-01, found in a real evaluation report (batch of 27 sources): a BLOCKING bug,
`utils.is_prime(...)` raised `UndefVarError: utils not defined` in Julia.

Root cause: `JuliaParser.extract()` did `module_name = _detect_module(cleaned) or path.stem`, then
reused that SAME value both as the tool name prefix (cosmetic, fine) and as the `"module"`
metadata used by the generator to qualify the call (`Module.func(...)`). But
`include("utils.jl")` (used by the generated template) runs the file in the current scope WITHOUT
creating an implicit module named after the file, unlike the `path.stem` fallback. A Julia file
without an explicit `module X ... end` block therefore got a false module qualifier.
"""
from __future__ import annotations

from pathlib import Path

from mcp_forge.discovery.codebase.julia import JuliaParser

FLAT_FUNCTIONS = """\
function is_prime(n::Int)::Bool
    return n > 1
end
"""

WITH_MODULE = """\
module Utils
function is_prime(n::Int)::Bool
    return n > 1
end
end
"""


def test_flat_file_without_module_block_has_no_module_metadata(tmp_path: Path) -> None:
    f = tmp_path / "utils.jl"
    f.write_text(FLAT_FUNCTIONS, encoding="utf-8")

    tools = JuliaParser().extract(f, tmp_path)

    assert len(tools) == 1
    assert tools[0].metadata["module"] == ""
    # The tool name prefix may still fall back on the file name.
    assert tools[0].name == "utils_is_prime"


def test_real_module_block_is_still_captured(tmp_path: Path) -> None:
    f = tmp_path / "utils.jl"
    f.write_text(WITH_MODULE, encoding="utf-8")

    tools = JuliaParser().extract(f, tmp_path)

    assert len(tools) == 1
    assert tools[0].metadata["module"] == "Utils"
