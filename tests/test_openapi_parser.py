"""
Unit tests: OpenAPIDiscovery (discovery/openapi.py).

Covers:
  - endpoint extraction (GET, POST...)
  - JSON Schema type mapping to ParameterType
  - path and query parameters
  - required vs optional parameters
  - base URL extraction
  - empty spec (0 tools)
  - enum values on parameters
"""
import pytest

from mcp_forge.discovery.openapi import OpenAPIDiscovery
from mcp_forge.models import ForgeConfig, ForgeMode, NameStyle, ParameterType, SourceType


# ---------------------------------------------------------------------------
# Helper: injects a spec without network, through monkeypatch
# ---------------------------------------------------------------------------

def make_config() -> ForgeConfig:
    return ForgeConfig(
        source="https://fake.api/openapi.json",
        mode=ForgeMode.AUTO,
        output="./output",
        source_type=SourceType.OPENAPI,
        name_style=NameStyle.SHORT,
    )


def discover(spec: dict, monkeypatch) -> list:
    """Runs OpenAPIDiscovery.discover() with an injected spec (no network)."""
    disc = OpenAPIDiscovery(make_config())
    monkeypatch.setattr(disc, "_load_spec", lambda: spec)
    result = disc.discover()
    return result.tools


# ---------------------------------------------------------------------------
# Spec minimale
# ---------------------------------------------------------------------------

MINIMAL_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Test API", "version": "1.0"},
    "paths": {
        "/users": {
            "get": {
                "operationId": "listUsers",
                "summary": "List all users",
                "parameters": [],
                "responses": {"200": {"description": "OK"}},
            }
        }
    },
}


def test_extracts_one_tool(monkeypatch):
    tools = discover(MINIMAL_SPEC, monkeypatch)
    assert len(tools) == 1


def test_tool_name_from_operation_id(monkeypatch):
    tools = discover(MINIMAL_SPEC, monkeypatch)
    # camelCase "listUsers" → snake_case
    assert tools[0].name == "list_users"


def test_tool_description_from_summary(monkeypatch):
    tools = discover(MINIMAL_SPEC, monkeypatch)
    assert "users" in tools[0].description.lower()


def test_tool_http_method(monkeypatch):
    tools = discover(MINIMAL_SPEC, monkeypatch)
    assert tools[0].http_method == "GET"


def test_tool_endpoint(monkeypatch):
    tools = discover(MINIMAL_SPEC, monkeypatch)
    assert tools[0].endpoint == "/users"


# ---------------------------------------------------------------------------
# Query parameters
# ---------------------------------------------------------------------------

SPEC_WITH_QUERY_PARAMS = {
    "openapi": "3.0.0",
    "info": {"title": "T", "version": "1"},
    "paths": {
        "/search": {
            "get": {
                "operationId": "search",
                "parameters": [
                    {"name": "q", "in": "query", "required": True,
                     "schema": {"type": "string"}},
                    {"name": "limit", "in": "query", "required": False,
                     "schema": {"type": "integer"}},
                ],
                "responses": {},
            }
        }
    },
}


def test_query_params_extracted(monkeypatch):
    tools = discover(SPEC_WITH_QUERY_PARAMS, monkeypatch)
    names = [p.name for p in tools[0].parameters]
    assert "q" in names
    assert "limit" in names


def test_required_param_flagged(monkeypatch):
    tools = discover(SPEC_WITH_QUERY_PARAMS, monkeypatch)
    q = next(p for p in tools[0].parameters if p.name == "q")
    assert q.required is True


def test_optional_param_flagged(monkeypatch):
    tools = discover(SPEC_WITH_QUERY_PARAMS, monkeypatch)
    limit = next(p for p in tools[0].parameters if p.name == "limit")
    assert limit.required is False


# ---------------------------------------------------------------------------
# Type mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("json_type,expected", [
    ("string",  ParameterType.STRING),
    ("integer", ParameterType.INTEGER),
    ("number",  ParameterType.NUMBER),
    ("boolean", ParameterType.BOOLEAN),
    ("array",   ParameterType.ARRAY),
    ("object",  ParameterType.OBJECT),
])
def test_type_mapping(json_type, expected, monkeypatch):
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/t": {"get": {
                "operationId": "test_op",
                "parameters": [
                    {"name": "p", "in": "query", "required": True,
                     "schema": {"type": json_type}},
                ],
                "responses": {},
            }}
        },
    }
    tools = discover(spec, monkeypatch)
    assert tools[0].parameters[0].type == expected


# ---------------------------------------------------------------------------
# Path parameters
# ---------------------------------------------------------------------------

