# bash_lang codebase example

**Source:** `./codebases/bash_lang` (bundled in this repo under `simples_examples/codebases/bash_lang`)

**Score:** 8.5/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Bash: parses free functions from the source file and generates tools that invoke the real Bash toolchain (`bash`) directly against it, one call at a time.

---

Provides utility functions extracted from the bash_lang codebase, including operations for prime checking, factorial calculation, string reversal, and list summation.

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

Determine whether a given number is prime. Use this to check if a number has no divisors other than 1 and itself.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | Integer number to check for primality |
---
### `calculate_factorial`

Compute the factorial of a non-negative integer. Use this to calculate n! (the product of all positive integers from 1 to n).

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | Non-negative integer to calculate factorial for |
---
### `reverse_string`

Reverse the characters in a string. Use this to flip the order of characters from end to beginning.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `arg1` | `str` | yes | String to reverse |
---
### `sum_list`

Calculate the sum of numeric values in a list. Use this to add all numbers together and return the total.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `args` | `list` | yes | Array of numbers to sum |
---
