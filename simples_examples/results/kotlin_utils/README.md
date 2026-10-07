# Kotlin codebase example

**Source:** `./codebases/kotlin` (bundled in this repo under `simples_examples/codebases/kotlin`)

**Score:** 8.5/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Kotlin: parses free functions from the source file and generates tools that invoke the real Kotlin toolchain (`kotlin`) directly against it, one call at a time.

---

Provides utility functions for common Kotlin operations, including primality testing, factorial calculation, string reversing, and list summation.

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

Determines whether a given integer is a prime number. Use this tool when you need to verify if a number has no divisors other than 1 and itself.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer to check for primality. |
---
### `calculate_factorial`

Computes the factorial of a non-negative integer. Use this tool when you need the product of all positive integers less than or equal to "n".

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer for which to calculate the factorial. |
---
### `reverse_string`

Reverses the order of characters in a given string. Use this tool when you need to obtain the inverted version of a text input.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The string to be reversed. |
---
### `sum_list`

Calculates the sum of a list of numbers. Use this tool when you need to aggregate multiple numeric values into a single total.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | A list of numeric values to be summed. |
---
