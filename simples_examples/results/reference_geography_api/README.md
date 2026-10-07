# GraphQL example

**Source:** [https://countries.trevorblades.com/graphql](https://countries.trevorblades.com/graphql)

**Score:** 8.7/10 (6 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates GraphQL wrapping: tools are generated from the schema obtained via introspection, one per query, each one sending a real GraphQL request to the live endpoint.

---

Retrieves static geographic and linguistic reference data, including specific countries, continents, and their associated languages.

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

## Tools disponibles (6)

### `continent`

GraphQL query : continent

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `code` | `str` | yes | - |
---
### `continents`

GraphQL query : continents

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `filter` | `dict | None` | no | Objet de type ContinentFilterInput |
---
### `countries`

GraphQL query : countries

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `filter` | `dict | None` | no | Objet de type CountryFilterInput |
---
### `country`

GraphQL query : country

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `code` | `str` | yes | - |
---
### `language`

GraphQL query : language

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `code` | `str` | yes | - |
---
### `languages`

GraphQL query : languages

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `filter` | `dict | None` | no | Objet de type LanguageFilterInput |
---
