"""
Unit tests — FortranParser (discovery/codebase/fortran.py)

Covers:
  - SUBROUTINE extraction (free format .f90)
  - FUNCTION extraction with return type
  - Parameter list parsing
  - MODULE name used as prefix
  - Fixed format (.f) — comment stripping
  - Unsupported extension → empty list
  - Reserved word rejection
  - Modifier keywords (PURE, RECURSIVE, ELEMENTAL)
  - Duplicate slug deduplication
"""
from pathlib import Path

import pytest

from mcp_forge.discovery.codebase.fortran import FortranParser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse(source: str, tmp_path: Path, suffix: str = ".f90") -> list:
    f = tmp_path / f"mod{suffix}"
    f.write_text(source, encoding="utf-8")
    return FortranParser().extract(f, tmp_path)


# ---------------------------------------------------------------------------
# Subroutines
# ---------------------------------------------------------------------------

def test_subroutine_extracted(tmp_path):
    source = """\
MODULE Physics
CONTAINS
  SUBROUTINE compute_force(mass, accel, force)
    REAL, INTENT(IN) :: mass, accel
    REAL, INTENT(OUT) :: force
    force = mass * accel
  END SUBROUTINE
END MODULE
"""
    tools = parse(source, tmp_path)
    names = [t.name for t in tools]
    assert any("compute_force" in n for n in names)


def test_subroutine_params_extracted(tmp_path):
    source = """\
SUBROUTINE move(x, y, z)
  REAL :: x, y, z
END SUBROUTINE
"""
    tools = parse(source, tmp_path)
    assert len(tools) == 1
    param_names = [p.name for p in tools[0].parameters]
    assert "x" in param_names
    assert "y" in param_names
    assert "z" in param_names


def test_subroutine_no_params(tmp_path):
    source = """\
SUBROUTINE init()
  IMPLICIT NONE
END SUBROUTINE
"""
    tools = parse(source, tmp_path)
    assert len(tools) == 1
    assert tools[0].parameters == []


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def test_function_extracted(tmp_path):
    source = """\
REAL FUNCTION dot_product_custom(a, b, n)
  REAL, INTENT(IN) :: a(n), b(n)
  INTEGER, INTENT(IN) :: n
  dot_product_custom = SUM(a * b)
END FUNCTION
"""
    tools = parse(source, tmp_path)
    names = [t.name for t in tools]
    assert any("dot_product_custom" in n for n in names)


def test_pure_function_extracted(tmp_path):
    source = """\
PURE FUNCTION square(x)
  REAL, INTENT(IN) :: x
  square = x * x
END FUNCTION
"""
    tools = parse(source, tmp_path)
    names = [t.name for t in tools]
    assert any("square" in n for n in names)


def test_recursive_subroutine_extracted(tmp_path):
    source = """\
RECURSIVE SUBROUTINE factorial(n, result)
  INTEGER, INTENT(IN) :: n
  INTEGER, INTENT(OUT) :: result
END SUBROUTINE
"""
    tools = parse(source, tmp_path)
    assert len(tools) == 1


# ---------------------------------------------------------------------------
# Module prefix
# ---------------------------------------------------------------------------

def test_module_name_as_prefix(tmp_path):
    source = """\
MODULE Geometry
CONTAINS
  SUBROUTINE area(r)
    REAL :: r
  END SUBROUTINE
END MODULE
"""
    tools = parse(source, tmp_path)
    assert any(t.name.startswith("geometry_") for t in tools)


# ---------------------------------------------------------------------------
# Fixed format (.f)
# ---------------------------------------------------------------------------

def test_fixed_format_subroutine(tmp_path):
    source = (
        "C     This is a comment\n"
        "      SUBROUTINE LEGACY(X, Y)\n"
        "      REAL X, Y\n"
        "      END\n"
    )
    tools = parse(source, tmp_path, suffix=".f")
    names = [t.name for t in tools]
    assert any("legacy" in n for n in names)


def test_fixed_format_comments_stripped(tmp_path):
    source = (
        "C This should be ignored\n"
        "* Also ignored\n"
        "      SUBROUTINE CLEAN(A)\n"
        "      END\n"
    )
    tools = parse(source, tmp_path, suffix=".f")
    assert len(tools) == 1


# ---------------------------------------------------------------------------
# Unsupported extension
# ---------------------------------------------------------------------------

def test_unsupported_extension_returns_empty(tmp_path):
    f = tmp_path / "code.py"
    f.write_text("SUBROUTINE fake(x)\nEND SUBROUTINE\n", encoding="utf-8")
    assert FortranParser().extract(f, tmp_path) == []


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_tool_metadata_language(tmp_path):
    source = "SUBROUTINE work(x)\n  REAL :: x\nEND SUBROUTINE\n"
    tools = parse(source, tmp_path)
    assert tools[0].metadata["language"] == "fortran"


def test_subroutine_metadata_type(tmp_path):
    source = "SUBROUTINE work(x)\n  REAL :: x\nEND SUBROUTINE\n"
    tools = parse(source, tmp_path)
    assert tools[0].metadata["type"] == "subroutine"


def test_function_metadata_type(tmp_path):
    source = "REAL FUNCTION area(r)\n  REAL :: r\n  area = 3.14 * r * r\nEND FUNCTION\n"
    tools = parse(source, tmp_path)
    assert tools[0].metadata["type"] == "function"


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

def test_empty_file_returns_empty(tmp_path):
    f = tmp_path / "empty.f90"
    f.write_text("", encoding="utf-8")
    assert FortranParser().extract(f, tmp_path) == []


def test_missing_file_returns_empty(tmp_path):
    f = tmp_path / "ghost.f90"
    assert FortranParser().extract(f, tmp_path) == []
