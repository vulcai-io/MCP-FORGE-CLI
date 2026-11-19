# mcp-forge and the OWASP MCP Top 10

Status on 2026-11-19, CLI 0.4.4. Reference: [OWASP MCP Top 10](https://owasp.org/www-project-mcp-top-10/),
2025 edition, still in beta ("Phase 3 – Beta Release and Pilot Testing"): titles may change.

Two columns: the **generator** (what generated MCP servers contain) and the **evaluator** (what it
detects when it scores a server).

- **Covered**: protection in place and tested.
- **Partial**: protection in place but incomplete; the limit is stated.
- **Missing**: nothing yet.
- **Out of scope**: not something a server generator can address.

Every "Covered" and "Partial" entry is backed by automated tests. Most of them live in our private
repository (generator and evaluator); the parser tests are public, in [`tests/`](tests/) of this
repository. The evaluator's code is public too, in [`src/mcp_forge/`](src/mcp_forge/). The
evaluator entries are also checked against a benchmark of servers with planted bugs.

The evaluator relies in part on an LLM: its results vary slightly from one run to the next. The
benchmark figures, and how much they vary, are on the public roadmap:
https://mcp-forge.vulcai.io/roadmap.

| OWASP risk | Generator | Evaluator |
|---|---|---|
| **MCP01 — Token Mismanagement & Secret Exposure** | **Covered.** API keys are read from environment variables, never written into the code. Sensitive fields in API responses are masked (`[redacted]`). The tool-call log never records arguments or secrets. Generated prompts that ask for a secret are rejected (pattern-based). | **Partial.** The evaluator's security criterion and a planted-bug case (secret written to logs). No mechanical check yet. |
| **MCP02 — Privilege Escalation via Scope Creep** | **Partial.** Accurate tool annotations (`readOnlyHint`, `destructiveHint`). `MCP_READ_ONLY=1` exposes only read-only tools. Deletions ask the user for confirmation. Limits: the API token's scope is the one you provide (mcp-forge does not narrow it). On a remote server, the client LLM can set `confirm=true` itself, so only `MCP_READ_ONLY=1` is a guarantee. | **Covered.** A wrong annotation (read-only on a write, non-destructive on a deletion) is a major bug, found by a mechanical check. Two planted-bug cases. |
| **MCP03 — Tool Poisoning** | **Partial.** Invisible characters are removed from text the client LLM reads. Generated prompts are validated and poisoning patterns rejected. MCP tool names come from the source, never from an LLM. Limit: a poisoned description written in the API's own spec is kept as is (it is the source); the evaluator flags it. | **Partial.** Pattern-based detection (hidden instructions, role changes, sensitive files, HTML comments, invisible characters). One planted-bug case. Limit: patterns, not understanding; a new wording can get through. |
| **MCP04 — Software Supply Chain Attacks & Dependency Tampering** | **Partial.** Dependency versions of generated servers are constrained to compatible versions (`~=`). mcp-forge's own dependencies are locked and audited in CI; the hosted MCP server's image runs exactly the locked versions, checked in CI. Missing: exact pins with hashes in the generated `requirements.txt`, and an automatic audit of generated servers. | **Missing.** The evaluator does not look at a server's dependencies. |
| **MCP05 — Command Injection & Execution** | **Covered.** No `shell=True`; programs resolved to a full path; values starting with "-" refused in CLI tools; arguments written as safe literals in codebase drivers (Ruby, PowerShell, Fortran…). | **Partial.** The evaluator's LLM only. Four planted-bug cases (CLI option injection, PowerShell literals, path traversal, SSRF). |
| **MCP06 — Prompt Injection via Contextual Payloads** | **Partial.** API responses (OpenAPI, GraphQL) and website text are returned between untrusted-content markers, with a size limit. Limit: output of CLI tools and codebases is returned without markers. A marker reduces the risk; it does not remove it. | **Partial.** Mechanical check for raw API responses and unmarked external content. Two planted-bug cases. Does not cover CLI and codebase output. |
| **MCP07 — Insufficient Authentication & Authorization** | **Covered.** HTTP servers require a token (`MCP_SERVER_TOKEN`), compared in constant time. The hosted server uses OAuth 2.1 with PKCE and an allowlist of redirect hosts, and rate-limited sign-in; signed tokens with refresh and Client ID Metadata Documents are in progress. | **Partial.** The evaluator's LLM only. One planted-bug case (four authentication flaws). |
| **MCP08 — Lack of Audit and Telemetry** | **Partial.** One log line per tool call (name, outcome, duration; no arguments or secrets), can be turned off (`MCP_TOOL_LOG`). Limit: written to standard error, not a tamper-proof audit trail. | **Missing.** The evaluator does not check that the log is there. |
| **MCP09 — Shadow MCP Servers** | **Out of scope.** Governance of deployments inside your organisation. mcp-forge only contributes through mandatory authentication over HTTP (MCP07). | **Out of scope.** |
| **MCP10 — Context Injection & Over-Sharing** | **Partial.** Sensitive fields masked in responses, size limited (`MCP_MAX_RESPONSE_CHARS`). No optional parameter is sent unless the caller set it. Limit: masking relies on a list of field names. | **Partial.** An API response returned without filtering is a bug (mechanical check); the rest by the evaluator's LLM. |

## Recent fixes

- **CLI 0.4.4:** when the URL given is a Swagger UI or Redoc page, or a site whose OpenAPI spec the
  website discovery finds, the server now matches the one generated from the spec's URL. CLI 0.4.3
  generated a website server instead, without the masking of sensitive fields (MCP01, MCP10).
  Regenerate such servers with 0.4.4.
- **Hosted MCP server:** its image now runs exactly the locked dependency versions, and CI checks
  them (MCP04).

## Known gaps (not scheduled yet)

1. MCP04: hashes in generated `requirements.txt` files and an audit of generated servers.
2. MCP06: untrusted-content markers on CLI and codebase output, and the matching evaluator check.
3. MCP01, MCP05, MCP07: mechanical evaluator checks (hard-coded or logged secrets, `shell=True`,
   HTTP server without a token), in addition to the LLM.
4. MCP08: the evaluator flags a server without a tool-call log.
