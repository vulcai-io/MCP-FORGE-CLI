# Julia codebase example

**Source:** `./codebases/julia` (bundled in this repo under `simples_examples/codebases/julia`)

**Score:** 8.5/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for Julia: tools invoke the real Julia function via a `julia` subprocess for each call.

---

Provides access to public utility functions extracted from the julia codebase, including functions for checking primality, calculating factorials, reversing strings, and summing lists.

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

Determine if a number is prime. Use this to check primality of positive integers.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | Positive integer to check for primality |
---
### `calculate_factorial`

Compute the factorial of a non-negative integer. Use this to calculate n! for mathematical operations.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | Non-negative integer for factorial calculation |
---
### `reverse_string`

Reverse a string. Use this to invert character order in text.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | String to reverse |
---
### `sum_list`

Calculate the sum of numeric values in a list. Use this to aggregate numbers for totals or averages.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list` | yes | Array of numeric values to sum |
---
