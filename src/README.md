# Source mirror

This directory mirrors the public parts of the `vulcai-mcp-forge-cli`
package (CLI, parsing, discovery) as published on PyPI.

Two engines are intentionally closed-source and excluded from this
mirror: `mcp_forge/enrichment/` (LLM-based description enrichment) and
`mcp_forge/generation/` (code generation). They run server-side via
Vulcai's API, not on your machine.

Install the published package:

```bash
pip install vulcai-mcp-forge-cli
```
