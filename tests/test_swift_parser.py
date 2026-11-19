"""
Regression 2026-10-05: `SwiftParser` only extracted `public`/`open` functions, a deliberate choice
(same convention as the Java parser). But unlike a typical Java library, a single-file Swift module
(script, utility) usually has NO explicit visibility modifier: Swift uses `internal` by default,
without a keyword. Result: a test source with 4 functions without a modifier gave 0 tools, a total
failure rather than an imperfect generation.

Widened to accept any visibility EXCEPT `private`/`fileprivate` (these stay real, intended
exclusions: a private function is rightly not exposable).
"""
from __future__ import annotations

from pathlib import Path

from mcp_forge.discovery.codebase.swift import SwiftParser
from mcp_forge.models import ParameterType


def _extract(tmp_path: Path, source: str):
    f = tmp_path / "Utils.swift"
    f.write_text(source, encoding="utf-8")
    return SwiftParser().extract(f, tmp_path)


def test_function_without_visibility_modifier_is_extracted(tmp_path: Path) -> None:
    """The case of the real test fixture: no modifier at all."""
    tools = _extract(tmp_path, "func isPrime(_ n: Int) -> Bool {\n    return n > 1\n}\n")
    assert len(tools) == 1
    assert tools[0].metadata["function"] == "isPrime"


def test_public_function_still_extracted(tmp_path: Path) -> None:
    tools = _extract(tmp_path, "public func isPrime(_ n: Int) -> Bool {\n    return n > 1\n}\n")
    assert len(tools) == 1


def test_private_function_still_excluded(tmp_path: Path) -> None:
    tools = _extract(tmp_path, "private func helper(_ n: Int) -> Bool {\n    return n > 1\n}\n")
    assert len(tools) == 0


def test_fileprivate_function_still_excluded(tmp_path: Path) -> None:
    tools = _extract(tmp_path, "fileprivate func helper(_ n: Int) -> Bool {\n    return n > 1\n}\n")
    assert len(tools) == 0


def test_array_bracket_syntax_detected_as_array_with_items_type(tmp_path: Path) -> None:
    """A separate regression found in the same pass: `[Double]` (Swift array syntax, not the generic
    `Array<Double>`) fell back on the STRING default because the type lookup did not recognise
    the brackets."""
    tools = _extract(tmp_path, "func sumList(_ numbers: [Double]) -> Double {\n    return 0\n}\n")
    assert tools[0].parameters[0].type == ParameterType.ARRAY
    assert tools[0].parameters[0].items_type == ParameterType.NUMBER
