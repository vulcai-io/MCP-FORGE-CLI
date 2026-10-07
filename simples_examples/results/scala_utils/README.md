# Scala codebase example

**Source:** `./codebases/scala` (bundled in this repo under `simples_examples/codebases/scala`)

**Score:** 8.5/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Scala: parses free functions from the source file and generates tools that invoke the real Scala toolchain (`scala-cli`) directly against it, one call at a time.

---

Provides utility functions such as primality testing, factorial calculation, string reversal, and list summation.

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

Determine whether a number is prime. Use this when you need to verify if a given integer is a prime number.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer to check for primality |
---
### `calculate_factorial`

Compute the factorial of a non-negative integer. Use this when you need to calculate n! (n × (n-1) × ... × 1).

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | Non-negative integer for which to calculate the factorial |
---
### `reverse_string`

Reverse the characters in a string. Use this when you need to flip the order of characters in text.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The string to reverse |
---
### `sum_list`

Calculate the sum of all numbers in a list. Use this when you need to add up numeric values.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | Array of numeric values (integers or decimals) to sum |
---
