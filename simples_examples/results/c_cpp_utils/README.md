# c_cpp codebase example

**Source:** `./codebases/c_cpp` (bundled in this repo under `simples_examples/codebases/c_cpp`)

**Score:** 8.5/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's C/C++ support: tools call into a precompiled shared library via `ctypes` — you provide the compiled `.so`/`.dll`, mcp-forge generates the typed wrapper from the source's free functions.

---

Provides access to fundamental C and C++ utility functions such as is_prime, factorial, reverse_string, and sum_list. Use this server when you need to execute basic mathematical and string operations extracted from a C/C++ codebase.

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

### `is_prime`

Checks if a given integer is a prime number. Use this tool when you need to verify the primality of a number for mathematical or algorithmic purposes.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The positive integer to check for primality. |
---
### `factorial`

Calculates the factorial of a non-negative integer. Use this tool to compute the product of all positive integers less than or equal to a given number.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer for which to calculate the factorial. |
---
### `reverse_string`

Reverses the characters of a given string. Use this tool to obtain the reverse order of a text string.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The string to be reversed. |
---
### `sum_list`

Calculates the sum of an array of numbers. Use this tool to find the total value of a list of floating-point numbers.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | An array of floating-point numbers to sum |
| `count` | `int` | yes | The number of elements in the numbers array |
---
