"""
Limites des serveurs générés depuis une spec OpenAPI (décisions du PO,
2026-11-01).

- Filtre des opérations, par tag et par préfixe de chemin (options
  --include-tags, --exclude-tags, --include-paths, --exclude-paths de la CLI,
  mêmes clés dans mcp-forge.yaml et dans l'API). Une opération est gardée si
  aucun filtre d'inclusion n'est donné, ou si l'un de ses tags ou son chemin
  correspond à un filtre d'inclusion ; une exclusion l'emporte toujours. Tags
  comparés sans casse ; un préfixe de chemin correspond au chemin lui-même et
  à ses sous-chemins (`/repos` : `/repos/{owner}`, pas `/repository`).
- Au plus MAX_TOOLS tools (les premières opérations dans l'ordre de la
  spec), comme le payload accepté par l'API.
- Au plus MAX_TOOL_PARAMETERS paramètres par tool : au-delà, les paramètres
  facultatifs (requête, en-tête, corps) sont regroupés dans un seul
  paramètre objet `options` (MAX_OPTION_PARAMETERS au plus), décrit par un
  schéma JSON complet ; les paramètres obligatoires, de chemin et de
  fichier restent séparés. Si cela ne suffit pas, le tool est retiré.
Chaque opération retirée est comptée dans la couverture (motifs ci-dessous,
connus du payload).
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from mcp_forge.models import DiscoveredTool, ToolParameter

MAX_TOOLS = 1_000
MAX_TOOL_PARAMETERS = 50
MAX_OPTION_PARAMETERS = 200
OPTIONS_PARAMETER = "options"

EXCLUDED_BY_FILTER = "operations left out by the --include/--exclude filters"
EXCLUDED_OVER_LIMIT = f"operations beyond the {MAX_TOOLS}-tool limit (the first {MAX_TOOLS} in spec order are kept)"
EXCLUDED_TOO_MANY_PARAMETERS = (f"operations with more than {MAX_TOOL_PARAMETERS} required, path or file parameters "
                                f"(or more than {MAX_OPTION_PARAMETERS} optional ones)")
EXCLUSION_REASONS = (EXCLUDED_BY_FILTER, EXCLUDED_OVER_LIMIT, EXCLUDED_TOO_MANY_PARAMETERS)

# Au-delà (tools après filtres), pas d'enrichissement des tools (décision du
# PO, 2026-11-01) : l'enrichissement est séquentiel (~6 s par lot de 5), un
# serveur plus grand dépasserait le délai de génération de l'API (300 s), et
# les grandes API ont déjà des descriptions détaillées
MAX_ENRICHED_TOOLS = 150


def large_api_message(count: int) -> str:
    """Message affiché quand l'enrichissement des tools est sauté."""
    return (f"Large API ({count} tools): the spec descriptions are kept as they are, they are already "
            f"detailed; filter below {MAX_ENRICHED_TOOLS} operations (--include-tags / --include-paths) "
            "to get LLM enrichment back.")


# Emplacements jamais regroupés : chemin, fichier, corps binaire ou tableau
_SEPARATE = ("path", "file_upload", "body_binary", "body_array")


def parse_list(values: Any) -> list[str]:
    """Liste d'options répétées ou séparées par des virgules (CLI, YAML,
    API), sans vide ni doublon."""
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    for value in values:
        for item in str(value).split(","):
            item = item.strip()
            if item and item not in out:
                out.append(item)
    return out[:100]


def _path_matches(path: str, prefix: str) -> bool:
    prefix = "/" + prefix.strip().strip("/")
    path = "/" + path.strip("/")
    return prefix == "/" or path == prefix or path.startswith(prefix + "/")


class OperationFilter:
    def __init__(self, include_tags: Iterable[str] = (), exclude_tags: Iterable[str] = (),
                 include_paths: Iterable[str] = (), exclude_paths: Iterable[str] = ()):
        self.include_tags = {t.lower() for t in parse_list(list(include_tags))}
        self.exclude_tags = {t.lower() for t in parse_list(list(exclude_tags))}
        self.include_paths = parse_list(list(include_paths))
        self.exclude_paths = parse_list(list(exclude_paths))

    @classmethod
    def from_config(cls, config: Any) -> OperationFilter:
        return cls(*(getattr(config, name, None) or () for name in
                     ("include_tags", "exclude_tags", "include_paths", "exclude_paths")))

    @property
    def active(self) -> bool:
        return bool(self.include_tags or self.exclude_tags or self.include_paths or self.exclude_paths)

    def keeps(self, path: str, tags: Iterable[str]) -> bool:
        tags = {str(t).lower() for t in tags or ()}
        if tags & self.exclude_tags or any(_path_matches(path, p) for p in self.exclude_paths):
            return False
        if not (self.include_tags or self.include_paths):
            return True
        return bool(tags & self.include_tags) or any(_path_matches(path, p) for p in self.include_paths)


def group_options(tool: DiscoveredTool) -> bool:
    """Ramène le tool sous MAX_TOOL_PARAMETERS paramètres en regroupant les
    facultatifs dans `option_parameters` (paramètre objet `options` du
    serveur généré). False si c'est impossible : le tool doit être retiré."""
    if len(tool.parameters) <= MAX_TOOL_PARAMETERS:
        return True
    separate = [p for p in tool.parameters if p.required or p.param_in in _SEPARATE]
    grouped = [p for p in tool.parameters if not (p.required or p.param_in in _SEPARATE)]
    if len(separate) + 1 > MAX_TOOL_PARAMETERS or len(grouped) > MAX_OPTION_PARAMETERS:
        return False
    tool.parameters = separate
    tool.option_parameters = grouped
    return True


def top_tags(tags_per_operation: Iterable[Iterable[str]], limit: int = 15) -> list[tuple[str, int]]:
    """Tags les plus fréquents, pour le message qui propose un filtre."""
    counter: Counter[str] = Counter(t for tags in tags_per_operation for t in set(tags or ()))
    return counter.most_common(limit)


def options_schema(parameters: list[ToolParameter]) -> dict[str, Any]:
    """Schéma JSON du paramètre `options` : une propriété par paramètre
    regroupé (type, valeurs permises, description), aucune autre clé."""
    from mcp_forge.instructions import visible

    types = {"string": "string", "integer": "integer", "number": "number", "boolean": "boolean",
             "array": "array", "object": "object"}
    properties: dict[str, Any] = {}
    for p in parameters:
        prop: dict[str, Any] = {}
        json_type = types.get(getattr(p.type, "value", str(p.type)))
        if json_type:
            prop["type"] = json_type
        description = visible(p.description or "").strip()[:300]
        if description:
            prop["description"] = description
        if p.enum_values and len(p.enum_values) <= 100:  # liste tronquée : des valeurs valides refusées
            prop["enum"] = [visible(str(v))[:100] for v in p.enum_values]
        properties[visible(p.name)] = prop
    return {
        "type": "object",
        "description": "Optional parameters of this operation, by name (omit the ones you do not need).",
        "properties": properties,
        "additionalProperties": False,
    }
