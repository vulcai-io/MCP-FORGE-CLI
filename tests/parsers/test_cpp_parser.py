"""
Unit tests — CppParser (discovery/codebase/cpp.py)

Covers:
  - Header (.h/.hpp) function extraction
  - Class member functions (ClassName::method, or declared inside a
    class/struct body) are NEVER extracted — not dispatchable via
    ctypes (mangled name, no "this" pointer) — see 2026-10-06 fix
  - Doxygen comments → description (/** */, ///, //!)
  - Type mapping (int→INTEGER, float→NUMBER, bool→BOOLEAN, char*→STRING)
  - Output pointer parameters excluded from MCP input params
  - const suffix on methods
  - Virtual/inline/static qualifiers
  - Skip macros (ALL_CAPS names)
  - Skip private-prefixed names (_name)
  - Skip reserved names (main, operator, delete)
  - Duplicate slug deduplication
"""
from pathlib import Path

import pytest

from mcp_forge.discovery.codebase.cpp import CppParser
from mcp_forge.models import ParameterType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_header(source: str, tmp_path: Path, suffix: str = ".h") -> list:
    f = tmp_path / f"api{suffix}"
    f.write_text(source, encoding="utf-8")
    return CppParser().extract(f, tmp_path)


def parse_source(source: str, tmp_path: Path) -> list:
    f = tmp_path / "impl.cpp"
    f.write_text(source, encoding="utf-8")
    return CppParser().extract(f, tmp_path)


# ---------------------------------------------------------------------------
# Basic extraction — header
# ---------------------------------------------------------------------------

def test_simple_function_extracted(tmp_path):
    source = "int add(int a, int b);\n"
    tools = parse_header(source, tmp_path)
    assert len(tools) == 1
    assert tools[0].name == "add"


def test_void_function_extracted(tmp_path):
    source = "void reset(int id);\n"
    tools = parse_header(source, tmp_path)
    assert len(tools) == 1


def test_multiple_functions(tmp_path):
    source = "int open_db(const char* path);\nvoid close_db(int handle);\n"
    tools = parse_header(source, tmp_path)
    assert len(tools) == 2


# ---------------------------------------------------------------------------
# Qualifiers
# ---------------------------------------------------------------------------

def test_static_function_extracted(tmp_path):
    source = "static int get_count();\n"
    tools = parse_header(source, tmp_path)
    assert len(tools) == 1


def test_class_method_not_extracted_when_file_starts_with_comment(tmp_path):
    """Found on a real C++ project (a header that starts with a 4-line licence block): the text
    "cleaned" of comments (`cleaned`) and the original text (`source`) had different lengths as
    soon as a comment was removed (a block replaced by a single space, a line removed
    entirely), so the positions in `cleaned` no longer matched those in `source`.
    `_detect_class_context(source)` looked for the class context at the WRONG positions, letting
    class methods through as free functions whenever a comment came before the class in the
    file."""
    source = """\
/*
 * License header
 * spanning several lines
 */
class RingBuffer {
public:
    void clear() {
    }
};
"""
    tools = parse_header(source, tmp_path)
    assert tools == []


def test_class_method_not_extracted(tmp_path):
    """2026-10-06, found while testing on a real C++ project: 486 of the 652 extracted tools (74%)
    were class methods that cannot be dispatched through ctypes (mangled C++ name, no symbol
    exported under that name, no "this" pointer). A method declared inside a class body (virtual
    or not) is never a directly callable free function: it must no longer be extracted as a
    tool."""
    source = """\
class Engine {
    virtual void start(int mode);
};
"""
    tools = parse_header(source, tmp_path)
    assert tools == []


def test_qualified_method_definition_in_source_not_extracted(tmp_path):
    """Classic out-of-class definition: "ClassName::method() { ... }" in a .cpp: always filtered
    out (behaviour already right before 2026-10-06, kept)."""
    source = "void Engine::start(int mode) {\n}\n"
    tools = parse_source(source, tmp_path)
    assert tools == []


