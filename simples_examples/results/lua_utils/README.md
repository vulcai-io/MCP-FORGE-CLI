# Lua codebase example

**Source:** `./codebases/lua` (bundled in this repo under `simples_examples/codebases/lua`)

**Score:** 8.5/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Lua: parses free functions from the source file and generates tools that invoke the real Lua toolchain (`lua`) directly against it, one call at a time.

---

Provides lightweight Lua utility functions for mathematical operations (primality testing, factorial) and string/list manipulation (reversal, summation).

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

Checks if the given integer is a prime number. Use this when verifying primality of a value.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer value to check for primality. |
---
### `calculate_factorial`

Computes the factorial of a non-negative integer. Use this to get the product of all integers from 1 to n.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer to compute the factorial of. |
---
### `reverse_string`

Reverses the characters in the input string. Use this when the order of a string's characters needs to be inverted.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The input string to be reversed. |
---
### `sum_list`

Calculates the sum of a list of numbers. Use this to obtain the total of numeric values.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | The list of numeric values to sum. |
---
