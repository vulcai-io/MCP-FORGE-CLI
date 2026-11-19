"""
2026-10-05, found while digging into why the evaluation score of a website source (Wikipedia)
capped at 7.2: `_extract_from_navigation` created ONE hard-coded tool per navigation link found
(`get_wiki_python_programming_language`, `get_wiki_file_upload_wizard`...), never a generic "fetch
any page under /wiki/<title>" tool. Two symptoms reported by the quality evaluator: no coverage of
an article not linked from the start page, and two near-duplicate tools (`File_upload_wizard` vs
`File_Upload_Wizard`) that differed only by case.

Root cause: no detection of templated URL patterns. Generic fix (not specific to Wikipedia): when
3 or more navigation links share the same path prefix (e.g. /wiki/Python, /wiki/Java, /wiki/Rust),
they are replaced by ONE parameterised tool (`/wiki/{slug}`) instead of N hard-coded tools. Below
the threshold, the previous behaviour is kept (single pages, no grouping).
"""
from __future__ import annotations

from mcp_forge.discovery.web import WebDiscovery
from mcp_forge.models import ForgeConfig, ForgeMode, SourceType


def _discovery() -> WebDiscovery:
    config = ForgeConfig(
        source="https://en.wikipedia.org/wiki/Python",
        mode=ForgeMode.AUTO,
        source_type=SourceType.WEBSITE,
    )
    return WebDiscovery(config)


def test_three_or_more_shared_prefix_links_collapse_into_one_templated_tool() -> None:
    raw_links = [
        ("/wiki/Python_(programming_language)", "Python"),
        ("/wiki/Java_(programming_language)", "Java"),
        ("/wiki/Rust_(programming_language)", "Rust"),
    ]
    endpoints = _discovery()._generalize_templated_links(raw_links)
    assert len(endpoints) == 1
    ep = endpoints[0]
    assert ep.path == "/wiki/{slug}"
    assert len(ep.params) == 1
    assert ep.params[0].name == "slug"
    assert ep.params[0].required is True


def test_case_insensitive_duplicate_does_not_create_a_second_tool() -> None:
    """The original regression mentioned two near-duplicate tools (`File_upload_wizard` vs
    `File_Upload_Wizard`, the same page up to case). Once the group is generalised into one
    parameterised tool, both variants must disappear into the same generic tool: never two
    separate tools for the same family of pages."""
    raw_links = [
        ("/wiki/Python", "Python"),
        ("/wiki/python", "python (variante de casse)"),
        ("/wiki/Java", "Java"),
        ("/wiki/Rust", "Rust"),
    ]
    endpoints = _discovery()._generalize_templated_links(raw_links)
    assert len(endpoints) == 1
    assert endpoints[0].path == "/wiki/{slug}"


def test_below_threshold_links_stay_as_individual_hardcoded_tools() -> None:
    """2 links sharing a prefix do not justify generalising: not enough evidence that it is a real
    parameterised collection rather than two pages that look alike by coincidence."""
    raw_links = [
        ("/wiki/Python", "Python"),
        ("/wiki/Java", "Java"),
    ]
    endpoints = _discovery()._generalize_templated_links(raw_links)
    assert len(endpoints) == 2
    assert {ep.path for ep in endpoints} == {"/wiki/Python", "/wiki/Java"}
    assert all(not ep.params for ep in endpoints)


def test_single_segment_links_never_grouped() -> None:
    """/about, /contact, /pricing have no meaningful common prefix (a single segment each): never
    grouped, even if there are many of them."""
    raw_links = [
        ("/about", "About"),
        ("/contact", "Contact"),
        ("/pricing", "Pricing"),
        ("/careers", "Careers"),
    ]
    endpoints = _discovery()._generalize_templated_links(raw_links)
    assert len(endpoints) == 4
    assert all(not ep.params for ep in endpoints)


def test_single_occurrence_link_generalized_when_it_matches_the_origin_page() -> None:
    """2026-10-05, found while checking stability (9 runs of the full batch): the website score
    varied from 7.4 to 8.2 depending on whether the evaluator judged two hard-coded tools "major"
    (`Special:WhatLinksHere/<page>`, `Special:RecentChangesLinked/<page>`). Each appears only ONCE
    (different families, below the threshold of 3), but both end with exactly the same segment as
    the start page itself: a strong signal that it is an action that applies to ANY page, not a
    fixed link."""
    raw_links = [
        ("/wiki/Special:WhatLinksHere/Python_(programming_language)", "What links here"),
        ("/wiki/Special:RecentChangesLinked/Python_(programming_language)", "Related changes"),
    ]
    endpoints = _discovery()._generalize_templated_links(raw_links, origin_last_segment="Python_(programming_language)")
    paths = {ep.path for ep in endpoints}
    assert paths == {
        "/wiki/Special:WhatLinksHere/{slug}",
        "/wiki/Special:RecentChangesLinked/{slug}",
    }
    assert all(ep.params and ep.params[0].name == "slug" for ep in endpoints)


def test_single_occurrence_link_not_generalized_without_origin_match() -> None:
    """Without a match with the start page, a single link stays hard-coded: no
    over-generalisation from a mere coincidence."""
    raw_links = [("/wiki/Special:WhatLinksHere/Java_(programming_language)", "What links here")]
    endpoints = _discovery()._generalize_templated_links(raw_links, origin_last_segment="Python_(programming_language)")
    assert len(endpoints) == 1
    assert endpoints[0].path == "/wiki/Special:WhatLinksHere/Java_(programming_language)"
    assert not endpoints[0].params


def test_discover_includes_a_dedicated_tool_for_the_starting_page(monkeypatch) -> None:
    """2026-10-05, reported by the quality evaluator: after the /wiki/<title> links were
    generalised into one parameterised tool, the START page (the one the user gave to mcp-forge)
    had no direct access any more: an LLM had to guess the right parameter of the generic tool
    instead of having a dedicated "this exact page" tool."""
    html = """
    <html><head><title>Python (programming language) - Wikipedia</title></head>
    <body>
        <nav>
            <a href="/wiki/Java_(programming_language)">Java</a>
            <a href="/wiki/Rust_(programming_language)">Rust</a>
            <a href="/wiki/Go_(programming_language)">Go</a>
        </nav>
        <p>content</p>
    </body></html>
    """
    config = ForgeConfig(
        source="https://en.wikipedia.org/wiki/Python_(programming_language)",
        mode=ForgeMode.AUTO,
        source_type=SourceType.WEBSITE,
    )
    wd = WebDiscovery(config)
    monkeypatch.setattr(wd, "_try_openapi_discovery", lambda: None)
    monkeypatch.setattr(wd, "_fetch_page", lambda url: (html, config.source, False))
    result = wd.discover()

    paths = {t.endpoint for t in result.tools}
    assert "/wiki/Python_(programming_language)" in paths
    assert "/wiki/{slug}" in paths


def test_unrelated_prefixes_do_not_merge_with_templated_group() -> None:
    """A site with both /wiki/<title> (templated) and a few pages outside the wiki (/about,
    /donate): only the /wiki/* group must be generalised, the rest keeps its hard-coded tool."""
    raw_links = [
        ("/wiki/Python", "Python"),
        ("/wiki/Java", "Java"),
        ("/wiki/Rust", "Rust"),
        ("/about", "About"),
        ("/donate", "Donate"),
    ]
    endpoints = _discovery()._generalize_templated_links(raw_links)
    paths = {ep.path for ep in endpoints}
    assert paths == {"/wiki/{slug}", "/about", "/donate"}
