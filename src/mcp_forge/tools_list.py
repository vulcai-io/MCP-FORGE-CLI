"""
Taille de la liste des tools (tools/list) d'un serveur généré (décisions du
PO, 2026-11-01).

Le client MCP place la liste complète des tools (nom, description, schéma
des paramètres, outputSchema) dans le contexte du LLM, à chaque message.
Une liste trop longue réduit la place laissée à la conversation, fait
baisser la qualité du choix des tools et augmente le coût de chaque
message ; certains clients limitent aussi le nombre de tools. D'où un
avertissement (jamais un retrait) au-delà de WARN_TOOLS tools ou d'une liste
estimée à plus de WARN_TOKENS jetons, avec la taille mesurée et les moyens
de la réduire (filtres par tag et par chemin, --no-output-schema).

L'estimation reproduit la forme de tools/list (FastMCP) à partir des tools
découverts : c'est une estimation (environ CHARS_PER_TOKEN caractères par
jeton), calculée de la même façon par la CLI, avant l'envoi, et par le
générateur, pour USAGE.md.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from mcp_forge.discovery.limits import options_schema
from mcp_forge.discovery.response_schema import for_tool
from mcp_forge.instructions import visible
from mcp_forge.models import DiscoveredTool

WARN_TOOLS = 100
WARN_TOKENS = 50_000
CHARS_PER_TOKEN = 4
_FILTER_HINT = ("--include-tags / --include-paths (or --exclude-tags / --exclude-paths) to generate only the "
                "operations you need, --no-output-schema to drop the response schemas")


def output_schema_for_tool(tool: DiscoveredTool) -> dict[str, Any]:
    """outputSchema du tool dans le serveur généré : borné (for_tool), ou la
    seule description de la réponse."""
    return for_tool(tool.response_schema) or {
        "description": visible(tool.response_description).strip()[:300] or "Response of the API"}


def _tool_entry(tool: DiscoveredTool, no_output_schema: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    # FastMCP reprend toute la docstring : description, section Args, Returns
    docstring = [tool.description, "", "    Args:"]
    for p in tool.parameters:
        kind = getattr(p.type, "value", str(p.type))
        prop: dict[str, Any] = {"title": p.name, "type": kind}
        if p.description:
            prop["description"] = p.description
        if p.enum_values:
            prop["enum"] = list(p.enum_values)
        if not p.required:
            prop = {"anyOf": [{"type": kind}, {"type": "null"}], "default": None, "title": p.name}
        properties[p.name] = prop
        docstring.append(f"        {p.name}: {p.description or p.name}")
    if tool.option_parameters:
        properties["options"] = {**options_schema(tool.option_parameters), "default": None}
        docstring.append("        options: optional parameters, by name (see the schema)")
    docstring += ["    Returns:", f"        {tool.response_description}"]
    entry: dict[str, Any] = {
        "name": tool.stable_name or tool.name,
        "description": "\n".join(docstring),
        "inputSchema": {"type": "object", "properties": properties,
                        "required": [p.name for p in tool.parameters if p.required]},
        "annotations": {"title": tool.name, "readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": False, "openWorldHint": True},
    }
    if not no_output_schema:
        entry["outputSchema"] = {"type": "object", "properties": {"result": output_schema_for_tool(tool)},
                                 "required": ["result"]}
    return entry


def estimate_chars(tools: Iterable[DiscoveredTool], no_output_schema: bool = False) -> int:
    """Taille estimée de tools/list, en caractères JSON."""
    return sum(len(json.dumps(_tool_entry(t, no_output_schema), ensure_ascii=False)) for t in tools if t.enabled)


def size_report(tools: list[DiscoveredTool], no_output_schema: bool = False) -> dict[str, Any]:
    """Nombre de tools, taille estimée et, au-delà d'un seuil, le texte de
    l'avertissement (sinon None)."""
    count = sum(1 for t in tools if t.enabled)
    chars = estimate_chars(tools, no_output_schema)
    tokens = chars // CHARS_PER_TOKEN
    warning = None
    if count > WARN_TOOLS or tokens > WARN_TOKENS:
        warning = (f"{count} tools, tool list estimated at ~{tokens // 1000}k tokens ({chars // 1024} KiB): "
                   "the MCP client sends it to the LLM with every message. Shorten it with " + _FILTER_HINT + ".")
    return {"tools": count, "chars": chars, "tokens": tokens, "warning": warning,
            "no_output_schema": no_output_schema}
