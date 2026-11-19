"""
Schéma de réponse des tools (lot D, D5, 2026-11-01).

Le schéma de la réponse (OpenAPI : réponse 2xx JSON ; GraphQL : type de
retour, mêmes champs que la sélection) devient l'outputSchema du tool. Il
est **descriptif** : seuls `description`, `properties` et `items` sont
gardés ; le type, le format et les valeurs possibles passent dans la
description. Sans `type`, `required` ni `enum`, aucune réponse ne peut le
contredire : une API qui s'écarte de sa spec (cas fréquent) ne fait pas
échouer le tool, alors qu'un schéma strict la ferait refuser par le
serveur MCP et par le client, qui valident la sortie.

`sanitize` borne et nettoie un schéma reçu (payload de la CLI) : il finit
en littéral dans le code généré et sous les yeux du LLM.
"""
from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable
from typing import Any

from mcp_forge.instructions import visible

MAX_DEPTH = 4
MAX_PROPERTIES = 40
MAX_NODES = 120
MAX_DESCRIPTION = 200
# Budget en caractères (noms et descriptions) : l'outputSchema de chaque tool
# part dans tools/list, donc dans le contexte du LLM client (Stripe : 25 Kio
# médians par tool avant ce budget)
MAX_CHARS = 4000
MAX_ENUM_VALUES = 10
# Borne par tool dans le serveur généré (for_tool), en caractères JSON
TOOL_SCHEMA_CHARS = 1200


def sanitize(schema: Any) -> dict | None:
    """Schéma descriptif borné : clés `description` (texte visible, 200
    caractères au plus), `properties` (40 au plus par objet) et `items`,
    profondeur 4, 120 nœuds et 4 000 caractères au total (parcours en
    largeur d'abord : les champs du premier niveau passent avant le
    détail). None si rien d'utile."""
    if not isinstance(schema, dict):
        return None
    nodes, chars = [MAX_NODES], [MAX_CHARS]

    def take(text: str) -> bool:
        if nodes[0] <= 0 or chars[0] < len(text):
            return False
        nodes[0] -= 1
        chars[0] -= len(text)
        return True

    root: dict[str, Any] = {}
    queue = deque([(schema, root, 0)])
    while queue:
        node, out, depth = queue.popleft()
        description = node.get("description")
        if isinstance(description, str) and visible(description).strip():
            text = visible(description).strip()[:MAX_DESCRIPTION]
            if take(text):
                out["description"] = text
        if depth >= MAX_DEPTH:
            continue
        properties = node.get("properties")
        if isinstance(properties, dict):
            kept: dict[str, Any] = {}
            for name, sub in list(properties.items())[:MAX_PROPERTIES]:
                name = visible(str(name)).strip()[:100]
                if name and isinstance(sub, dict) and take(name):
                    kept[name] = {}
                    queue.append((sub, kept[name], depth + 1))
            if kept:
                out["properties"] = kept
        items = node.get("items")
        if isinstance(items, dict) and take(""):
            out["items"] = {}
            queue.append((items, out["items"], depth + 1))
    _drop_empty_items(root)
    return root or None


def _drop_empty_items(node: dict) -> None:
    """`items` vide (budget épuisé avant son contenu) : retiré. Une propriété
    vide reste : son nom est déjà une information."""
    for child in (node.get("properties") or {}).values():
        _drop_empty_items(child)
    if "items" in node:
        _drop_empty_items(node["items"])
        if not node["items"]:
            del node["items"]


def _first_level(schema: dict) -> dict:
    """Premier niveau seulement : description, noms des champs et leur
    description (pour une liste, ceux de ses éléments)."""
    out: dict[str, Any] = {k: v for k, v in schema.items() if k == "description"}
    if isinstance(schema.get("properties"), dict):
        out["properties"] = {name: {k: v for k, v in sub.items() if k == "description"}
                             for name, sub in schema["properties"].items()}
    elif isinstance(schema.get("items"), dict):
        out["items"] = _first_level({k: v for k, v in schema["items"].items() if k != "items"})
    return out


def _size(schema: dict) -> int:
    return len(json.dumps(schema, ensure_ascii=False))


def for_tool(schema: Any, max_chars: int | None = None) -> dict | None:
    """outputSchema d'un tool, borné (décision du PO, 2026-11-01) : il part
    dans tools/list, donc dans le contexte du LLM client à chaque message.
    Schéma complet jusqu'à TOOL_SCHEMA_CHARS caractères (JSON), sinon premier
    niveau seulement, sinon None (le générateur garde alors la seule
    description de la réponse)."""
    limit = TOOL_SCHEMA_CHARS if max_chars is None else max_chars
    schema = sanitize(schema)
    if schema is None:
        return None
    if _size(schema) <= limit:
        return schema
    first = _first_level(schema)
    return first if _size(first) <= limit else None


