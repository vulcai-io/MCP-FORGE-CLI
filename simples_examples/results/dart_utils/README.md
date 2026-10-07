# Dart codebase example

**Source:** `./codebases/dart` (bundled in this repo under `simples_examples/codebases/dart`)

**Score:** 8.5/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Dart: parses free functions from the source file and generates tools that invoke the real Dart toolchain (`dart`) directly against it, one call at a time.

---

Provides public utility functions from the Dart codebase, including prime checking, factorial calculation, string reversal, and summing lists.

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

### `check_is_prime`

Determines whether a given integer is a prime number. Use this when you need to verify the primality of a number for mathematical calculations or number theory tasks.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer to test for primality. Must be a non-negative whole number. |
---
### `calculate_factorial`

Computes the factorial of a non-negative integer. Use this when you need the product of all positive integers up to the given number for combinatorics or probability calculations.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer for which to calculate the factorial. |
---
### `reverse_string`

Reverses the characters of a given string. Use this when you need to invert the order of a text string for validation, puzzles, or text processing.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The string to be reversed. |
---
### `sum_list`

Calculates the sum of all numbers in a list. Use this when you need the total of a set of numeric values provided as a list.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | A list of numbers (integers or decimals). Although typed as string in source, it expects a list of doubles. |
---
