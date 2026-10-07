# Groovy codebase example

**Source:** `./codebases/groovy` (bundled in this repo under `simples_examples/codebases/groovy`)

**Score:** 8.5/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Groovy: parses free functions from the source file and generates tools that invoke the real Groovy toolchain (`groovy`) directly against it, one call at a time.

---

This MCP server exposes Groovy utility functions for common mathematical and string operations, including prime checking, factorial calculation, string reversal, and list summation.

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

### `check_isprime`

Determine whether a number is prime. Use this to check if a given integer has exactly two divisors (1 and itself).

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer to check for primality. Must be a positive integer. |
---
### `calculate_factorial`

Calculate the factorial of a non-negative integer. Use this to compute n! (the product of all positive integers up to n).

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | Non-negative integer for which to calculate the factorial. |
---
### `reverse_string`

Reverse the characters in a string. Use this to get the inverse order of a given text string.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The string to reverse. |
---
### `sum_list`

Calculate the sum of all numeric values in a list. Use this to aggregate numbers from a collection.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | Array of numeric values (integers or decimals) to sum. |
---
