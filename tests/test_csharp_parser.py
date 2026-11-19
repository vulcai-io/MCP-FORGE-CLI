"""
Regression 2026-10-05, found while checking generated C# support (`dotnet run`) on a real fixture.

Two separate bugs:

1. The regex that removes `[...]` attributes (e.g. `[FromBody] string s`) used `[^\\]]*` (zero or
   more) instead of `[^\\]]+` (one or more). An array type (`double[] numbers`) has EMPTY
   brackets: the regex matched them too and merged "double[] numbers" into "doublenumbers" (a
   single token), silently dropping the whole parameter.

2. The `print_suffix` of C# scripting was ")" without the final `;` that .NET top-level statements
   require (`CS1002: ; expected`). Unlike the other languages of this group, where the call alone
   (without a semicolon) is a valid expression.
"""
from __future__ import annotations

from pathlib import Path

from mcp_forge.discovery.codebase.csharp import CSharpParser
from mcp_forge.models import ParameterType


def test_array_parameter_not_swallowed_by_attribute_stripping_regex(tmp_path: Path) -> None:
    source = """
using System;
using System.Linq;

public static class Utils
{
    public static double SumList(double[] numbers)
    {
        return numbers.Sum();
    }
}
"""
    path = tmp_path / "Utils.cs"
    path.write_text(source, encoding="utf-8")
    tools = CSharpParser().extract(path, tmp_path)
    assert len(tools) == 1
    params = tools[0].parameters
    assert len(params) == 1
    assert params[0].name == "numbers"
    assert params[0].type == ParameterType.ARRAY
    assert params[0].items_type == ParameterType.NUMBER


def test_real_attribute_is_still_stripped(tmp_path: Path) -> None:
    source = """
public static class Utils
{
    public static string Greet([Optional] string name)
    {
        return "hi " + name;
    }
}
"""
    path = tmp_path / "Utils.cs"
    path.write_text(source, encoding="utf-8")
    tools = CSharpParser().extract(path, tmp_path)
    assert len(tools) == 1
    params = tools[0].parameters
    assert len(params) == 1
    assert params[0].name == "name"
    assert params[0].type == ParameterType.STRING
