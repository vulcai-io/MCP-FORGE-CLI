# Changelog

All notable changes to the `vulcai-mcp-forge-cli` package
([PyPI](https://pypi.org/project/vulcai-mcp-forge-cli/)) are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Changes to the public MCP server are tracked in the
[MCP-FORGE-MCP-SERVEUR repository](https://github.com/vulcai-io/MCP-FORGE-MCP-SERVEUR/blob/main/CHANGELOG.md).

---

## [0.4.0] - 2026-10-27

**Upgrade required for codebases.** Generating from a local codebase now
needs CLI 0.4.0: the API refuses codebases sent by older versions (HTTP 426,
with a message asking you to upgrade) instead of returning a broken server.
No quota is consumed. Older versions keep working for the other sources; they
receive the server before its evaluation, without a score.

### Changed

- **Asynchronous evaluation.** The API returns the server as soon as it is
  generated, then evaluates it in the background.
  - `mcp-forge run` waits for the evaluation with a progress display, then
    writes the final version and prints the score. When the evaluation leads
    to a refinement, the final version is the refined server.
  - `--no-wait` stops at the provisional version and prints the generation id.
  - New command: `mcp-forge status <generation_id> [--output DIR]` fetches the
    final version later. With `--no-wait`, it only prints the current state.
- **Codebases are sent as an asynchronous job.** Large codebases are no longer
  cut off by the time limit of a single request: the CLI shows progress and
  waits up to 15 minutes.
- **Generated servers** use Streamable HTTP on `/mcp`, with MCP-conformant
  OAuth: tokens out of the query string and bound to the server (RFC 8707),
  authorization metadata (RFC 9728 / RFC 8414), Client ID Metadata Documents
  and Origin validation. Drivers are hardened against code, command and
  argument injection.
- **`mcp-forge evaluate`** is more deterministic:
  - an anchored scoring grid and a mandatory security checklist;
  - mechanical checks: compilation, undefined names, isolated import, and
    verification of each bug the model reports;
  - dynamic tests of the server's HTTP layer;
  - static analyzers (Bandit when it is installed, secrets written to logs,
    regular expressions at risk of ReDoS). Bandit is not a dependency of the
    CLI. Set `MCP_FORGE_STATIC_ANALYZERS=0` to switch the analyzers off.

### Fixed

- **Codebases generated through the API got a Python server.** The CLI did not
  send the codebase language, nor the language-specific details (Java package
  and source root, Fortran and Elixir modules, enclosing types, COBOL
  parameters...). It now sends the language, from the list of the 23 supported
  ones, with only the details that language needs. File paths stay relative to
  the codebase.
- **GraphQL tools generated through the API requested only `__typename`.** The
  field selection is now sent.
- **Java:**
  - methods are executed for real, through a small generated driver compiled
    with `javac`, instead of relying on a dispatcher you had to write; static
    and instance methods and array parameters are handled;
  - interface methods declared without `public` (implicitly public) were not
    discovered.
- **Websites:** links that apply an action to the current page (for example
  "what links here") are turned into one parameterized tool even when they
  appear only once, instead of a tool hardcoded to a single page.
- **Fortran:** parameter types, and generated servers no longer leave `.mod`
  files in the directory they were started from.
- **OpenAPI:** optional parameters you leave unset are no longer sent.
- **`mcp-forge test`** did not start MCP Inspector on Linux and macOS, and failed
  on Windows when `npx` resolved to its extensionless script. It now runs
  without a shell on every platform, says so when Node.js is missing, and uses
  a pinned MCP Inspector version (1.0.3).
- **The CLI installed mcp 2.x**, where `mcp.server.fastmcp` no longer exists:
  `smoke-test` and `functional-test` failed on every generated server. The CLI
  now requires `mcp>=1.27.2,<2`.
- **`mcp-forge test` and `functional-test` could not reach generated servers.**
  `python server.py` starts the HTTP server, while both talk stdio. They now
  serve the server's FastMCP object over stdio, and `mcp-forge test` runs it
  with the versions pinned in its `requirements.txt`. It no longer installs
  them into the CLI's own environment, and on Windows with a uv-managed Python
  it no longer passes `PYTHONHOME` to the server.
- **Client configuration** in the README uses the same verified command.
- The "No API key found, LLM enrichment disabled" warning is shown only for
  the local pipeline: with the API, enrichment runs on the server side.

### Security

- The CLI ignores entries of a downloaded server bundle that would be written
  outside the output folder.
- Generated servers pin fixed versions of `mcp`, Starlette and PyJWT, which
  close known vulnerabilities, including an unauthenticated denial of service
  on form bodies.

## [0.3.0] - 2026-10-05

Beta milestone: a quality pass across every generation path. Execution
support now covers the languages that codebase analysis discovers, and the
generation templates shared between languages were reworked.

| Source | Score before | Score after (0–10, evaluator of the time) |
|---|---|---|
| TypeScript, Swift, Dart, Kotlin, Go, Rust, Fortran, Scala, C#, Ruby, Elixir, PowerShell, JavaScript, Bash | unsupported or ≤ 7.8 | 8.2–8.5 |
| Website | 7.2 | 8.2 |
| COBOL | 3.5 (unsupported) | 8.4 (modern subprogram style) |
| CLI (`git`) | 7.8 | 8.4 |

These scores come from the evaluator shipped with 0.3.0. They are not
comparable with scores from the 0.4.0 evaluator, which uses a different,
stricter grid and mechanical checks.

### Added

- **Execution for compiled and scripting languages:** generated servers now
  call the discovered functions for real, through a driver compiled or run
  with the language's own toolchain (`rustc`, `gfortran`, `go run`,
  `dotnet run`, `scala-cli`, `kotlin`, `dart`, `npx tsx`, R, PowerShell,
  Bash...).
- **COBOL:** *modern, isolated* subprograms (`PROGRAM-ID` with an explicit
  `PROCEDURE DIVISION USING <inputs...> <output>.` clause) are executed end
  to end with GnuCOBOL. Legacy monolithic COBOL (a single `PROCEDURE DIVISION`
  of paragraphs sharing global `WORKING-STORAGE` state) is detected but returns
  an explicit error instead of a guessed result: isolating one paragraph's
  inputs and outputs from shared mutable state can't be done reliably without
  risking a silently wrong answer.
- **Websites:** families of similar links become one parameterized tool, the
  page you started from gets a dedicated tool, and GET forms no longer send
  empty optional fields.

### Fixed

- **CLI tools:** positional arguments were sometimes marked required even
  when the tool documents an argument-less usage form (`git log`, `git fetch`,
  `git branch`...).
- **Codebases:**
  - most non-Python languages were generated with the wrong interpreter;
  - generated servers defaulted to an absolute path from the machine that
    generated them;
  - two unrelated codebases with similar function names could share cached
    descriptions;
  - array parameters in C/C++, Java and other languages were typed by their
    element instead of as arrays;
  - functions that fill a C string buffer in place now return its content;
  - C/C++ projects could yield 0 tools.
- `mcp-forge run` could crash after a successful evaluation when the model
  returned an unexpected report shape.

## [0.2.6] to [0.2.20] - 2026-09-23 to 2026-09-30

Fixes released in quick succession during the first week of the public beta,
summarized by theme.

### Added

- **CLI tools:** positional arguments documented in a tool's usage synopsis
  (`git clone <repo> <dir>`, GNU-style `PATTERN` / `[FILE]...`) are now
  discovered, and many more options are detected in real `--help` outputs.

### Fixed

- **Request encoding in generated servers:**
  - query parameters were dropped on POST, PUT and PATCH;
  - `application/x-www-form-urlencoded` bodies were sent as JSON;
  - required parameters were checked only after the URL was built.

  The root cause was that the payload sent to the API did not say where each
  parameter goes (query, header, path or body); it now does.
- **Evaluation and refinement:**
  - `mcp-forge evaluate` silently truncated servers at 12,000 characters;
  - the automatic refinement could regress code that was already correct;
  - the evaluation report was missing for GraphQL, CLI and website sources.
- **Reliability:**
  - `mcp-forge run` gave up after 60 seconds while the API was still working;
  - GraphQL discovery crashed on every run;
  - validation failed on any server containing non-ASCII text.
- The default output directory was one level above the working directory.

## [0.2.5] - 2026-09-22

### Added

- MIT licence shipped with the package and declared in its metadata, so PyPI shows
  it in the project sidebar. A `LICENSE` file is also available in this repository.

### Documentation

- The README licence link is now absolute, so it works on the PyPI page.

## [0.2.4] - 2026-09-21

### Added

- `mcp-forge evaluate` now automatically selects the best Groq model your
  `GROQ_API_KEY` can use, since Groq retires models over time. Set `GROQ_MODEL`
  to force a specific model.

### Fixed

- `mcp-forge --version` always printed `0.1.0`. It now reports the installed version.
- Error messages for quota and missing licence pointed to a domain we do not own.
  They now point to https://mcp-forge.vulcai.io and contact@vulcai.io.

### Changed

- The "Changelog" link on the PyPI page now points to this repository.

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

[0.2.5]: https://pypi.org/project/vulcai-mcp-forge-cli/0.2.5/
[0.2.4]: https://pypi.org/project/vulcai-mcp-forge-cli/0.2.4/
[0.2.3]: https://pypi.org/project/vulcai-mcp-forge-cli/0.2.3/
[0.2.2]: https://pypi.org/project/vulcai-mcp-forge-cli/0.2.2/
[0.2.1]: https://pypi.org/project/vulcai-mcp-forge-cli/0.2.1/
[0.2.0]: https://pypi.org/project/vulcai-mcp-forge-cli/0.2.0/
