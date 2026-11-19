"""
Regression 2026-10-06, found while running on a real COBOL codebase
(aws-mainframe-modernization-carddemo): CSUTLDTC is called with CALL by several other programs of
the codebase, AND it also exists itself as the file CSUTLDTC.cbl, rightly recognised as an
isolated, really executable subprogram. CobolParser.extract() handles each file on its own and
cannot know that both refer to the same program: only the overall orchestration
(CodebaseDiscovery) sees both at once. Without cross-file deduplication, the generated MCP server
exposed both a static stub that always fails (the CALL) and the real executable tool (the
subprogram) for the same external program: confusing for an agent, and reported as a bug by the
mcp-forge quality evaluator itself.
"""
from __future__ import annotations

from pathlib import Path

from mcp_forge.discovery.codebase import CodebaseDiscovery, _drop_call_stubs_shadowed_by_subprograms
from mcp_forge.models import DiscoveredTool, ForgeConfig, SourceType


def _call_tool(function: str) -> DiscoveredTool:
    return DiscoveredTool(
        name=f"call_{function.lower()}",
        description=f"CALL '{function}': external program called",
        parameters=[],
        metadata={"file": "a.cbl", "function": function, "type": "call", "language": "cobol"},
    )


def _subprogram_tool(function: str) -> DiscoveredTool:
    return DiscoveredTool(
        name=f"b_{function.lower()}",
        description=f"COBOL subprogram (modern, isolated): {function}",
        parameters=[],
        metadata={"file": "b.cbl", "function": function, "type": "subprogram", "language": "cobol"},
    )


class TestDropCallStubsShadowedBySubprograms:
    def test_call_stub_dropped_when_matching_subprogram_exists(self):
        tools = [_call_tool("CSUTLDTC"), _subprogram_tool("CSUTLDTC")]
        result = _drop_call_stubs_shadowed_by_subprograms(tools)
        types = {t.metadata["type"] for t in result}
        assert types == {"subprogram"}

    def test_call_stub_kept_when_no_matching_subprogram(self):
        """The CALL to an external program (e.g. CEE3ABD, an IBM Language Environment service, never present as a
        source file) must stay: it is the only possible contact point for that program."""
        tools = [_call_tool("CEE3ABD")]
        result = _drop_call_stubs_shadowed_by_subprograms(tools)
        assert len(result) == 1
        assert result[0].metadata["type"] == "call"

    def test_unrelated_calls_and_subprograms_both_kept(self):
        tools = [_call_tool("CEE3ABD"), _subprogram_tool("IS-PRIME")]
        result = _drop_call_stubs_shadowed_by_subprograms(tools)
        assert len(result) == 2


class TestCodebaseDiscoveryIntegration:
    def test_cross_file_call_to_isolated_subprogram_is_deduplicated(self, tmp_path: Path):
        caller = tmp_path / "CALLER.cbl"
        caller.write_text(
            "       IDENTIFICATION DIVISION.\n"
            "       PROGRAM-ID. CALLER.\n"
            "       PROCEDURE DIVISION.\n"
            "           CALL 'CSUTLDTC' USING WS-DATE WS-FORMAT WS-RESULT.\n"
            "           STOP RUN.\n",
            encoding="utf-8",
        )
        callee = tmp_path / "CSUTLDTC.cbl"
        callee.write_text(
            "       IDENTIFICATION DIVISION.\n"
            "       PROGRAM-ID. CSUTLDTC.\n"
            "       DATA DIVISION.\n"
            "       LINKAGE SECTION.\n"
            "       01 LS-DATE        PIC X(10).\n"
            "       01 LS-FORMAT      PIC X(10).\n"
            "       01 LS-RESULT      PIC X(80).\n"
            "       PROCEDURE DIVISION USING LS-DATE, LS-FORMAT, LS-RESULT.\n"
            "           GOBACK.\n"
            "       END PROGRAM CSUTLDTC.\n",
            encoding="utf-8",
        )
        config = ForgeConfig(source=str(tmp_path), source_type=SourceType.CODEBASE, server_name="x")
        result = CodebaseDiscovery(config).discover()

        types_by_function = {
            t.metadata["function"]: t.metadata["type"]
            for t in result.tools
            if t.metadata.get("language") == "cobol"
        }
        assert types_by_function.get("CSUTLDTC") == "subprogram"
        assert not any(
            t.metadata.get("function") == "CSUTLDTC" and t.metadata.get("type") == "call"
            for t in result.tools
        )
