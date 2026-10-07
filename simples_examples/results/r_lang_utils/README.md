# R codebase example

**Source:** `./codebases/r_lang` (bundled in this repo under `simples_examples/codebases/r_lang`)

**Score:** 8.5/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for R: parses free functions from the source file and generates tools that invoke the real R toolchain (`Rscript`) directly against it, one call at a time.

---

Provides access to public utility functions from the r_lang codebase, including functions for checking primes, computing factorials, reversing strings, and summing lists.

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

### `utils_is_prime`

Determines whether a given positive integer is a prime number. Use this when you need to validate the primality of a numeric value.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer to check for primality. Must be a non-negative integer. |
---
### `utils_factorial_fn`

Calculates the factorial of a non-negative integer. Use this to compute n! (product of all positive integers up to n).

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer for which to calculate the factorial. |
---
### `utils_reverse_string`

Reverses the order of characters in a given string. Use this when you need to process text in reverse order.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The input string to be reversed. |
---
### `utils_sum_list`

Calculates the sum of all elements in a list of numbers. Use this to aggregate numeric data efficiently.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | A list of numeric values (integers or floats) to sum. |
---
