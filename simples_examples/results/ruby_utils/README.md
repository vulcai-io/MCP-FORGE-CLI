# Ruby codebase example

**Source:** `./codebases/ruby` (bundled in this repo under `simples_examples/codebases/ruby`)

**Score:** 8.5/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Ruby: parses free functions from the source file and generates tools that invoke the real Ruby toolchain (`ruby`) directly against it, one call at a time.

---

Provides utility functions for number theory, factorials, string manipulation, and list operations extracted from the ruby library.

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

Determine if a number is prime. Use this when you need to verify whether a given integer has exactly two divisors (1 and itself).

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | Integer number to check for primality |
---
### `calculate_factorial`

Compute the factorial of a non-negative integer. Use this when you need to calculate n! (the product of all positive integers up to n).

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | Non-negative integer for which to calculate the factorial |
---
### `reverse_string`

Reverse the order of characters in a string. Use this when you need to flip a string's character sequence for validation, palindrome checking, or text transformation.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | String to reverse |
---
### `sum_list`

Calculate the sum of all numbers in a list. Use this when you need to aggregate numeric values into a single total.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | Array of numeric values to sum |
---
