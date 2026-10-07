"""
Chargement de la configuration mcp-forge depuis un fichier YAML.

Priorité : flags CLI > mcp-forge.yaml > valeurs par défaut

Format supporté (mcp-forge.yaml) :
  source: https://api.example.com/openapi.json
  mode: auto
  output: ./generated
  name: my_server
  type: openapi
  name_style: exhaustive
  no_llm: false
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

_DEFAULT_CONFIG_FILE = "mcp-forge.yaml"


def load_yaml_config(config_path: str | None) -> dict[str, Any]:
    """Charge un fichier YAML de configuration.

    Si config_path est None, cherche mcp-forge.yaml dans le répertoire courant.
    Retourne un dict vide si aucun fichier trouvé.
    """
    import yaml

    path: Path | None = None
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Fichier de configuration introuvable : {config_path}")
    else:
        candidate = Path(_DEFAULT_CONFIG_FILE)
        if candidate.exists():
            path = candidate

    if path is None:
        return {}

    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return data


def merge_config(yaml_cfg: dict[str, Any], **cli_flags: Any) -> dict[str, Any]:
    """Fusionne config YAML et flags CLI. Les flags CLI ont la priorité.

    Un flag CLI est considéré comme "non défini" si sa valeur est None
    (pour les optionnels) ou correspond à la valeur par défaut Typer.
    """
    merged = dict(yaml_cfg)
    for key, value in cli_flags.items():
        if value is not None:
            merged[key] = value
    return merged