def test_path_param_extracted(monkeypatch):
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/users/{user_id}": {"get": {
                "operationId": "getUser",
                "parameters": [
                    {"name": "user_id", "in": "path", "required": True,
                     "schema": {"type": "integer"}},
                ],
                "responses": {},
            }}
        },
    }
    tools = discover(spec, monkeypatch)
    names = [p.name for p in tools[0].parameters]
    assert "user_id" in names


# ---------------------------------------------------------------------------
# Enum values
# ---------------------------------------------------------------------------

def test_enum_values_extracted(monkeypatch):
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/filter": {"get": {
                "operationId": "filterItems",
                "parameters": [
                    {"name": "status", "in": "query", "required": False,
                     "schema": {"type": "string", "enum": ["active", "inactive", "pending"]}},
                ],
                "responses": {},
            }}
        },
    }
    tools = discover(spec, monkeypatch)
    p = tools[0].parameters[0]
    assert p.enum_values == ["active", "inactive", "pending"]


# ---------------------------------------------------------------------------
# Spec vide
# ---------------------------------------------------------------------------

def test_empty_paths_returns_no_tools(monkeypatch):
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {},
    }
    tools = discover(spec, monkeypatch)
    assert tools == []


# ---------------------------------------------------------------------------
# Several endpoints / methods
# ---------------------------------------------------------------------------

def test_multiple_endpoints(monkeypatch):
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/users": {
                "get":  {"operationId": "listUsers",  "parameters": [], "responses": {}},
                "post": {"operationId": "createUser", "parameters": [], "responses": {}},
            },
            "/users/{id}": {
                "get":    {"operationId": "getUser",    "parameters": [], "responses": {}},
                "delete": {"operationId": "deleteUser", "parameters": [], "responses": {}},
            },
        },
    }
    tools = discover(spec, monkeypatch)
    assert len(tools) == 4
    names = {t.name for t in tools}
    assert "list_users" in names
    assert "create_user" in names


# ---------------------------------------------------------------------------
# Regression 2026-09-23: form-urlencoded/multipart/header/query requestBody
# ---------------------------------------------------------------------------

def _spec_with_request_body(media_type: str) -> dict:
    return {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/pets/{id}": {
                "post": {
                    "operationId": "updatePetWithForm",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True,
                         "schema": {"type": "integer"}},
                    ],
                    "requestBody": {
                        "content": {
                            media_type: {
                                "schema": {
                                    "type": "object",
                                    "properties": {"name": {"type": "string"}},
                                },
                            },
                        },
                    },
                    "responses": {},
                },
            },
        },
    }


def test_form_urlencoded_body_gets_formdata_param_in(monkeypatch):
    """Regression: application/x-www-form-urlencoded must be sent with data=, not json=, so it is
    classified param_in="formData" like multipart/form-data."""
    tools = discover(_spec_with_request_body("application/x-www-form-urlencoded"), monkeypatch)
    name_param = next(p for p in tools[0].parameters if p.name == "name")
    assert name_param.param_in == "formData"


def test_multipart_body_still_gets_formdata_param_in(monkeypatch):
    tools = discover(_spec_with_request_body("multipart/form-data"), monkeypatch)
    name_param = next(p for p in tools[0].parameters if p.name == "name")
    assert name_param.param_in == "formData"


def test_plain_json_body_still_gets_body_param_in(monkeypatch):
    tools = discover(_spec_with_request_body("application/json"), monkeypatch)
    name_param = next(p for p in tools[0].parameters if p.name == "name")
    assert name_param.param_in == "body"


def test_header_param_in_extracted(monkeypatch):
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/pets/{id}": {
                "delete": {
                    "operationId": "deletePet",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True,
                         "schema": {"type": "integer"}},
                        {"name": "api_key", "in": "header", "required": False,
                         "schema": {"type": "string"}},
                    ],
                    "responses": {},
                },
            },
        },
    }
    tools = discover(spec, monkeypatch)
    api_key = next(p for p in tools[0].parameters if p.name == "api_key")
    assert api_key.param_in == "header"


def test_query_param_in_extracted_on_post(monkeypatch):
    """Regression: a query parameter on a POST method must stay classified "query" (the bug was in
    the template, which ignored query_params outside GET/DELETE/HEAD)."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/pets/{id}": {
                "post": {
                    "operationId": "updatePetWithForm",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True,
                         "schema": {"type": "integer"}},
                        {"name": "status", "in": "query", "required": False,
                         "schema": {"type": "string"}},
                    ],
                    "responses": {},
                },
            },
        },
    }
    tools = discover(spec, monkeypatch)
    status_param = next(p for p in tools[0].parameters if p.name == "status")
    assert status_param.param_in == "query"
