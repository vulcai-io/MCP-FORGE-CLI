# Java codebase example

**Source:** `./codebases/java` (bundled in this repo under `simples_examples/codebases/java`)

**Score:** 8.4/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Java: each call writes a small driver class next to a copy of the source file, compiles both with `javac`, and runs the result with `java`.

---

Provides access to public Java utility functions extracted from the codebase, including operations like finding prime numbers, calculating factorials, reversing strings, and summing lists.

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

Determines whether a given integer is a prime number. Use this to validate if a number has no divisors other than 1 and itself.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer to test for primality. |
---
### `calculate_factorial`

Computes the factorial of a non-negative integer. Use this when you need the product of all positive integers up to n.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer for which to calculate the factorial. |
---
### `reverse_string`

Returns the reverse of the input string. Use this when the character order of a string needs to be inverted.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The input string to be reversed. |
---
### `sum_list`

Calculates the sum of a list of numbers. Use this to compute the total of a collection of numeric values.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list[float]` | yes | An array of numbers (integers or floats) to be summed. |
---
