"""
Unit tests — CobolParser (discovery/codebase/cobol.py)

Covers:
  - Paragraphs/sections are NOT extracted as tools (2026-10-06 decision :
    internal-only, never executable, pure noise on real legacy codebases —
    see module docstring in cobol.py)
  - FUNCTION-ID (modern COBOL)
  - CALL external programs with USING params
  - Reserved word rejection
  - Fixed vs free format detection
  - PROGRAM-ID used as slug prefix (via CALL/subprogram, not paragraphs)
  - File without PROCEDURE DIVISION → empty list
  - Unreadable file → empty list
"""
from pathlib import Path

import pytest

from mcp_forge.discovery.codebase.cobol import CobolParser, _detect_format, _is_valid_paragraph
from mcp_forge.models import ParameterType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse(source: str, tmp_path: Path, suffix: str = ".cbl") -> list:
    f = tmp_path / f"prog{suffix}"
    f.write_text(source, encoding="utf-8")
    return CobolParser().extract(f, tmp_path)


# ---------------------------------------------------------------------------
# Paragraphs / sections — NOT extracted as tools (2026-10-06 decision)
#
# Found while testing on real legacy code (aws-mainframe-modernization-
# carddemo): the paragraphs/sections of a monolithic PROCEDURE DIVISION
# are NEVER executable on their own (shared global state) and are NOT
# an external contact point: on that real codebase they were
# 194 of the 195 generated tools, all identical static stubs. An MCP
# agent needs to reach external inputs/outputs (CALL, isolated
# subprograms), not the internal plumbing of a single program.
# ---------------------------------------------------------------------------

def test_bare_paragraph_not_extracted(tmp_path):
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BILLING.
       PROCEDURE DIVISION.
           COMPUTE-TOTAL.
               DISPLAY 'hello'.
    """
    tools = parse(source, tmp_path)
    assert tools == []


def test_section_not_extracted(tmp_path):
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. REPORT.
       PROCEDURE DIVISION.
           INIT-SECTION SECTION.
               DISPLAY 'init'.
           MAIN-SECTION SECTION.
               DISPLAY 'main'.
    """
    tools = parse(source, tmp_path)
    assert tools == []


def test_reserved_words_not_extracted(tmp_path):
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MYAPP.
       PROCEDURE DIVISION.
           STOP RUN.
    """
    tools = parse(source, tmp_path)
    names = [t.name for t in tools]
    assert not any(n.endswith("_stop") or n.endswith("_end") for n in names)


def test_program_id_used_as_prefix_for_external_call(tmp_path):
    """The PROGRAM-ID prefix still applies to real tools (external CALL): since paragraphs are no
    longer extracted, it can no longer be tested through a paragraph as before."""
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYROLL.
       PROCEDURE DIVISION.
           CALL 'PAY-SLIP' USING WS-EMPLOYEE.
           STOP RUN.
    """
    tools = parse(source, tmp_path)
    assert any("pay_slip" in t.name for t in tools)


def test_compound_scope_terminators_never_leak_as_tools(tmp_path):
    """Found while testing on real legacy code (aws-mainframe-modernization-carddemo,
    CBACT01C.cbl): END-PERFORM./END-IF. alone on their line looked syntactically like a paragraph
    label. Since paragraphs are no longer extracted at all (see above), that risk is gone by
    design: this test keeps a record of the concrete case."""
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CBACT01C.
       PROCEDURE DIVISION.
           REAL-PARAGRAPH.
               PERFORM VARYING WS-IDX FROM 1 BY 1 UNTIL WS-IDX > 10
                   DISPLAY WS-IDX
               END-PERFORM.
               IF WS-IDX > 5
                   DISPLAY 'big'
               END-IF.
               EXEC CICS
                   SYNCPOINT
               END-EXEC.
    """
    tools = parse(source, tmp_path)
    assert tools == []


def test_no_procedure_division_returns_empty(tmp_path):
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. EMPTY.
       DATA DIVISION.
           WORKING-STORAGE SECTION.
    """
    tools = parse(source, tmp_path)
    assert tools == []


# ---------------------------------------------------------------------------
# FUNCTION-ID (modern COBOL)
# ---------------------------------------------------------------------------

def test_function_id_extracted(tmp_path):
    source = """\
       IDENTIFICATION DIVISION.
       FUNCTION-ID. CALC-TAX.
       PROCEDURE DIVISION.
           COMPUTE TAX = AMOUNT * 0.2.
           GOBACK.
    """
    tools = parse(source, tmp_path)
    names = [t.name for t in tools]
    assert any("calc_tax" in n for n in names)


# ---------------------------------------------------------------------------
# CALL external programs
# ---------------------------------------------------------------------------

