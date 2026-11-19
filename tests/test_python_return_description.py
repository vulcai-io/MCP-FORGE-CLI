"""
Regression 2026-10-04, a recurring "minor" bug in every Python evaluation report: the `Returns:`
docstring of the generated server always said a generic sentence without the type, which tells
an LLM calling the tool very little.

`PythonParser` ignored the return annotation (`-> bool`, `-> int`...) of the source function,
although it is available through `ast`: `_describe_return()` now reads it to fill
`DiscoveredTool.response_description`.
"""
from __future__ import annotations

from pathlib import Path

from mcp_forge.discovery.codebase.python import PythonParser


def _extract(tmp_path: Path, source: str):
    f = tmp_path / "utils.py"
    f.write_text(source, encoding="utf-8")
    return PythonParser().extract(f, tmp_path)


def test_bool_return_annotation_described(tmp_path: Path) -> None:
    tools = _extract(tmp_path, "def is_prime(n: int) -> bool:\n    return n > 1\n")
    assert "bool" in tools[0].response_description


def test_list_return_annotation_described(tmp_path: Path) -> None:
    tools = _extract(tmp_path, "def get_items() -> list[str]:\n    return []\n")
    assert "list" in tools[0].response_description


def test_no_annotation_leaves_description_empty_for_template_fallback(tmp_path: Path) -> None:
    """No annotation gives an empty string, so that the template uses its own generic fallback
    rather than inventing a false one."""
    tools = _extract(tmp_path, "def mystery(n):\n    return n\n")
    assert tools[0].response_description == ""
