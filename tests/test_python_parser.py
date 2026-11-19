"""
Unit tests: PythonParser (discovery/codebase/python.py).

Covers:
  - extraction of public / private functions
  - extraction of class methods
  - annotation types (str, int, float, bool, list, dict, Optional)
  - required vs optional parameters (default values)
  - self/cls parameter ignored
  - docstring to description and params
  - negative default values
  - invalid file (SyntaxError gives an empty list)
"""
import textwrap
from pathlib import Path

import pytest

from mcp_forge.discovery.codebase.python import PythonParser, _first_line, _parse_docstring_params
from mcp_forge.models import ParameterType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse(source: str, tmp_path: Path) -> list:
    """Writes the source to a temporary file and calls PythonParser.extract."""
    f = tmp_path / "module.py"
    f.write_text(textwrap.dedent(source), encoding="utf-8")
    return PythonParser().extract(f, tmp_path)


# ---------------------------------------------------------------------------
# Public / private functions
# ---------------------------------------------------------------------------

def test_public_function_extracted(tmp_path):
    tools = parse("""
        def get_user(user_id: int) -> str:
            pass
    """, tmp_path)
    assert len(tools) == 1
    assert tools[0].name == "get_user"


def test_private_function_ignored(tmp_path):
    tools = parse("""
        def _internal():
            pass
    """, tmp_path)
    assert tools == []


def test_multiple_functions(tmp_path):
    tools = parse("""
        def foo(): pass
        def bar(): pass
        def _baz(): pass
    """, tmp_path)
    assert [t.name for t in tools] == ["foo", "bar"]


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------

def test_class_public_method_extracted(tmp_path):
    tools = parse("""
        class MyService:
            def get_item(self, item_id: int): pass
    """, tmp_path)
    assert len(tools) == 1
    assert tools[0].name == "myservice_get_item"


def test_class_private_method_ignored(tmp_path):
    tools = parse("""
        class MyService:
            def _helper(self): pass
    """, tmp_path)
    assert tools == []


def test_self_cls_not_in_params(tmp_path):
    tools = parse("""
        class Svc:
            def action(self, name: str): pass
    """, tmp_path)
    params = [p.name for p in tools[0].parameters]
    assert "self" not in params
    assert "name" in params


# ---------------------------------------------------------------------------
# Types d'annotations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("annotation,expected_type", [
    ("str",   ParameterType.STRING),
    ("int",   ParameterType.INTEGER),
    ("float", ParameterType.NUMBER),
    ("bool",  ParameterType.BOOLEAN),
    ("list",  ParameterType.ARRAY),
    ("dict",  ParameterType.OBJECT),
])
def test_annotation_types(tmp_path, annotation, expected_type):
    tools = parse(f"""
        def fn(x: {annotation}): pass
    """, tmp_path)
    assert tools[0].parameters[0].type == expected_type


def test_optional_annotation(tmp_path):
    tools = parse("""
        from typing import Optional
        def fn(x: Optional[str] = None): pass
    """, tmp_path)
    p = tools[0].parameters[0]
    assert p.type == ParameterType.STRING
    assert not p.required


def test_list_generic_annotation(tmp_path):
    tools = parse("""
        from typing import List
        def fn(items: List[str]): pass
    """, tmp_path)
    assert tools[0].parameters[0].type == ParameterType.ARRAY


# ---------------------------------------------------------------------------
# Required / optional / default values
# ---------------------------------------------------------------------------

def test_required_param(tmp_path):
    tools = parse("""
        def fn(x: str): pass
    """, tmp_path)
    assert tools[0].parameters[0].required is True


def test_optional_default_none(tmp_path):
    tools = parse("""
        def fn(x: str = "hello"): pass
    """, tmp_path)
    p = tools[0].parameters[0]
    assert not p.required
    assert p.default == "hello"


def test_default_integer(tmp_path):
    tools = parse("""
        def fn(limit: int = 10): pass
    """, tmp_path)
    p = tools[0].parameters[0]
    assert p.default == 10
    assert not p.required


def test_default_negative_number(tmp_path):
    tools = parse("""
        def fn(offset: int = -1): pass
    """, tmp_path)
    assert tools[0].parameters[0].default == -1


def test_default_bool(tmp_path):
    tools = parse("""
        def fn(verbose: bool = False): pass
    """, tmp_path)
    p = tools[0].parameters[0]
    assert p.default is False
    assert not p.required


# ---------------------------------------------------------------------------
# Docstrings
# ---------------------------------------------------------------------------

def test_docstring_description(tmp_path):
    tools = parse("""
        def fn():
            \"\"\"Returns the answer.\"\"\"
            pass
    """, tmp_path)
    assert tools[0].description == "Returns the answer."


def test_docstring_param_google_style(tmp_path):
    tools = parse("""
        def fn(user_id: int):
            \"\"\"Get a user.

            Args:
                user_id (int): The user identifier.
            \"\"\"
            pass
    """, tmp_path)
    p = tools[0].parameters[0]
    assert "user" in p.description.lower() or "identifier" in p.description.lower()


def test_no_docstring_fallback_name(tmp_path):
    tools = parse("""
        def get_data(): pass
    """, tmp_path)
    assert tools[0].description == "get_data"


# ---------------------------------------------------------------------------
# Invalid file
# ---------------------------------------------------------------------------

def test_syntax_error_returns_empty(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("def (broken:", encoding="utf-8")
    tools = PythonParser().extract(f, tmp_path)
    assert tools == []


# ---------------------------------------------------------------------------
# Helpers purs
# ---------------------------------------------------------------------------

def test_first_line_basic():
    assert _first_line("Hello world\nSecond line") == "Hello world"


def test_first_line_skips_blank():
    assert _first_line("\n\nActual content") == "Actual content"


def test_first_line_empty():
    assert _first_line("") == ""


def test_parse_docstring_params_sphinx():
    doc = ":param user_id: The user ID\n:param name: The name"
    params = _parse_docstring_params(doc)
    assert params["user_id"] == "The user ID"
    assert params["name"] == "The name"


def test_parse_docstring_params_google():
    doc = "Get item.\n\n    Args:\n        item_id (int): Identifier of the item.\n"
    params = _parse_docstring_params(doc)
    assert "item_id" in params
