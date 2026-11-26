"""
Unit tests: GraphQLDiscovery (discovery/graphql.py).

Regression 2026-09-30: `_detect_auth` used `re.compile(...)` without `import re` at the top of
the file: a guaranteed NameError on EVERY call to GraphQLDiscovery.discover() (the HTTP probe is in
a try/except that swallows its own errors, but the computation of `has_auth_mutation` right after
runs unconditionally). Never caught by the existing suite, because another test fully mocked
GraphQLDiscovery: no test ran the real code of discovery/graphql.py. Confirmed by reproducing the
real call against https://countries.trevorblades.com/graphql (the endpoint that crashed) after
the fix.
"""
import httpx
import pytest

from mcp_forge.discovery.graphql import GraphQLDiscovery
from mcp_forge.models import DiscoveredTool, ForgeConfig, ForgeMode, NameStyle, SourceType


def _post_via_fetch(monkeypatch, fake) -> None:
    """GraphQL discovery goes through download.fetch (shared size and time limits, 2026-11-18):
    `fake(url, json=..., headers=...)` returns an httpx.Response, like httpx.post."""
    from mcp_forge.discovery import download

    def fetch(url, *, max_bytes, deadline_s, headers=None, method="GET", json=None, url_guard=None):
        response = fake(url, json=json, headers=headers)
        return download.Downloaded(response.status_code, response.text, url)

    monkeypatch.setattr(download, "fetch", fetch)


def make_config(endpoint: str = "https://fake.api/graphql") -> ForgeConfig:
    return ForgeConfig(
        source=endpoint,
        mode=ForgeMode.AUTO,
        output_dir="./output",
        source_type=SourceType.GRAPHQL,
        name_style=NameStyle.SHORT,
    )


def _tool(name: str, tags: list[str]) -> DiscoveredTool:
    return DiscoveredTool(name=name, description="", tags=tags)


def test_detect_auth_no_probe_no_mutation_returns_empty(monkeypatch):
    """Nominal case: the HTTP probe fails silently (network cut in the test), no auth mutation:
    must not raise NameError."""
    disc = GraphQLDiscovery(make_config())
    _post_via_fetch(monkeypatch, lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("no network")))
    tools = [_tool("get_country", ["query"]), _tool("list_continents", ["query"])]
    assert disc._detect_auth(tools) == []


def test_detect_auth_login_mutation_alone_is_not_auth(monkeypatch):
    """2026-11-17: a login mutation is no longer enough to assume a Bearer token (a public
    endpoint with a login mutation was taken for a protected one, a false case of the benchmark).
    Authentication comes from the headers given or from a 401/403."""
    disc = GraphQLDiscovery(make_config())
    _post_via_fetch(monkeypatch, lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("no network")))
    tools = [_tool("login", ["mutation"]), _tool("get_country", ["query"])]
    assert disc._detect_auth(tools) == []


def test_detect_auth_probe_401_returns_bearer(monkeypatch):
    def _post(*a, **k):
        return httpx.Response(401, request=httpx.Request("POST", "https://fake.api/graphql"))
    _post_via_fetch(monkeypatch, _post)
    disc = GraphQLDiscovery(make_config())
    schemes = disc._detect_auth([])
    assert len(schemes) == 1
    assert schemes[0].type.value == "bearer"


def test_detect_auth_no_auth_signal_returns_empty(monkeypatch):
    def _post(*a, **k):
        return httpx.Response(200, json={"data": {"__typename": "Query"}}, request=httpx.Request("POST", "https://fake.api/graphql"))
    _post_via_fetch(monkeypatch, _post)
    disc = GraphQLDiscovery(make_config())
    tools = [_tool("get_country", ["query"]), _tool("create_review", ["mutation"])]
    assert disc._detect_auth(tools) == []


@pytest.mark.network  # real public endpoint: excluded with -m "not network"
def test_full_discover_against_real_public_endpoint():
    """End-to-end reproduction of the incident: discover() on a real public GraphQL endpoint,
    without mocks: exactly what crashed with NameError: name 're' is not defined."""
    disc = GraphQLDiscovery(make_config("https://countries.trevorblades.com/graphql"))
    try:
        result = disc.discover()
    except httpx.HTTPError:
        pytest.skip("endpoint public injoignable depuis cet environnement de test")
        return
    assert len(result.tools) > 0


# ---------------------------------------------------------------------------
# Regression 2026-10-01, found in EVERY GraphQL evaluation report of the test
# batch: the template always generated `{ __typename }` as the selection
# set, whatever the real return type. Every tool therefore returned
# only the name of the GraphQL type, never useful data.
# ---------------------------------------------------------------------------

_SCHEMA_SIMPLE = {
    "Query": {"kind": "OBJECT", "name": "Query", "fields": []},
    "Continent": {
        "kind": "OBJECT",
        "name": "Continent",
        "fields": [
            {"name": "code", "type": {"kind": "SCALAR", "name": "String"}},
            {"name": "name", "type": {"kind": "SCALAR", "name": "String"}},
        ],
    },
}

_SCHEMA_NESTED = {
    **_SCHEMA_SIMPLE,
    "Country": {
        "kind": "OBJECT",
        "name": "Country",
        "fields": [
            {"name": "code", "type": {"kind": "SCALAR", "name": "String"}},
            {"name": "continent", "type": {"kind": "OBJECT", "name": "Continent"}},
        ],
    },
}

_SCHEMA_WITH_ARG_FIELD = {
    "Query": {"kind": "OBJECT", "name": "Query", "fields": []},
    "Country": {
        "kind": "OBJECT",
        "name": "Country",
        "fields": [
            {"name": "code", "type": {"kind": "SCALAR", "name": "String"}},
            {
                "name": "translatedName",
                "type": {"kind": "SCALAR", "name": "String"},
                "args": [{"name": "lang", "type": {"kind": "SCALAR", "name": "String"}}],
            },
        ],
    },
}


def test_selection_set_selects_real_scalar_fields_not_just_typename():
    disc = GraphQLDiscovery(make_config())
    selection = disc._build_selection_set("Continent", _SCHEMA_SIMPLE)
    assert selection == "code name"


def test_selection_set_recurses_one_level_into_object_subfields():
    disc = GraphQLDiscovery(make_config())
    selection = disc._build_selection_set("Country", _SCHEMA_NESTED)
    assert selection == "code continent { code name }"


def test_selection_set_is_empty_for_scalar_type():
    """2026-11-17: no selection on a scalar. Before, "__typename", which the template put
    between braces (`hello { __typename }`, refused by GraphQL)."""
    disc = GraphQLDiscovery(make_config())
    assert disc._build_selection_set("String", _SCHEMA_SIMPLE) == ""


def test_selection_set_falls_back_to_typename_for_unknown_type():
    disc = GraphQLDiscovery(make_config())
    assert disc._build_selection_set("Nonexistent", _SCHEMA_SIMPLE) == "__typename"


def test_selection_set_skips_fields_that_require_arguments():
    """A field that itself needs arguments cannot be requested without them: leave it out rather
    than produce an invalid query."""
    disc = GraphQLDiscovery(make_config())
    selection = disc._build_selection_set("Country", _SCHEMA_WITH_ARG_FIELD)
    assert selection == "code"
    assert "translatedName" not in selection
