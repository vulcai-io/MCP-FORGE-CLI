# Security policy

## Reporting a vulnerability

Please report security vulnerabilities by email to **security@vulcai.io**.
Do not open a public issue, pull request or discussion for a vulnerability.

Please include:
- the affected component: the CLI (with `mcp-forge --version`), a generated server
  (with the command used to generate it), the hosted API or the hosted MCP server;
- the steps to reproduce, and a proof of concept if you have one;
- the impact you observed or expect;
- whether you want to be credited, and under which name.

## What to expect

- A first response within **3 business days**.
- An assessment and a severity rating within 10 business days.
- We aim to fix critical and high-severity issues within 30 days, and the others within 90 days.
  We keep you informed until the fix is released.
- Coordinated disclosure: please allow us up to 90 days before publishing
  details. With your agreement, we credit you in the release notes.

## Scope

In scope: the mcp-forge CLI (`vulcai-mcp-forge-cli` on PyPI), the MCP servers it
generates, the hosted website and API (mcp-forge.vulcai.io and
api.mcp-forge.vulcai.io) and the hosted MCP server (mcp.mcp-forge.vulcai.io).

Out of scope: volumetric denial of service, social engineering, physical
attacks, reports from automated scanners without a demonstrated impact, and
vulnerabilities in third-party services we rely on (please report those to their
vendors).

## Safe harbour

We will not take legal action against good-faith research that follows this
policy. Do not access or modify other users' data: if you reach any, stop and
tell us. Do not degrade the service for other users.

## Supported versions

Only the latest release of the CLI receives security fixes.
