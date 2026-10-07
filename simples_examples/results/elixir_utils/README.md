# Elixir codebase example

**Source:** `./codebases/elixir` (bundled in this repo under `simples_examples/codebases/elixir`)

**Score:** 8.4/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Elixir: parses free functions from the source file and generates tools that invoke the real Elixir toolchain (`elixir`) directly against it, one call at a time.

---

Provides access to public utility functions from the elixir codebase, including operations for primality testing, factorial calculation, string reversal, and list summation.

Généré par **mcp-forge**.

## Installation

```bash
pip install -r requirements.txt
```

## Lancement

```bash
python server.py
```

## Test avec MCP Inspector

```bash
mcp dev server.py
```

## Tools disponibles (4)

### `is_prime`

Determines whether a given integer is a prime number. Use this to validate numerical properties.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer value to check. |
---
### `get_factorial`

Calculates the factorial of a non-negative integer. Use this for combinatorial calculations.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer for which to find the factorial. |
---
### `reverse_string`

Returns the input string in reverse order. Use this to manipulate text data.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The string to be reversed. |
---
### `sum_list`

Calculates the arithmetic sum of a list of numbers. Use this for aggregate numerical analysis.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | A list of integers or floats to be summed. |
---
