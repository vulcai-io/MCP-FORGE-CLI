# Python codebase example

**Source:** `./codebases/python` (bundled in this repo under `simples_examples/codebases/python`)

**Score:** 8.5/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Python: parses free functions from the source file and generates tools that import and call the real Python module directly, no subprocess involved.

---

A utility service providing common Python functions for mathematical operations and string manipulation. Enables tools for checking prime numbers, calculating factorials, reversing strings, and summing lists.

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

Use this tool to determine if a given integer is a prime number. Returns true only if the number is greater than 1 and has no divisors other than 1 and itself.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer to test for primality. |
---
### `compute_factorial`

Use this tool to calculate the factorial of a non-negative integer. Returns the product of all positive integers less than or equal to n.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer for which to compute the factorial. |
---
### `reverse_string`

Use this tool to get the characters of a string in reverse order. Ideal for quickly inverting text without manual logic.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The string to be reversed. |
---
### `sum_list`

Use this tool to calculate the total sum of all numeric values in a provided list. Returns the aggregate of the array's elements.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | An array of numeric values (integers or floating-point numbers) to be summed. |
---
