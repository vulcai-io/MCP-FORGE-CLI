# Go codebase example

**Source:** `./codebases/go` (bundled in this repo under `simples_examples/codebases/go`)

**Score:** 8.4/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Go: parses free functions from the source file and generates tools that invoke the real Go toolchain (`go`) directly against it, one call at a time.

---

Provides a collection of general-purpose utility functions, including prime number checking, factorial calculation, string reversal, and list summing.

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

Determine whether a number is prime. Use this when you need to verify if a given integer has exactly two divisors.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | Integer value to check for primality |
---
### `calculate_factorial`

Compute the factorial of a non-negative integer. Use this when you need to calculate n! (n × (n-1) × ... × 1).

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | Non-negative integer for which to calculate factorial |
---
### `reverse_string`

Reverse the characters in a string. Use this when you need to obtain a string with characters in reverse order.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | String to reverse |
---
### `sum_list`

Calculate the sum of numeric values in a list. Use this when you need to add multiple numbers together.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | Array of numeric values to sum |
---
