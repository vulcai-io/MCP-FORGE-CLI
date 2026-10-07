# PHP codebase example

**Source:** `./codebases/php` (bundled in this repo under `simples_examples/codebases/php`)

**Score:** 8.7/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for PHP: parses free functions from the source file and generates tools that invoke the real PHP toolchain (`php`) directly against it, one call at a time.

---

Provides access to public utility functions extracted from a PHP codebase, including prime checking, factorial calculation, string reversal, and list summing.

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

Determine whether a number is prime. Use this to verify if a given integer has exactly two divisors (1 and itself).

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | Integer value to check for primality |
---
### `calculate_factorial`

Calculate the factorial of a non-negative integer. Use this to find the product of all positive integers from 1 to n.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | Non-negative integer for which to calculate factorial |
---
### `reverse_string`

Reverse the order of characters in a string. Use this to flip the sequence of characters in a text value.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | Text string to reverse |
---
### `sum_list`

Calculate the sum of all numbers in a list. Use this to add up numeric values in an array.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | Array of numeric values to sum |
---
