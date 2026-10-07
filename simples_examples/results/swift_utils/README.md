# Swift codebase example

**Source:** `./codebases/swift` (bundled in this repo under `simples_examples/codebases/swift`)

**Score:** 8.7/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Swift: parses free functions from the source file and generates tools that invoke the real Swift toolchain (`swift`) directly against it, one call at a time.

---

Provides a collection of fundamental utility functions including prime number checking, factorial calculation, string reversal, and list summation.

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

### `check_prime`

Determines whether a given integer is a prime number. Use this tool to validate primality for mathematical computations or number theory tasks.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer to test for primality. Must be greater than 1. |
---
### `calculate_factorial`

Computes the factorial of a non-negative integer. Use this tool to obtain combinatorial values or solve problems involving permutations and combinations.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer for which to calculate the factorial. Must be >= 0. |
---
### `reverse_string`

Returns the input string with its characters in reverse order. Use this tool for string manipulation tasks where reversal is required.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The string to be reversed. |
---
### `sum_list`

Calculates the total sum of a list of numeric values. Use this tool to compute aggregates for floating-point number collections.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list[float]` | yes | An array of double-precision floating-point numbers to sum. |
---