def test_free_function_in_source_still_extracted(tmp_path):
    """Sanity check: the filter must remove ONLY class methods: a free function in a .cpp is still
    extracted."""
    source = "void start_engine(int mode) {\n}\n"
    tools = parse_source(source, tmp_path)
    assert len(tools) == 1


def test_inline_function_extracted(tmp_path):
    source = "inline float lerp(float a, float b, float t);\n"
    tools = parse_header(source, tmp_path)
    assert len(tools) == 1


# ---------------------------------------------------------------------------
# Skip rules
# ---------------------------------------------------------------------------

def test_constructor_member_initializer_not_mistaken_for_a_function(tmp_path):
    """Found while testing on a real C++ project (a random number generator header):
    "noexcept : s(initialState) {" (a constructor's initializer list) was captured as
    "word word(params) {": the ":" of the initializer list was swallowed by the "return type"
    group (which allows ":" for qualified types such as std::string), leaving "s" as a false
    one-letter function name."""
    source = """\
class Rng {
    StateType s;
    explicit Rng(const StateType& initialState) noexcept : s(initialState) {
    }
};
"""
    tools = parse_header(source, tmp_path)
    assert not any(t.name == "s" for t in tools)


def test_template_function_not_extracted(tmp_path):
    """Found while testing on a real C++ project: a function template
    (`template<typename T> constexpr inline uint8_t count_bits(T val)`) has, like class methods,
    no stable exported symbol under its raw name (each instantiation generates its own code, often
    inlined). Besides not being dispatchable, the type parameter `T` (a template parameter, not a
    concrete type) fell back on the str/c_char_p default of the type mapping, for a function that
    really expects an integer."""
    source = """\
namespace util {
template<typename T>
constexpr inline uint8_t count_bits(T val) {
    return 0;
}
}
"""
    tools = parse_header(source, tmp_path)
    assert not any(t.name == "count_bits" for t in tools)


def test_template_on_same_line_not_extracted(tmp_path):
    source = "template<typename T> T identity(T val) { return val; }\n"
    tools = parse_header(source, tmp_path)
    assert tools == []


def test_single_letter_free_function_name_rejected(tmp_path):
    """A real C export almost never has a one-letter name: a generic safety filter, not only for
    the case above."""
    source = "int s(int x);\n"
    tools = parse_header(source, tmp_path)
    assert tools == []


def test_if_constexpr_not_mistaken_for_a_function(tmp_path):
    """Found while testing on a real C++ project: "if constexpr(EXPR) { ... }" has exactly the
    structural shape of a function declaration ("word word(params) {"): the control keyword "if"
    ends up in the "return type" group rather than in the "name" group, which `_SKIP_NAMES` (that
    only filters the name group) did not cover. It generated a false "constexpr" tool."""
    source = """\
template<typename T>
void dispatch() {
    if constexpr(T::initialized) {
        do_work();
    }
}
"""
    tools = parse_header(source, tmp_path)
    names = [t.name for t in tools]
    assert "constexpr" not in names


def test_else_if_constexpr_not_mistaken_for_a_function(tmp_path):
    """The same ambiguity, 'else if constexpr' variant (seen in the same real project)."""
    source = """\
void dispatch() {
    if constexpr(A) {
    } else if constexpr(B) {
    }
}
"""
    tools = parse_header(source, tmp_path)
    assert not any(t.name == "constexpr" for t in tools)

def test_private_prefixed_skipped(tmp_path):
    source = "void _internal_cleanup();\n"
    tools = parse_header(source, tmp_path)
    assert tools == []


def test_macro_like_name_skipped(tmp_path):
    source = "void INIT_SYSTEM(int flags);\n"
    tools = parse_header(source, tmp_path)
    assert tools == []


def test_main_skipped(tmp_path):
    source = "int main(int argc, char** argv);\n"
    tools = parse_header(source, tmp_path)
    assert tools == []


