"""
Regression 2026-10-01, found while testing the generated PowerShell server: `Get-SumList` (param
`[double[]]$Numbers`) had no parameter detected, which made it unusable.

Root cause: the type regex `\\[([^\\]]+)\\]\\s*\\$(\\w+)` stopped at the first `]` it met: for an
array type such as `double[]`, the `]` at the end of the type closed the regex too early, before
reaching the `]` that really ends the type annotation, so the whole parameter failed to match and
was silently dropped.
"""
from __future__ import annotations

from mcp_forge.discovery.codebase.powershell import _parse_single_ps_param
from mcp_forge.models import ParameterType


def test_array_type_param_is_detected() -> None:
    param = _parse_single_ps_param("[double[]]$Numbers")
    assert param is not None
    assert param.name == "numbers"
    assert param.type == ParameterType.ARRAY


def test_scalar_type_param_still_works() -> None:
    param = _parse_single_ps_param("[int]$N")
    assert param is not None
    assert param.name == "n"
    assert param.type == ParameterType.INTEGER


def test_string_array_type_param() -> None:
    param = _parse_single_ps_param("[string[]]$Items")
    assert param is not None
    assert param.type == ParameterType.ARRAY
