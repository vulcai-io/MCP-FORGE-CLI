# OWASP MCP Top 10 and mcp-forge

Status on 2026-11-19, CLI 0.4.4. Reference: [OWASP MCP Top 10](https://owasp.org/www-project-mcp-top-10/),
2025 version, in beta ("Phase 3 – Beta Release and Pilot Testing", a living document): the
titles may still change.

Two columns. The **generator** column covers what the generated servers contain. The
**evaluator** column covers what `mcp-forge evaluate` detects in a server. The states are:

- **Covered**: a protection is in place and tested.
- **Partial**: a protection is in place but incomplete; the limit is written down.
- **Missing**: nothing yet.
- **Out of scope**: not something a server generator can address.

The evaluator is public: its code is in [`src/mcp_forge/`](src/mcp_forge/). The generator is
closed-source. Its protections are checked by automated tests in the private repository, and
the table states each limit.

| OWASP risk | Generator | Evaluator |
|---|---|---|
| **MCP01 — Token Mismanagement & Secret Exposure** | **Covered.** Keys go through environment variables, never into the code. Sensitive fields in API responses are masked (`[redacted]`). The tool call log writes neither arguments nor secrets. A prompt cannot ask for a secret. | **Partial.** No mechanical check yet: the LLM evaluator's security criterion, and a planted-bug case (secret written to the log) in the benchmark. |
| **MCP02 — Privilege Escalation via Scope Creep** | **Partial.** Exact annotations (`readOnlyHint`, `destructiveHint`). `MCP_READ_ONLY=1` exposes only the read-only tools. Deletions ask the user to confirm. Limits: the API token's scope is the one the user provides (mcp-forge does not narrow it). In remote mode the client's LLM can set `confirm=true` itself, so only `MCP_READ_ONLY=1` is a guarantee. | **Covered.** A wrong annotation is a major bug, found by a mechanical check ([`eval_annotations.py`](src/mcp_forge/eval_annotations.py)): read-only on a write, or a non-destructive deletion. Benchmark cases for both. |
| **MCP03 — Tool Poisoning** | **Partial.** Invisible characters are removed from the texts the client's LLM reads. Prompts are validated and poisoning patterns refused. MCP tool names come from the source, never from the LLM. Limit: a poisoned description written in the API's own spec is kept as it is, since that is the source; the evaluator flags it. | **Partial.** Detection by patterns: hidden instructions, role changes, sensitive files, HTML comments, invisible characters ([`eval_annotations.py`](src/mcp_forge/eval_annotations.py)). Limit: patterns, not understanding; a new wording gets through. |
| **MCP04 — Software Supply Chain Attacks & Dependency Tampering** | **Partial.** Dependency versions in generated servers are pinned to a compatible range (`~=`). The project's dependencies are locked, and the lockfile is checked in CI. The hosted MCP server's image runs exactly the locked versions, checked in CI. Missing: hashes in the generated `requirements.txt`, and an automated audit of the generated servers. | **Missing.** The evaluator does not look at a server's dependencies. |
| **MCP05 — Command Injection & Execution** | **Covered.** CLI tools never use `shell=True`. The program is resolved to a full path. A value starting with "-" is refused. Codebase drivers (Ruby, PowerShell, Fortran…) write arguments as safe literals. | **Partial.** The LLM evaluator only. Benchmark cases: CLI option injection, PowerShell literals, path traversal, SSRF. |
| **MCP06 — Prompt Injection via Contextual Payloads** | **Partial.** API responses (OpenAPI, GraphQL) and website text are returned between markers that flag them as untrusted content, with a size limit. Limits: outputs of CLI tools and codebases are returned without a marker. A marker reduces the risk; it does not prevent it. | **Partial.** Mechanical checks for raw API responses and unmarked external content ([`eval_annotations.py`](src/mcp_forge/eval_annotations.py)). They do not cover CLI and codebase outputs. |
| **MCP07 — Insufficient Authentication & Authorization** | **Covered.** A generated server over HTTP requires a token (`MCP_SERVER_TOKEN`), compared in constant time. The hosted server uses OAuth with PKCE and rate limits. | **Partial.** The LLM evaluator only. A benchmark case covers authentication flaws. |
| **MCP08 — Lack of Audit and Telemetry** | **Partial.** One log line per tool call (name, result, duration; no arguments or secrets), which can be turned off (`MCP_TOOL_LOG`). Limit: it goes to standard error; there is no tamper-proof audit trail. | **Missing.** The evaluator does not check that the log is there. |
| **MCP09 — Shadow MCP Servers** | **Out of scope.** This is governance of deployments in the user's organisation. mcp-forge only contributes through the authentication required over HTTP (MCP07). | **Out of scope.** |
| **MCP10 — Context Injection & Over-Sharing** | **Partial.** Sensitive fields are masked in responses, whose size is limited (`MCP_MAX_RESPONSE_CHARS`). No optional parameter is sent unless it was set. Limit: masking relies on a list of field names. | **Partial.** An API response returned without filtering is a bug ([`eval_annotations.py`](src/mcp_forge/eval_annotations.py)); the rest is left to the LLM evaluator. |

## Fixed since the first version of this table (2026-11-12)

- **CLI 0.4.4:** when the URL given is a Swagger UI or Redoc page, or a site whose OpenAPI spec the
  website discovery finds, the server now matches the one generated from the spec's URL. CLI 0.4.3
  generated a website server instead, without the masking of sensitive fields (MCP01, MCP10).
  Regenerate such servers with 0.4.4.
- **Hosted MCP server:** its image now runs exactly the locked dependency versions, and CI checks
  them (MCP04).

## Next steps (proposed, not scheduled)

1. MCP04: hashes in the generated `requirements.txt`, and a dependency audit of generated servers.
2. MCP06: untrusted-content markers on CLI and codebase outputs, and the matching evaluator check.
3. MCP01, MCP05, MCP07: mechanical evaluator checks, in addition to the LLM: hard-coded or logged
   secret, `shell=True`, HTTP server without a token.
4. MCP08: the evaluator flags a server without a tool call log.
