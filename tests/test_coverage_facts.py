"""
Step 3 (2026-10-13): coverage figures of the generator given to the evaluator. Measured: the
coverage of a real Java API (~2,000 files) varied from 7.5 to 9.5 from one run to the next, the
evaluator estimating the number of tools from an excerpt. The parsers now count what they leave
out, by reason.
"""
from __future__ import annotations

from pathlib import Path

from mcp_forge.discovery.codebase import CodebaseDiscovery, coverage_summary
from mcp_forge.discovery.codebase.cpp import CppParser
from mcp_forge.discovery.codebase.java import JavaParser
from mcp_forge.evaluate import coverage_context
from mcp_forge.models import ForgeConfig, ForgeMode, NameStyle, SourceType


def test_java_parser_counts_exclusions_by_reason(tmp_path: Path) -> None:
    (tmp_path / "Plugin.java").write_text("public interface Plugin { String getName(); }\n", encoding="utf-8")
    f = tmp_path / "Svc.java"
    f.write_text(
        "public abstract class Svc {\n"
        "    public abstract int a(int x);\n"
        "    public int b(int x) { return x; }\n"
        "    public static int c(Plugin p) { return 0; }\n"
        "    public static int d(int x) { return x; }\n"
        "}\n", encoding="utf-8")
    parser = JavaParser()
    tools = parser.extract(f, tmp_path)
    parser.extract(tmp_path / "Plugin.java", tmp_path)
    assert [t.metadata["function"] for t in tools] == ["d"]
    # `a`, and `getName`: interface method, implicitly public
    assert parser.exclusions["abstract or interface methods (no body to execute)"] == 2
    assert parser.exclusions["instance methods of types that cannot be instantiated with new X()"] == 1
    assert parser.exclusions["methods with a parameter type that cannot be built from a tool argument"] == 1


def test_cpp_parser_counts_class_methods_and_templates(tmp_path: Path) -> None:
    f = tmp_path / "lib.h"
    f.write_text(
        "template<typename T> T twice(T v) { return v + v; }\n"
        "class Box {\npublic:\n    int size() { return 1; }\n};\n"
        "int add(int a, int b) { return a + b; }\n", encoding="utf-8")
    parser = CppParser()
    assert [t.metadata["function"] for t in parser.extract(f, tmp_path)] == ["add"]
    assert sum(parser.exclusions.values()) == 2


def test_discovery_exposes_coverage_and_skipped_files_are_not_operations(tmp_path: Path) -> None:
    (tmp_path / "src" / "test" / "java").mkdir(parents=True)
    (tmp_path / "src" / "test" / "java" / "T.java").write_text("public class T { public static int t() { return 0; } }\n", encoding="utf-8")
    (tmp_path / "U.java").write_text("public class U { public static int u() { return 0; } }\n", encoding="utf-8")
    config = ForgeConfig(source=str(tmp_path), mode=ForgeMode.AUTO, output_dir="x",
                         source_type=SourceType.CODEBASE, name_style=NameStyle.SHORT)
    coverage = CodebaseDiscovery(config).discover().metadata["coverage"]
    assert coverage["generated"] == 1 and coverage["discovered"] == 1
    assert coverage["excluded"] == {"test source files (src/test/), not counted as operations": 1}


def test_coverage_context_states_counts_reasons_and_unexplained_gap() -> None:
    code = '@mcp.tool(name="a")\n@mcp.tool(name="b")\n'
    text = coverage_context(coverage_summary(5, {"abstract methods": 3}), code)
    assert "found 8 callable operations" in text and "defines 2 tools" in text
    assert "3 abstract methods" in text
    assert "3 other operations are not exposed, without a recorded reason" in text  # 8 - 3 - 2
    assert "do not re-estimate the number of tools" in text
    assert coverage_context(None, code) is None
