# JavaScript codebase example

**Source:** `./codebases/javascript` (bundled in this repo under `simples_examples/codebases/javascript`)

**Score:** 8.4/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for JavaScript: parses free functions from the source file and generates tools that invoke the real JavaScript toolchain (`node`) directly against it, one call at a time.

---

Provides mathematical and string utility functions such as primality testing, factorial calculation, string reversal, and list summation.

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

Determines whether a given integer is a prime number. Use this to verify primality for a specific non-negative integer.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer to check for primality |
---
### `calculate_factorial`

Computes the factorial of a non-negative integer. Use this to find the product of all positive integers up to and including the specified number.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer to calculate the factorial for |
---
### `reverse_string`

Returns the reverse of a given string. Use this to reverse the character order of any input text.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The string to be reversed |
---
### `sum_list`

Calculates the sum of a list of numbers. Use this to compute the total of a provided collection of numeric values.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `str` | yes | A JSON array of numbers to sum. Example: [1, 2, 3] |
---
