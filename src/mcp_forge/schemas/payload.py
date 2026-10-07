"""
Contrat JSON entre le CLI (discovery locale) et l'API Azure (enrichissement + génération).

Ce modèle est une vue sanitisée de DiscoveryResult :
- Aucun chemin absolu (source_path exclu)
- headers jamais inclus (vecteur potentiel de fuite de credentials)
- metadata filtrée : seules les clés connues et nécessaires à la génération
- cmd_args réduit au nom du binaire uniquement (pas de chemin absolu)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from mcp_forge.models import (
    AuthScheme,
    DiscoveredTool,
    DiscoveryResult,
    ParameterType,
    SourceType,
    ToolParameter,
)

# Clés de metadata autorisées par source_type.
# Toute clé absente de cette liste est silencieusement supprimée.
_ALLOWED_METADATA: dict[SourceType, set[str]] = {
    SourceType.OPENAPI:   set(),
    SourceType.WEBSITE:   set(),
    SourceType.GRAPHQL:   {"operation", "field_name", "gql_args"},
    SourceType.CLI_APP:   {"cmd", "param_flags"},
    SourceType.CODEBASE:  {"file", "function", "class", "is_async", "language",
                           "return_type", "is_header", "cpp_params_full"},
}


class ToolParameterPayload(BaseModel):
    name: str                     = Field(max_length=200)
    type: ParameterType           = ParameterType.STRING
    description: str              = Field(default="", max_length=2_000)
    required: bool                = False
    default: Any                  = None
    enum_values: list[str]        = Field(default_factory=list, max_length=100)
    items_type: ParameterType | None = None
    # Emplacement du paramètre dans la requête HTTP ("query"|"header"|"path"|
    # "body"|"body_array"|"formData"|"file_upload") — calculé côté CLI par la
    # discovery à partir de la spec source. Sans ce champ, l'API régénère le
    # serveur avec un param_in vide et devine la mauvaise forme de requête
    # (params= vs json= vs data=, header vs query) pour chaque paramètre.
    param_in: str                 = Field(default="", max_length=20)


class DiscoveredToolPayload(BaseModel):
    name: str                          = Field(max_length=200)
    description: str                   = Field(max_length=5_000)
    parameters: list[ToolParameterPayload] = Field(default_factory=list, max_length=50)
    http_method: str | None            = Field(default=None, max_length=10)
    endpoint: str | None               = Field(default=None, max_length=2_048)
    base_url: str | None               = Field(default=None, max_length=2_048)
    response_description: str          = Field(default="", max_length=2_000)
    tags: list[str]                    = Field(default_factory=list, max_length=20)
    metadata: dict[str, Any]           = Field(default_factory=dict)
    enabled: bool                      = True
    # headers : intentionnellement absent


class DiscoveryPayload(BaseModel):
    """Payload envoyé par le CLI vers l'API Azure."""
    source_type:   SourceType
    title:         str = Field(default="", max_length=500)
    description:   str = Field(default="", max_length=10_000)
    base_url:      str = Field(default="", max_length=2_048)
    tools:         list[DiscoveredToolPayload] = Field(default_factory=list, max_length=1_000)
    auth_schemes:  list[AuthScheme] = Field(default_factory=list, max_length=20)
    forge_version: str = Field(default="", max_length=50)
    # source_path / source_url : intentionnellement absents

    @classmethod
    def from_discovery_result(cls, result: DiscoveryResult) -> "DiscoveryPayload":
        """Construit un payload sécurisé depuis un DiscoveryResult."""
        from mcp_forge import __version__
        return cls(
            source_type=result.source_type,
            title=result.title,
            description=result.description,
            base_url=result.base_url,
            tools=[_sanitize_tool(t, result.source_type) for t in result.tools],
            auth_schemes=result.auth_schemes,
            forge_version=__version__,
        )


def _sanitize_tool(tool: DiscoveredTool, source_type: SourceType) -> DiscoveredToolPayload:
    """Convertit un DiscoveredTool en version sanitisée pour le payload."""
    allowed = _ALLOWED_METADATA.get(source_type, set())
    metadata = _filter_metadata(tool.metadata, allowed)

    return DiscoveredToolPayload(
        name=tool.name,
        description=tool.description,
        parameters=[
            ToolParameterPayload(
                name=p.name,
                type=p.type,
                description=p.description,
                required=p.required,
                default=p.default,
                enum_values=p.enum_values,
                items_type=p.items_type,
                param_in=p.param_in,
            )
            for p in tool.parameters
        ],
        http_method=tool.http_method,
        endpoint=tool.endpoint,
        base_url=tool.base_url,
        response_description=tool.response_description,
        tags=tool.tags,
        metadata=metadata,
        enabled=tool.enabled,
    )


def _filter_metadata(
    metadata: dict[str, Any],
    allowed_keys: set[str],
) -> dict[str, Any]:
    """Filtre et neutralise les champs sensibles du metadata."""
    if not metadata or not allowed_keys:
        return {}

    filtered: dict[str, Any] = {}
    for key in allowed_keys:
        if key not in metadata:
            continue
        value = metadata[key]

        if key == "cmd" and isinstance(value, list) and value:
            # Garde uniquement le nom du binaire, pas le chemin absolu
            # ["/opt/interne/outil", "sous-cmd"] → ["outil", "sous-cmd"]
            filtered["cmd"] = [Path(value[0]).name] + list(value[1:])

        elif key == "file" and isinstance(value, str):
            # Chemin relatif uniquement — détecte les chemins absolus Unix et Windows
            p = Path(value)
            is_absolute = p.is_absolute() or value.startswith("/")
            filtered["file"] = p.name if is_absolute else value

        else:
            filtered[key] = value

    return filtered
