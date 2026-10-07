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
    if _use_local(config):
        from mcp_forge.pipeline.local import run_local
        return run_local(result, config)

    from mcp_forge.pipeline.remote import run_remote
    return run_remote(result, config)


def _use_local(config: ForgeConfig) -> bool:
    if getattr(config, "force_local", False):
        return True
    if os.environ.get("FORGE_MODE", "").lower() == "local":
        return True
    if os.environ.get("FORGE_LICENSE_KEY", ""):
        return False
    return False  # pas de licence → remote.py affiche l'erreur FORGE_LICENSE_KEY manquante
