# Contributing to mcp-forge

Thanks for your interest! Contributions are welcome on the **source parsers**. A parser reads
a source and turns it into a list of tools. The sources are:

- an OpenAPI spec or a GraphQL schema;
- a command-line tool or a website;
- a codebase: Python, Go, Java, COBOL, Fortran, Ruby and more.

## What is in this repository

`src/` mirrors the public part of the `vulcai-mcp-forge-cli` package, as published on PyPI:

- the CLI;
- discovery and parsing;
- validation;
- the evaluator.

Two engines are closed-source and not included: `mcp_forge/generation/` (code generation) and
`mcp_forge/enrichment/` (LLM descriptions). You don't need them: parser work is tested on its
own.

## Run the tests (a few seconds)

You need Python 3.11.5 or later. No API key, no license and no network access are needed.

```bash
git clone https://github.com/vulcai-io/MCP-FORGE-CLI.git
cd MCP-FORGE-CLI
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt          # Windows: .venv\Scripts\pip
.venv/bin/python -m pytest -m "not network" -q         # Windows: .venv\Scripts\python
```

`requirements-dev.txt` pins the same versions as the published package's lock file. The tests
run against the sources in `src/`, not against an installed `vulcai-mcp-forge-cli`.

During tests:

- network access is blocked;
- any variable that looks like a credential is removed from the environment (see
  `tests/conftest.py`).

A test that really needs the Internet must be marked `@pytest.mark.network`. The same tests run
on every push and pull request (`.github/workflows/contributor-checks.yml`, Python 3.11 and
3.12).

## Propose a parser or a fix

1. **Start from an issue** labelled **`parser`**, or open one first for a new parser or a larger
   change. Every issue gives:
   - the file to change;
   - the current behaviour, reproduced on a small sample;
   - the expected behaviour;
   - the tests to add.
2. **Follow the conventions:**
   - A parser returns `DiscoveredTool` objects. Their parameters have a `ParameterType`:
     `string`, `integer`, `number`, `boolean`, `array` or `object`.
   - A function that **cannot be called** from a tool argument is **left out**, not exposed.
     The parser counts it in `self.exclusions[<reason>]` (a `collections.Counter`); these
     counts are reported as coverage figures.
   - Put one test per behaviour in `tests/parsers/test_<language>_parser.py` (create it if it
     does not exist). Use `tmp_path` and small inline samples. Do not add third-party source
     trees.
3. **Run the tests** as above: all of them must pass with `pytest -m "not network"`.

The maintainers also run a parser benchmark on real corpora (thousands of OpenAPI specs, open
source repositories in 22 languages, GraphQL schemas, web pages). A change that lowers one of
its measured indicators is not merged as it is.

## Rules

- **No secrets.** Never commit an API key, a token, a `.env` file or a real credential, not even
  in a test. Use obviously fake values (`test-token`, `example.com`).
- **Tests with a witness.** A test for a fix must fail on the code before the fix. Check it:
  run the new test on the old code, see it fail, then on your change, see it pass. Say in the
  pull request that you did. A test that would pass either way proves nothing.
- **Small samples only.** Inline samples or tiny files under `tests/`. No generated servers, no
  large sample projects, no code under a licence that is not compatible with MIT.
- **One issue per pull request,** with its tests.

## Submitting a pull request

1. **Target branch:** open your pull request against the **`contributor`** branch, not `main`.
   The maintainers port accepted changes into the main code base and publish them in a release.
2. **Sign off every commit** (Developer Certificate of Origin, see
   <https://developercertificate.org/>):
   ```bash
   git commit -s -m "fix(go): keep names of grouped parameters"
   ```
   This adds a `Signed-off-by: Your Name <you@example.com>` line. It certifies that you wrote
   the change, or have the right to submit it under the MIT license of this repository. Pull
   requests with unsigned commits cannot be merged. The DCO check runs automatically.

## Reporting a security issue

Please do not open a public issue: write to **security@vulcai.io**.
