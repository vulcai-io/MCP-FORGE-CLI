# Rust codebase example

**Source:** `./codebases/rust` (bundled in this repo under `simples_examples/codebases/rust`)

**Score:** 8.2/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Rust: generates tools that recompile a small driver plus the original function with `rustc` and run the resulting binary for each call (no compilation cache between calls).

---

Provides utility functions for number theory, text processing, and list operations. Enables tasks such as checking primality, calculating factorials, reversing strings, and summing lists.

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

Check if a given non-negative integer is a prime number. Use this when you need to verify the primality of a value for mathematical calculations or number theory tasks.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer to check for primality. |
---
### `calculate_factorial`

Compute the factorial of a non-negative integer. Use this when you need to calculate the product of all positive integers up to n for combinatorial problems.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer for which to compute the factorial. |
---
### `reverse_string`

Reverse the characters in a given string. Use this when you need to flip the order of characters for string manipulation tasks.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The string to be reversed. |
---
### `sum_numbers`

Calculate the sum of a list of floating-point numbers. Use this when you need to compute the total of a collection of numerical values.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | The list of floating-point numbers to sum. |
---
