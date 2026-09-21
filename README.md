# mcp-forge CLI

[![PyPI](https://img.shields.io/pypi/v/vulcai-mcp-forge-cli)](https://pypi.org/project/vulcai-mcp-forge-cli/)
[![Python](https://img.shields.io/pypi/pyversions/vulcai-mcp-forge-cli)](https://pypi.org/project/vulcai-mcp-forge-cli/)

**Generate MCP servers from your APIs, codebases and command-line tools, without having to learn the protocol first.**

Building an MCP server by hand means learning one more protocol, structuring tool schemas and handling transport and authentication. mcp-forge does that work for you: point it at a source, get a ready-to-run `server.py`, then score it with the built-in evaluator to see what still needs your attention.

> This repository hosts the documentation and changelog. Install the package from [PyPI](https://pypi.org/project/vulcai-mcp-forge-cli/).

<!-- Demo GIF: add it here as ![mcp-forge demo](docs/demo.gif) -->

## Quick start

```bash
pip install vulcai-mcp-forge-cli
mcp-forge set-license mfg_live_...      # free during the public beta, see "Access" below
mcp-forge run https://petstore3.swagger.io/api/v3/openapi.json
```

The generated server is written to `../mcp-forge-output/<server_name>/` by default.

**Requirements:** Python 3.11+, [Node.js 18+](https://nodejs.org) and [uv](https://docs.astral.sh/uv/) (used to run generated servers).

## Supported sources

| Source | Auto-detected when | Example |
|---|---|---|
| OpenAPI / Swagger | URL or file ending in `.json`, `.yaml`, `.yml` | `mcp-forge run https://api.example.com/openapi.json` |
| GraphQL | URL contains `graphql` | `mcp-forge run https://api.example.com/graphql` |
| Codebase | Local directory | `mcp-forge run ./my-project` |
| CLI application | Command name | `mcp-forge run git` |
| Website | `http(s)` URL without a spec extension | `mcp-forge run https://docs.example.com` |

**23 languages for codebase analysis**, including legacy ones: Python, JavaScript, TypeScript, Go, Rust, Java, C/C++, C#, PHP, Ruby, Kotlin, Swift, Scala, Dart, Elixir, R, **Fortran**, Bash, PowerShell, Groovy, Julia, Lua and **COBOL**.

## Automatic quality evaluation

A generated server is never perfect for every configuration, so mcp-forge evaluates its own output. Each server is scored from 0 to 10 on six criteria, and servers scoring below 6/10 are automatically refined before delivery.

| Criterion | What is checked |
|---|---|
| Code structure | Readability, organisation, FastMCP idioms |
| Endpoint coverage | All tools present and correctly mapped |
| Auth & security | Environment variables, headers, no hardcoded secrets |
| Description quality | Docstrings, tool names, argument documentation |
| Spec fidelity | Types, body vs query parameters, path parameters |
| Robustness | Timeout handling, error handling, default values |

Run the evaluator on any server and save the report:

```bash
mcp-forge evaluate output/my_server/server.py --save report.json
```

<!-- Screenshot: add a real evaluator report here as ![evaluator report](docs/evaluator-report.png) -->

You can also check that a server starts and speaks MCP correctly with `mcp-forge smoke-test` (no startup needed) and `mcp-forge functional-test` (starts the server and runs a real handshake).

## Use the generated server

Every generated server exposes OAuth 2.0 (Authorization Code + PKCE), rate limiting, multi-tenant token isolation and SSE transport. It works with Claude Desktop, Claude Code, Cursor, VS Code, Windsurf and any MCP client. For example, in Claude Desktop:

```json
{
  "mcpServers": {
    "my_api": {
      "command": "uv",
      "args": ["run", "--with", "mcp", "mcp", "run", "server.py"],
      "cwd": "/path/to/mcp-forge-output/my_api"
    }
  }
}
```

Configuration for the other clients is in the [full CLI documentation on PyPI](https://pypi.org/project/vulcai-mcp-forge-cli/).

## What leaves your machine

Source analysis runs locally. To enrich and generate the server, the CLI sends the Vulcai API a sanitized description of what it discovered: operation names, parameters, descriptions and, for codebases, relative file and function names. Request headers, credentials and absolute paths are excluded from that payload. See the [Trust & Security page](https://mcp-forge.vulcai.io/trust) for data retention, model access and subprocessors.

## Limitations

- Generated servers usually need some adjustments for your own configuration. The evaluator report tells you where to look.
- JavaScript-heavy sites and single-page apps need the web extra: `pip install "vulcai-mcp-forge-cli[web]"` then `playwright install chromium`.
- GraphQL generation needs introspection to be enabled on the endpoint.
- If a generation returns 0 tools, see the [troubleshooting guide](https://mcp-forge.vulcai.io/docs/troubleshooting/no-tools).

## Access

mcp-forge is in **free public beta**. Create an account at [mcp-forge.vulcai.io/register](https://mcp-forge.vulcai.io/register) to get your license key, then register it once with `mcp-forge set-license`.

## Using mcp-forge from an AI agent

Agents such as Claude or Cursor can also generate servers directly, by passing only a URL, through the public MCP server. See [MCP-FORGE-MCP-SERVEUR](https://github.com/vulcai-io/MCP-FORGE-MCP-SERVEUR). For local codebases and non-public sources, use this CLI.

## Links

- [Full CLI documentation and options (PyPI)](https://pypi.org/project/vulcai-mcp-forge-cli/)
- [Homepage](https://mcp-forge.vulcai.io)
- [Changelog](CHANGELOG.md)
- [Trust & Security](https://mcp-forge.vulcai.io/trust)
- [Troubleshooting](https://mcp-forge.vulcai.io/docs/troubleshooting/no-tools)
- [MCP server repository](https://github.com/vulcai-io/MCP-FORGE-MCP-SERVEUR)

## License

This repository contains documentation only. The CLI package is published on PyPI under the MIT license, as stated in its package metadata.