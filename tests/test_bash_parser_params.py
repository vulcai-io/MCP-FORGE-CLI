"""
Regression 2026-10-01, found in a real evaluation report: the `reverse_string`/`sum_list` tools
generated from a Bash script had NO parameter, which made them unusable.

Root cause: `_extract_params_from_body()` (mcp_forge/discovery/codebase/bash.py) only detected the
`local name=$1` convention. A function that uses `$1` directly without a local alias
(`echo "$1" | rev`), or `"$@"` for a variadic list (`for n in "$@"`), never had any parameter
detected.
"""
from __future__ import annotations

from pathlib import Path

from mcp_forge.discovery.codebase.bash import BashParser
from mcp_forge.models import ParameterType


def _extract(tmp_path: Path, script: str):
    f = tmp_path / "utils.sh"
    f.write_text("#!/usr/bin/env bash\n" + script, encoding="utf-8")
    return BashParser().extract(f, tmp_path)


def test_direct_positional_reference_without_local_alias(tmp_path: Path) -> None:
    tools = _extract(tmp_path, 'reverse_string() {\n    echo "$1" | rev\n}\n')
    assert len(tools) == 1
    assert [p.name for p in tools[0].parameters] == ["arg1"]


def test_variadic_at_sign_becomes_array_param(tmp_path: Path) -> None:
    tools = _extract(
        tmp_path,
        'sum_list() {\n    local total=0\n    for n in "$@"; do\n        total=$((total + n))\n    done\n    echo "$total"\n}\n',
    )
    assert len(tools) == 1
    assert len(tools[0].parameters) == 1
    assert tools[0].parameters[0].name == "args"
    assert tools[0].parameters[0].type == ParameterType.ARRAY


def test_named_local_alias_still_preferred_over_positional_name(tmp_path: Path) -> None:
    tools = _extract(tmp_path, 'is_prime() {\n    local n=$1\n    echo "$n"\n}\n')
    assert [p.name for p in tools[0].parameters] == ["n"]


def test_multiple_positional_params_sorted_by_position(tmp_path: Path) -> None:
    tools = _extract(tmp_path, 'add() {\n    echo "$(( $2 + $1 ))"\n}\n')
    assert [p.name for p in tools[0].parameters] == ["arg1", "arg2"]
