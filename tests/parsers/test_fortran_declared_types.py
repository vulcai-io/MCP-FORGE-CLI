"""
2026-10-13, found while regenerating the Fortran example of the public repository: the parser
only read the signature (`function is_prime(n)`), where Fortran declares no type. Every parameter
fell back on `str`, and the driver passed `IS_PRIME("42")` to a function that expects an INTEGER.
Only the LLM enrichment sometimes fixed the types, at random. The types now come from the
declarations of the unit.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mcp_forge.discovery.codebase.fortran import FortranParser
from mcp_forge.models import ParameterType


def _params(tmp_path: Path, filename: str, source: str) -> dict:
    f = tmp_path / filename
    f.write_text(source, encoding="utf-8")
    tools = FortranParser().extract(f, tmp_path)
    return {t.metadata["function"]: {p.name: (p.type, p.items_type) for p in t.parameters} for t in tools}


def test_free_form_declarations_with_intent_and_arrays(tmp_path) -> None:
    params = _params(tmp_path, "m.f90", """
module m
contains
    logical function is_prime(n)
        integer, intent(in) :: n
        is_prime = .true.
    end function is_prime

    real function weighted(values, weights, count, scale)
        real, intent(in) :: values(:)
        double precision, dimension(:), intent(in) :: weights
        integer :: count
        real(kind=8), intent(in) :: scale
        weighted = 0.0
    end function weighted

    subroutine greet(name, loud)
        character(len=*), intent(in) :: name
        logical, intent(in) :: loud
    end subroutine greet
end module m
""")
    assert params["IS_PRIME"] == {"n": (ParameterType.INTEGER, None)}
    assert params["WEIGHTED"] == {
        "values": (ParameterType.ARRAY, ParameterType.NUMBER),
        "weights": (ParameterType.ARRAY, ParameterType.NUMBER),
        "count": (ParameterType.INTEGER, None),
        "scale": (ParameterType.NUMBER, None),
    }
    assert params["GREET"] == {"name": (ParameterType.STRING, None), "loud": (ParameterType.BOOLEAN, None)}


def test_fixed_form_fortran77_declarations(tmp_path) -> None:
    params = _params(tmp_path, "old.f", (
        "      SUBROUTINE SCALE(X, N, F)\n"
        "      INTEGER N\n"
        "      REAL*8 X(N), F\n"
        "      END\n"
    ))
    assert params["SCALE"] == {
        "x": (ParameterType.ARRAY, ParameterType.NUMBER),
        "n": (ParameterType.INTEGER, None),
        "f": (ParameterType.NUMBER, None),
    }


def test_declarations_of_another_unit_not_borrowed(tmp_path) -> None:
    params = _params(tmp_path, "m.f90", """
module m
contains
    integer function aa(x)
        integer, intent(in) :: x
        aa = x
    end function aa

    subroutine bb(x)
        print *, x
    end subroutine bb
end module m
""")
    assert params["AA"] == {"x": (ParameterType.INTEGER, None)}
    assert params["BB"] == {"x": (ParameterType.STRING, None)}  # no declaration: default unchanged
