"""
Regression 2026-09-30, found while running a batch of 27 generation tests: a C project without
any .h file gave 0 tools.

`_collect_files()` explicitly documents a "no headers: fall back on the sources" fallback
(mcp_forge/discovery/codebase/__init__.py), but `_FUNC_DECL_RE` only accepted a `;` ending (a
header prototype): a full function definition (`int foo(int n) { ... }`) never matched, which made
the fallback useless for a standalone .c/.cpp file without a header.
"""
from __future__ import annotations

from pathlib import Path

from mcp_forge.discovery.codebase.cpp import CppParser

SOURCE_ONLY_C = """\
/* Small utility module. */
#include <string.h>

int is_prime(int n) {
    if (n < 2) return 0;
    for (int i = 2; i * i <= n; i++) {
        if (n % i == 0) return 0;
    }
    return 1;
}

long factorial(int n) {
    long result = 1;
    for (int i = 2; i <= n; i++) result *= i;
    return result;
}
"""


def test_source_only_c_file_without_header_is_parsed(tmp_path: Path) -> None:
    f = tmp_path / "utils.c"
    f.write_text(SOURCE_ONLY_C, encoding="utf-8")

    tools = CppParser().extract(f, tmp_path)

    names = {t.name for t in tools}
    assert names == {"is_prime", "factorial"}


def test_header_prototype_still_parsed(tmp_path: Path) -> None:
    f = tmp_path / "utils.h"
    f.write_text("int is_prime(int n);\nlong factorial(int n);\n", encoding="utf-8")

    tools = CppParser().extract(f, tmp_path)

    names = {t.name for t in tools}
    assert names == {"is_prime", "factorial"}


def test_control_flow_keywords_are_not_mistaken_for_functions(tmp_path: Path) -> None:
    f = tmp_path / "loop.c"
    f.write_text(
        """\
int count_up(int n) {
    int total = 0;
    for (int i = 0; i < n; i++) {
        if (i % 2 == 0) {
            total += i;
        }
    }
    while (total > 1000) {
        total -= 1;
    }
    switch (n) {
        case 0:
            break;
    }
    return total;
}
""",
        encoding="utf-8",
    )

    tools = CppParser().extract(f, tmp_path)

    names = {t.name for t in tools}
    assert names == {"count_up"}