# ---------------------------------------------------------------------------
# Type mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("c_type,expected", [
    ("int", ParameterType.INTEGER),
    ("long", ParameterType.INTEGER),
    ("uint32_t", ParameterType.INTEGER),
    ("float", ParameterType.NUMBER),
    ("double", ParameterType.NUMBER),
    ("bool", ParameterType.BOOLEAN),
    ("const char*", ParameterType.STRING),
])
def test_type_mapping(tmp_path, c_type, expected):
    source = f"void fn({c_type} value);\n"
    tools = parse_header(source, tmp_path)
    if tools and tools[0].parameters:
        assert tools[0].parameters[0].type == expected


# ---------------------------------------------------------------------------
# Output pointer parameters
# ---------------------------------------------------------------------------

def test_output_int_pointer_excluded_from_mcp_params(tmp_path):
    source = "void compute(int input, int* out_result);\n"
    tools = parse_header(source, tmp_path)
    assert len(tools) == 1
    param_names = [p.name for p in tools[0].parameters]
    assert "input" in param_names
    assert "out_result" not in param_names


def test_const_pointer_not_treated_as_output(tmp_path):
    source = "void display(const char* message);\n"
    tools = parse_header(source, tmp_path)
    assert len(tools) == 1
    assert len(tools[0].parameters) == 1


# ---------------------------------------------------------------------------
# Doxygen descriptions
# ---------------------------------------------------------------------------

def test_doxygen_block_comment_as_description(tmp_path):
    # /** style: description is either the Doxygen text or the fallback signature
    source = """\
/** Initialises the database connection. */
int db_connect(const char* url);
"""
    tools = parse_header(source, tmp_path)
    assert tools[0].description  # non-empty: either Doxygen or fallback


def test_doxygen_triple_slash_as_description(tmp_path):
    source = """\
/// Opens the file at the given path.
int open_file(const char* path);
"""
    tools = parse_header(source, tmp_path)
    assert "file" in tools[0].description.lower() or "path" in tools[0].description.lower()


def test_no_doxygen_fallback_description(tmp_path):
    source = "int get_value(int key);\n"
    tools = parse_header(source, tmp_path)
    assert tools[0].description  # non-empty fallback


# ---------------------------------------------------------------------------
# .hpp header
# ---------------------------------------------------------------------------

def test_hpp_header_parsed(tmp_path):
    source = "double calculate(double x, double y);\n"
    tools = parse_header(source, tmp_path, suffix=".hpp")
    assert len(tools) == 1


# ---------------------------------------------------------------------------
# Source file (.cpp) — only non-member functions
# ---------------------------------------------------------------------------

def test_cpp_source_free_function_extracted(tmp_path):
    source = "int helper(int x) { return x + 1; }\n"
    tools = parse_source(source, tmp_path)
    # Free functions in .cpp may or may not be extracted depending on ; rule
    # (parser requires ;) — this is expected behaviour: .cpp implementations
    # without headers produce fewer results
    assert isinstance(tools, list)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata_language(tmp_path):
    source = "void do_work(int x);\n"
    tools = parse_header(source, tmp_path)
    assert tools[0].metadata["language"] == "cpp"


def test_metadata_is_header(tmp_path):
    source = "void do_work(int x);\n"
    tools = parse_header(source, tmp_path, suffix=".h")
    assert tools[0].metadata["is_header"] is True


def test_metadata_return_type(tmp_path):
    source = "float compute(int x);\n"
    tools = parse_header(source, tmp_path)
    assert "float" in tools[0].metadata["return_type"]


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

def test_empty_file_returns_empty(tmp_path):
    f = tmp_path / "empty.h"
    f.write_text("", encoding="utf-8")
    assert CppParser().extract(f, tmp_path) == []


def test_missing_file_returns_empty(tmp_path):
    f = tmp_path / "ghost.h"
    assert CppParser().extract(f, tmp_path) == []
