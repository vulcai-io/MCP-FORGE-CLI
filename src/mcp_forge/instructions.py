"""
Instructions personnalisées pour le LLM (lot D, D4, 2026-10-31) et
nettoyage des textes montrés au LLM.

- `instructions` : pour tout le serveur, envoyées au client à
  l'initialisation MCP (champ `instructions` de FastMCP) ;
- `tool_instructions` : par tool (clé : nom MCP du tool), ajoutées à sa
  description.

Sources : mcp-forge.yaml (`instructions`, `tool_instructions`), options de
la CLI (`--instructions`, `--tool-instruction NOM=TEXTE`), champs de l'API.

Tout texte destiné au LLM (ces instructions, et les descriptions venues de
la source) est débarrassé des caractères invisibles : largeur nulle,
contrôle de direction (bidi), caractères « tag » — un moyen courant de
cacher des instructions dans une description (OWASP MCP03).
"""
from __future__ import annotations

import re

MAX_SERVER_INSTRUCTIONS = 4000
MAX_TOOL_INSTRUCTIONS = 1000
MAX_TOOL_INSTRUCTION_ENTRIES = 200

# Largeur nulle et formatage invisible, contrôle de direction, caractères
# « tag » (U+E0000–U+E007F), contrôles C0/C1 sauf saut de ligne et tabulation.
_INVISIBLE_RANGES = (
    (0x200B, 0x200F), (0x2028, 0x2029), (0x202A, 0x202E), (0x2060, 0x2064),
    (0x2066, 0x2069), (0xFEFF, 0xFEFF), (0xE0000, 0xE007F),
    (0x00, 0x08), (0x0B, 0x0C), (0x0E, 0x1F), (0x7F, 0x9F),
)
INVISIBLE = re.compile("[" + "".join(
    f"{re.escape(chr(a))}-{re.escape(chr(b))}" for a, b in _INVISIBLE_RANGES) + "]")


def visible(text: str) -> str:
    """Le texte sans ses caractères invisibles."""
    return INVISIBLE.sub("", text or "")


def clean_instructions(text: str, limit: int, what: str) -> str:
    """Instructions nettoyées (caractères invisibles retirés, espaces aux
    bords) ; ValueError si elles dépassent `limit` caractères."""
    text = visible(str(text)).strip()
    if len(text) > limit:
        raise ValueError(f"{what}: {len(text)} characters, limit {limit}")
    return text


def clean_tool_instructions(mapping: dict) -> dict[str, str]:
    if not isinstance(mapping, dict):
        raise ValueError("tool_instructions: expected a mapping of tool name to text")
    if len(mapping) > MAX_TOOL_INSTRUCTION_ENTRIES:
        raise ValueError(f"tool_instructions: {len(mapping)} entries, limit {MAX_TOOL_INSTRUCTION_ENTRIES}")
    cleaned = {}
    for name, text in mapping.items():
        name = visible(str(name)).strip()
        text = clean_instructions(text, MAX_TOOL_INSTRUCTIONS, f"tool_instructions[{name}]")
        if name and text:
            cleaned[name] = text
    return cleaned


def parse_tool_instruction_options(values: list[str] | None) -> dict[str, str]:
    """Options `--tool-instruction NOM=TEXTE` (répétables)."""
    mapping: dict[str, str] = {}
    for value in values or []:
        name, sep, text = value.partition("=")
        if not sep or not name.strip():
            raise ValueError(f"--tool-instruction: expected NAME=TEXT, got {value!r}")
        mapping[name.strip()] = text
    return mapping
