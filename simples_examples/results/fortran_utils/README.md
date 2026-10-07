# Fortran codebase example

**Source:** `./codebases/fortran` (bundled in this repo under `simples_examples/codebases/fortran`)

**Score:** 8.2/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Fortran: generates tools that recompile a small driver plus the original function with `gfortran` and run the resulting binary for each call (no compilation cache between calls).

---

Provides utility functions including primality testing, factorial calculation, string reversal, and list summation. Enables access to basic mathematical and string processing operations extracted from the fortran codebase.

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

Check whether a given integer is a prime number. Use this when you need to validate if a number has no divisors other than 1 and itself.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer to test for primality. |
---
### `calculate_factorial`

Compute the factorial of a non-negative integer. Use this when you need the product of all positive integers up to n.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer to calculate the factorial of. |
---
### `reverse_string`

Reverse the character order of a given string. Use this when you need to transform a string into its reversed form.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The string to be reversed. |
---
### `sum_list`

Calculate the sum of a list of numbers. Use this when you need to aggregate the total of a provided numeric sequence.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | An array of numbers to be summed. |
| `count` | `int` | yes | The number of elements in the list. |
---
