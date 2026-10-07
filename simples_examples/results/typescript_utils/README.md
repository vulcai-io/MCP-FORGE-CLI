# TypeScript codebase example

**Source:** `./codebases/typescript` (bundled in this repo under `simples_examples/codebases/typescript`)

**Score:** 8.7/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for TypeScript: parses free functions from the source file and generates tools that invoke the real TypeScript toolchain (`npx`) directly against it, one call at a time.

---

Provides access to utility functions extracted from a TypeScript codebase, including prime checking, factorial calculation, string reversal, and list summation.

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

Check whether a given number is a prime number.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer to test for primality |
---
### `compute_factorial`

Calculate the factorial of a non-negative integer.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer to compute the factorial of |
---
### `reverse_string`

Reverse the order of characters in a given string.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The string to reverse |
---
### `sum_list`

Calculate the sum of a list of numbers.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | An array of numbers to sum |
---
