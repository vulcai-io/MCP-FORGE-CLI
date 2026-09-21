# Changelog

All notable changes to the `vulcai-mcp-forge-cli` package
([PyPI](https://pypi.org/project/vulcai-mcp-forge-cli/)) are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Changes to the public MCP server are tracked in the
[MCP-FORGE-MCP-SERVEUR repository](https://github.com/vulcai-io/MCP-FORGE-MCP-SERVEUR/blob/main/CHANGELOG.md).

---

## [0.2.3] - 2026-07-20

### Documentation

- "How it compares" section added to the README / PyPI page, comparing mcp-forge
  with FastMCP, Smithery and openapi-mcp-generator.

## [0.2.2] - 2026-07-20

### Changed

- The default output directory is now derived deterministically from the URL
  hostname, which prevents collisions when generating from several endpoints in
  the same session.

## [0.2.1] - 2026-07-07

### Added

- `--lang` option: `mcp-forge run --lang fr` writes the comments of the generated
  server in French. The default is English (`--lang en`).
- Test coverage for the COBOL, Fortran, Java and C++ parsers (85 new tests, 363
  passing in total).

### Changed

- Generated `requirements.txt` files now use compatible-release pins (`~=`)
  instead of exact pins (`==`), so generated servers receive patch-level updates.
- Seven generated-server templates (CLI, codebase, GraphQL, website) were saved
  with a UTF-8 BOM, which could corrupt files in some editors. They are now clean
  UTF-8.

### Documentation

- The six quality-scoring criteria (structure, coverage, auth, docs, fidelity,
  robustness) are described in the README / PyPI page.

## [0.2.0] - 2026-07-07

**Breaking release.** CLI `0.1.x` is not compatible with the `0.2.0` backend.
Upgrade with `pip install -U vulcai-mcp-forge-cli`.

### Added

- Quality score in every generation: `eval_score` (0-10) and a per-criterion report.
- Generated bundle delivered through an authenticated download URL, with a preview
  of the first generated tools.

### Changed

- A generation that extracts zero tools is now reported as a failure with an
  actionable hint, instead of a silent success with 0 tools.

### Security

- Generated OAuth servers now validate `redirect_uri` against an allow-list set with
  the `OAUTH_ALLOWED_REDIRECT_HOSTS` environment variable. Without it, only
  `localhost` and `127.0.0.1` are accepted, and any other host is rejected with
  HTTP 400. This closes an open-redirect issue flagged by the built-in evaluator.

## [0.1.x] - 2026-05

Initial public releases, 0.1.0 to 0.1.25 (published between 2026-05-04 and
2026-05-21): parsers, template generation and CLI foundations.

[0.2.3]: https://pypi.org/project/vulcai-mcp-forge-cli/0.2.3/
[0.2.2]: https://pypi.org/project/vulcai-mcp-forge-cli/0.2.2/
[0.2.1]: https://pypi.org/project/vulcai-mcp-forge-cli/0.2.1/
[0.2.0]: https://pypi.org/project/vulcai-mcp-forge-cli/0.2.0/