def _type_text(node: dict) -> str:
    kind = node.get("type")
    if isinstance(kind, list):
        kind = " or ".join(str(k) for k in kind)
    text = str(kind) if kind else ""
    if node.get("format"):
        text = f"{text} ({node['format']})" if text else str(node["format"])
    enum = node.get("enum")
    if isinstance(enum, list) and enum:
        values = ", ".join(str(v)[:40] for v in enum[:MAX_ENUM_VALUES])
        more = ", …" if len(enum) > MAX_ENUM_VALUES else ""
        text = f"{text}, one of: {values}{more}" if text else f"one of: {values}{more}"
    if node.get("nullable"):
        text = f"{text}, nullable" if text else "nullable"
    return text


def from_openapi(schema: Any, resolve: Callable[[Any], Any]) -> dict | None:
    """Schéma descriptif d'un schéma OpenAPI (v2 ou v3). `resolve` résout un
    `$ref` ; un type déjà en cours de description (récursif) est arrêté."""

    def walk(node: Any, depth: int, seen: frozenset[str]) -> dict | None:
        if not isinstance(node, dict):
            return None
        ref = node.get("$ref")
        if isinstance(ref, str):
            if ref in seen:
                return {"description": f"{ref.rsplit('/', 1)[-1]} (recursive)"}
            seen = seen | {ref}
            node = resolve(node)
            if not isinstance(node, dict):
                return None
        merged = dict(node)
        for combinator in ("allOf", "oneOf", "anyOf"):
            variants = node.get(combinator)
            if isinstance(variants, list):
                properties = dict(merged.get("properties") or {})
                for variant in variants:
                    variant_node = resolve(variant) if isinstance(variant, dict) and "$ref" in variant else variant
                    if isinstance(variant_node, dict):
                        properties.update(variant_node.get("properties") or {})
                        merged.setdefault("type", variant_node.get("type"))
                        if variant_node.get("items") and "items" not in merged:
                            merged["items"] = variant_node["items"]
                if properties:
                    merged["properties"] = properties
        out: dict[str, Any] = {}
        type_text = _type_text(merged)
        description = str(merged.get("description") or merged.get("title") or "").strip()
        if description and type_text:
            out["description"] = f"{description} ({type_text})"
        elif description or type_text:
            out["description"] = description or type_text
        if depth < MAX_DEPTH:
            properties = merged.get("properties")
            if isinstance(properties, dict):
                children = {name: walk(sub, depth + 1, seen) for name, sub in properties.items()}
                children = {name: child for name, child in children.items() if child is not None}
                if children:
                    out["properties"] = children
            items = walk(merged.get("items"), depth + 1, seen)
            if items:
                out["items"] = items
        return out

    return sanitize(walk(schema, 0, frozenset()))


def openapi_response_schema(operation: dict, resolve: Callable[[Any], Any], is_v2: bool) -> dict | None:
    """Schéma de la première réponse 2xx JSON de l'opération (200, 201, puis
    les autres 2xx)."""
    responses = operation.get("responses") or {}
    if not isinstance(responses, dict):
        return None
    codes = [c for c in ("200", "201") if c in responses]
    codes += sorted(c for c in responses if str(c).startswith("2") and c not in codes)
    for code in codes:
        response = resolve(responses[code])
        if not isinstance(response, dict):
            continue
        if is_v2:
            schema = response.get("schema")
        else:
            content = response.get("content") or {}
            media = next((m for m in content if "json" in m.lower()), None) or (
                "*/*" if "*/*" in content else None)
            schema = (content.get(media) or {}).get("schema") if media else None
        if isinstance(schema, dict):
            return from_openapi(schema, resolve)
    return None


def from_graphql(field_name: str, gql_type: dict, types_by_name: dict[str, Any], max_depth: int,
                 max_fields: int, description: str = "") -> dict | None:
    """Schéma descriptif de `data` pour une opération GraphQL :
    {field_name: <type de retour>}, mêmes champs que la sélection
    (profondeur et largeur bornées, champs sans argument)."""

    def type_label(node: dict) -> tuple[str, dict]:
        """(libellé du type, type nommé) : « [Country!]! » → ("list of Country", Country)."""
        is_list = False
        while node.get("ofType") or node.get("kind") in ("NON_NULL", "LIST"):
            if node.get("kind") == "LIST":
                is_list = True
            node = node.get("ofType") or {}
            if not node:
                break
        name = node.get("name") or ""
        return (f"list of {name}" if is_list else name), node

    def walk(gql: dict, field_description: str, depth: int, visited: frozenset[str]) -> dict:
        label, named = type_label(gql)
        name = named.get("name") or ""
        text = f"{field_description} ({label})" if field_description and label else field_description or label
        out: dict[str, Any] = {"description": text} if text else {}
        node_type = types_by_name.get(name) or {}
        if node_type.get("kind") not in ("OBJECT", "INTERFACE") or depth >= max_depth or name in visited:
            return out
        properties = {}
        for sub in (node_type.get("fields") or [])[:max_fields]:
            sub_name = sub.get("name")
            if not sub_name or sub_name.startswith("__") or sub.get("args"):
                continue
            properties[sub_name] = walk(sub.get("type") or {}, sub.get("description") or "", depth + 1,
                                        visited | {name})
        if properties:
            if label.startswith("list of "):
                out["items"] = {"properties": properties}
            else:
                out["properties"] = properties
        return out

    return sanitize({"properties": {field_name: walk(gql_type, description, 0, frozenset())}})
