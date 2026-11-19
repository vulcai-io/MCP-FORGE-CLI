"""
Modules de découverte des capacités d'une source.
"""
from mcp_forge.models import DiscoveryResult, ForgeConfig, SourceType

from .cli_app import CLIAppDiscovery
from .codebase import CodebaseDiscovery
from .graphql import GraphQLDiscovery
from .openapi import OpenAPIDiscovery
from .web import WebDiscovery


def discover(config: ForgeConfig) -> DiscoveryResult:
    """Point d'entrée principal : sélectionne et lance le bon module de découverte."""
    discoverers = {
        SourceType.OPENAPI: OpenAPIDiscovery,
        SourceType.WEBSITE: WebDiscovery,
        SourceType.GRAPHQL: GraphQLDiscovery,
        SourceType.CLI_APP: CLIAppDiscovery,
        SourceType.CODEBASE: CodebaseDiscovery,
    }
    cls = discoverers.get(config.source_type)
    if cls is None:
        raise ValueError(f"Unsupported source type: {config.source_type}")
    return cls(config).discover()


__all__ = [
    "discover",
    "OpenAPIDiscovery",
    "WebDiscovery",
    "GraphQLDiscovery",
    "CLIAppDiscovery",
    "CodebaseDiscovery",
]
