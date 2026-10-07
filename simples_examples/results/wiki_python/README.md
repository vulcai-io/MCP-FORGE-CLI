# Website example

**Source:** [https://en.wikipedia.org/wiki/Python_(programming_language)](https://en.wikipedia.org/wiki/Python_(programming_language))

**Score:** 8.4/10 (5 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates website discovery with no public API: tools are inferred from the HTML structure of a static Wikipedia article, with no JavaScript rendering involved.

---

Provides access to specific Wikipedia page content and metadata, with a focus on the Python programming language article and its related pages.

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

## Tools disponibles (5)

### `search_wikipedia`

Search for Wikipedia articles or retrieve a specific article by its exact title. Use this tool to find information across the entire encyclopedia or navigate to a known article.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `search` | `str | None` | no | Keywords to search for within Wikipedia articles. |
| `title` | `str | None` | no | Exact title of a Wikipedia article to retrieve directly without searching. |
---
### `get_wiki_page`

Retrieve the full content of a specific Wikipedia article by its slug (e.g., Main_Page, Wikipedia:Contents). Use this when you know the exact page you want to access.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `slug` | `str` | yes | The page identifier under /wiki/ (e.g., 'Main_Page', 'Portal:Current_events'). |
---
### `list_wiki_links_here`

Get a list of all Wikipedia articles that link to a specific page. Use this to find backlinks or see which topics reference a given article.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `slug` | `str` | yes | The target article slug (e.g., 'Python_(programming_language)') to view links pointing to it. |
---
### `list_wiki_recent_changes`

View recent changes and edits to pages that link from a specific article. Use this to track the latest modifications to related content.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `slug` | `str` | yes | The source article slug (e.g., 'Python_(programming_language)') to track changes to its linked pages. |
---
### `get_python_article`

Retrieve the content of the 'Python (programming language)' Wikipedia article. Use this as a starting point for Python-related queries or general programming knowledge.

---
