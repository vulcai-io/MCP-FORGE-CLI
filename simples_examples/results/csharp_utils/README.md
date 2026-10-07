# C# codebase example

**Source:** `./codebases/csharp` (bundled in this repo under `simples_examples/codebases/csharp`)

**Score:** 8.4/10 (4 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates mcp-forge's codebase discovery for C#: parses free functions from the source file and generates tools that invoke the real C# toolchain (`dotnet`) directly against it, one call at a time.

---

A collection of common C# utility functions, including prime checking, factorial calculation, string reversal, and list summation.

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

### `utils_isprime`

Checks if a given integer is a prime number. Use this to validate primality in mathematical contexts.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The integer to check for primality. |
---
### `utils_factorial`

Computes the factorial of a non-negative integer. Use this for combinatorial calculations.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `n` | `int` | yes | The non-negative integer whose factorial is to be computed. |
---
### `utils_reversestring`

Reverses the characters in a string. Use this for string manipulation tasks requiring inversion.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `s` | `str` | yes | The input string to be reversed. |
---
### `utils_sumlist`

Calculates the sum of a list of floating-point numbers. Use this for aggregating numerical data.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `numbers` | `list[float]` | yes | An array of floating-point numbers to sum. |
---
