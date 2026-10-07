# PowerShell codebase example

**Source:** `./codebases/powershell` (bundled in this repo under `simples_examples/codebases/powershell`)

**Score:** 8.4/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for PowerShell: parses free functions from the source file and generates tools that invoke the real PowerShell toolchain (`powershell`) directly against it, one call at a time.

---

Provides utility functions for basic mathematical operations including primality testing, factorial calculation, string reversal, and list summing.

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

### `test_is_prime`

Determine whether a given integer is a prime number. Use this when you need to validate if an integer has no divisors other than itself and 1.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer to test for primality. |
---
### `get_factorial`

Calculate the factorial of a non-negative integer. Use this when you need the product of all positive integers up to the specified number.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer to calculate the factorial of. |
---
### `get_reverse_string`

Reverse the characters of a given string. Use this when you need to process or validate strings in their reversed order.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The string to reverse. |
---
### `get_sum_list`

Calculate the sum of a list of numbers. Use this when you need to compute the aggregate total of a collection of numeric values.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list[float]` | yes | An array of numbers to sum. |
---