def test_call_external_extracted(tmp_path):
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAIN.
       PROCEDURE DIVISION.
           CALL 'SEND-EMAIL' USING WS-RECIPIENT WS-BODY.
           STOP RUN.
    """
    tools = parse(source, tmp_path)
    names = [t.name for t in tools]
    assert any("send_email" in n for n in names)


def test_call_system_ignored(tmp_path):
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAIN.
       PROCEDURE DIVISION.
           CALL 'SYSTEM' USING WS-CMD.
           STOP RUN.
    """
    tools = parse(source, tmp_path)
    names = [t.name for t in tools]
    assert not any("system" in n for n in names)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_tool_metadata_language(tmp_path):
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. META.
       PROCEDURE DIVISION.
           CALL 'DO-WORK' USING WS-ARG.
           STOP RUN.
    """
    tools = parse(source, tmp_path)
    assert tools  # sanity: the source does give at least one real tool
    for t in tools:
        assert t.metadata.get("language") == "cobol"


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def test_detect_format_fixed():
    fixed = "\n".join(
        ("      *comment" if i % 5 == 0 else "      " + " " * 66)
        for i in range(20)
    )
    assert _detect_format(fixed) == "fixed"


def test_detect_format_free():
    free = "IDENTIFICATION DIVISION.\nPROGRAM-ID. FREE.\n"
    assert _detect_format(free) == "free"


# ---------------------------------------------------------------------------
# Helper purity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("COMPUTE-TOTAL", True),
    ("INIT-DATA", True),
    ("END", False),           # reserved word
    ("STOP", False),          # reserved word
    ("END-PERFORM", False),   # compound scope terminator
    ("END-IF", False),        # compound scope terminator
    ("END-READ", False),      # compound scope terminator
    ("END-STRING", False),    # compound scope terminator
    ("END-EXEC", False),      # EXEC SQL/CICS block terminator
    ("END-OF-FILE", True),    # legitimate paragraph name, NOT a terminator
    ("1BAD", False),          # starts with digit
    ("X", False),             # too short
])
def test_is_valid_paragraph(name, expected):
    assert _is_valid_paragraph(name) == expected


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

def test_empty_file_returns_empty(tmp_path):
    f = tmp_path / "empty.cbl"
    f.write_text("", encoding="utf-8")
    assert CobolParser().extract(f, tmp_path) == []


def test_missing_file_returns_empty(tmp_path):
    f = tmp_path / "ghost.cbl"
    assert CobolParser().extract(f, tmp_path) == []


# ---------------------------------------------------------------------------
# Modern subprograms (isolated, explicit parameters and output)
#
# 2026-10-05, decision: COBOL has two clearly distinct "forms", but it is
# NOT fixed vs free format (that is only layout, unrelated to our problem):
# it is the structure of the PROCEDURE DIVISION. A PROGRAM-ID subprogram
# with an explicit USING clause (inputs and output; see GnuCOBOL: RETURNING
# on a CALLed subprogram is NOT implemented by GnuCOBOL 3.2, tested) has
# isolated parameters and output, unlike the historical style of a
# monolithic PROCEDURE DIVISION of paragraphs sharing a global state.
# Only this modern form is really executable.
#
# ---------------------------------------------------------------------------

def test_subprogram_with_using_clause_extracted_with_real_params(tmp_path):
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. IS-PRIME.
       DATA DIVISION.
       LINKAGE SECTION.
       01 LS-N        PIC 9(4).
       01 LS-RESULT   PIC 9.
       PROCEDURE DIVISION USING LS-N LS-RESULT.
           MOVE 1 TO LS-RESULT.
           GOBACK.
       END PROGRAM IS-PRIME.
    """
    tools = parse(source, tmp_path, suffix=".cob")
    subprograms = [t for t in tools if t.metadata.get("type") == "subprogram"]
    assert len(subprograms) == 1
    tool = subprograms[0]
    assert len(tool.parameters) == 1  # LS-RESULT is the output, not a parameter
    assert tool.parameters[0].name == "n"
    assert tool.metadata["cobol_output"]["name"] == "LS-RESULT"


