# COBOL codebase example

**Source:** `./codebases/cobol` (bundled in this repo under `simples_examples/codebases/cobol`)

**Score:** 8.4/10 (3 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's COBOL support: only modern, isolated subprograms (`PROGRAM-ID` with an explicit `PROCEDURE DIVISION USING` clause) are exposed as real, executable tools — each call compiles and runs the subprogram via GnuCOBOL (`cobc`).

---

Provides utility functions for prime checking, factorial calculation, and string reversal extracted from the cobol codebase.

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

## Tools disponibles (3)

### `check_is_prime`

Tests if a given non-negative integer is a prime number. Use this to determine primality for mathematical or algorithmic tasks.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer to test for primality (must be between 0 and 9999). |
---
### `compute_factorial`

Calculates the factorial of a non-negative integer. Use this to compute the product of all positive integers up to the specified value.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n2` | `int` | yes | The integer for which to compute the factorial (must be between 0 and 9999). |
---
### `reverse_string`

Reverses the character order of a given string. Use this to mirror text sequences for processing or display purposes.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The string to reverse (maximum length 50 characters). |
---
