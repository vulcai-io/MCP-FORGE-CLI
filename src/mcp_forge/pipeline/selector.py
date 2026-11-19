"""
Sélecteur de pipeline : choisit entre local et distant selon l'environnement.

Ordre de priorité :
  1. Flag --local explicite (config.force_local = True)
  2. FORGE_MODE=local dans l'environnement
  3. FORGE_LICENSE_KEY présente → pipeline distant (Azure)
  4. Pas de clé → pipeline distant (remote.py affiche l'erreur manquante)
"""
from __future__ import annotations

import os

from mcp_forge.models import DiscoveryResult, ForgeConfig, GeneratedServer


def run_pipeline(result: DiscoveryResult, config: ForgeConfig) -> GeneratedServer:
    """Point d'entrée unique post-discovery. Délègue au bon pipeline."""
    _warn_tools_list_size(result, config)
    if _use_local(config):
        from mcp_forge.pipeline.local import run_local
        return run_local(result, config)

    from mcp_forge.pipeline.remote import run_remote
    return run_remote(result, config)


def _warn_tools_list_size(result: DiscoveryResult, config: ForgeConfig) -> None:
    """Avertissement (jamais un retrait) si la liste des tools est longue :
    le client MCP l'envoie au LLM à chaque message (voir
    mcp_forge/tools_list.py)."""
    from rich.console import Console
    from rich.markup import escape

    from mcp_forge.tools_list import size_report

    report = size_report(result.tools, config.no_output_schema)
    if report["warning"]:
        Console().print(f"[yellow]⚠ {escape(report['warning'])}[/yellow]")
    # Grande API par l'API : l'enrichissement y est sauté, le message de l'API
    # n'arrive pas jusqu'ici (en local, l'enrichissement l'affiche lui-même)
    from mcp_forge.discovery.limits import MAX_ENRICHED_TOOLS, large_api_message

    if not _use_local(config) and not config.no_llm and report["tools"] > MAX_ENRICHED_TOOLS:
        Console().print(f"[yellow]⚠ {escape(large_api_message(report['tools']))}[/yellow]")


def _use_local(config: ForgeConfig) -> bool:
    if getattr(config, "force_local", False):
        return True
    if os.environ.get("FORGE_MODE", "").lower() == "local":
        return True
    if os.environ.get("FORGE_LICENSE_KEY", ""):
        return False
    return False  # pas de licence → remote.py affiche l'erreur FORGE_LICENSE_KEY manquante