def test_subprogram_output_param_not_in_tool_parameters(tmp_path):
    """Convention: the LAST parameter of the USING clause is the output (passed by reference,
    changed by the subprogram): it must never appear as an input parameter of the generated
    tool."""
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FACTORIAL.
       DATA DIVISION.
       LINKAGE SECTION.
       01 LS-N2       PIC 9(4).
       01 LS-RESULT2  PIC 9(9).
       PROCEDURE DIVISION USING LS-N2 LS-RESULT2.
           GOBACK.
       END PROGRAM FACTORIAL.
    """
    tools = parse(source, tmp_path, suffix=".cob")
    subprograms = [t for t in tools if t.metadata.get("type") == "subprogram"]
    names = [p.name for p in subprograms[0].parameters]
    assert "result2" not in names
    assert names == ["n2"]


def test_subprogram_using_clause_with_commas_detected(tmp_path):
    """Found on real legacy code (CSUTLDTC.cbl, aws-mainframe-modernization-carddemo): the comma
    between the names of a USING clause is an optional separator in COBOL ("USING A, B" and
    "USING A B" are the same). An otherwise perfectly isolated subprogram (full LINKAGE SECTION,
    known PICs) was never recognised as such if its USING used commas."""
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CSUTLDTC.
       DATA DIVISION.
       LINKAGE SECTION.
       01 LS-DATE          PIC X(10).
       01 LS-DATE-FORMAT   PIC X(10).
       01 LS-RESULT        PIC 9.
       PROCEDURE DIVISION USING LS-DATE, LS-DATE-FORMAT, LS-RESULT.
           GOBACK.
       END PROGRAM CSUTLDTC.
    """
    tools = parse(source, tmp_path, suffix=".cob")
    subprograms = [t for t in tools if t.metadata.get("type") == "subprogram"]
    assert len(subprograms) == 1
    names = [p.name for p in subprograms[0].parameters]
    assert names == ["date", "date_format"]  # LS-RESULT is the output


def test_subprogram_string_param_detected_with_max_length(tmp_path):
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. REVERSE-STRING.
       DATA DIVISION.
       LINKAGE SECTION.
       01 LS-S        PIC X(50).
       01 LS-R        PIC X(50).
       PROCEDURE DIVISION USING LS-S LS-R.
           GOBACK.
       END PROGRAM REVERSE-STRING.
    """
    tools = parse(source, tmp_path, suffix=".cob")
    subprograms = [t for t in tools if t.metadata.get("type") == "subprogram"]
    tool = subprograms[0]
    assert tool.parameters[0].type == ParameterType.STRING
    assert tool.metadata["cobol_params"][0]["max_len"] == 50
    assert tool.metadata["cobol_output"]["max_len"] == 50


def test_subprogram_requires_matching_linkage_declaration(tmp_path):
    """If a name of the USING clause has no matching PIC declaration in the LINKAGE SECTION, the
    convention is not followed: ignore it rather than guess a default type."""
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BROKEN.
       DATA DIVISION.
       LINKAGE SECTION.
       01 LS-N        PIC 9(4).
       PROCEDURE DIVISION USING LS-N LS-UNDECLARED.
           GOBACK.
       END PROGRAM BROKEN.
    """
    tools = parse(source, tmp_path, suffix=".cob")
    assert not any(t.metadata.get("type") == "subprogram" for t in tools)


def test_subprogram_single_using_param_not_extracted(tmp_path):
    """A single parameter in the USING clause is not enough: the convention needs at least one
    input AND one output."""
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ONEPARAM.
       DATA DIVISION.
       LINKAGE SECTION.
       01 LS-N        PIC 9(4).
       PROCEDURE DIVISION USING LS-N.
           GOBACK.
       END PROGRAM ONEPARAM.
    """
    tools = parse(source, tmp_path, suffix=".cob")
    assert not any(t.metadata.get("type") == "subprogram" for t in tools)


def test_multiple_subprograms_in_one_file_each_get_own_name(tmp_path):
    """A modern file usually holds several independent subprograms: each is prefixed with the
    FILE name (not with the first PROGRAM-ID of the file, which would be misleading for the
    others)."""
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. IS-PRIME.
       DATA DIVISION.
       LINKAGE SECTION.
       01 LS-N        PIC 9(4).
       01 LS-RESULT   PIC 9.
       PROCEDURE DIVISION USING LS-N LS-RESULT.
           GOBACK.
       END PROGRAM IS-PRIME.

       IDENTIFICATION DIVISION.
       PROGRAM-ID. FACTORIAL.
       DATA DIVISION.
       LINKAGE SECTION.
       01 LS-N2       PIC 9(4).
       01 LS-RESULT2  PIC 9(9).
       PROCEDURE DIVISION USING LS-N2 LS-RESULT2.
           GOBACK.
       END PROGRAM FACTORIAL.
    """
    f = tmp_path / "utils.cob"
    f.write_text(source, encoding="utf-8")
    tools = CobolParser().extract(f, tmp_path)
    subprogram_names = {t.name for t in tools if t.metadata.get("type") == "subprogram"}
    assert subprogram_names == {"utils_is_prime", "utils_factorial"}


def test_legacy_monolithic_paragraphs_not_marked_as_subprogram(tmp_path):
    """The historical style (a single PROCEDURE DIVISION of paragraphs, without a USING clause)
    gives no tool (2026-10-06: raw paragraphs are no longer extracted at all, never executable
    on their own, shared global state), and so is never marked type=subprogram."""
    source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. UTILS.
       PROCEDURE DIVISION.
       IS-PRIME.
           DISPLAY 'ok'.
    """
    tools = parse(source, tmp_path, suffix=".cob")
    assert not any(t.metadata.get("type") == "subprogram" for t in tools)
    assert not any(t.metadata.get("type") == "paragraph" for t in tools)
    assert tools == []
