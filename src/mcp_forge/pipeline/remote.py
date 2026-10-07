"""
Pipeline distant : envoie le DiscoveryPayload à l'API Azure et récupère
le bundle ZIP via bundle_url.

Variables d'environnement :
  FORGE_API_URL       URL de l'API (défaut : https://api.mcp-forge.vulcai.io)
  FORGE_LICENSE_KEY   Clé de licence (format : mfg_live_<uuid>)
"""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import httpx
from rich.console import Console

from mcp_forge.models import DiscoveryResult, ForgeConfig, GeneratedServer

console = Console(stderr=True)
from mcp_forge.schemas.payload import DiscoveryPayload

_DEFAULT_API_URL = "https://api.mcp-forge.vulcai.io"
_TIMEOUT = 60.0
# La génération serveur peut enchaîner eval + raffinement + ré-évaluation (jusqu'à
# 300s côté API, cf. _GENERATE_TIMEOUT dans api/services/generate.py) — le client
# doit attendre au moins aussi longtemps, sans quoi il abandonne alors que le
# serveur a fini par réussir (constaté : 60-90s en pratique quand Groq échoue et
# que le raffinement bascule sur Anthropic).
_GENERATE_TIMEOUT = 320.0


class RemoteError(Exception):
    """Erreur levée par le pipeline distant (affichée après la fin du spinner)."""


def run_remote(result: DiscoveryResult, config: ForgeConfig) -> GeneratedServer:
    """Envoie le payload à l'API Azure et écrit les fichiers générés localement."""
    api_url = os.environ.get("FORGE_API_URL", _DEFAULT_API_URL).rstrip("/")
    license_key = os.environ.get("FORGE_LICENSE_KEY", "")

    if not license_key:
        raise RemoteError(
            "FORGE_LICENSE_KEY manquante.\n"
            "  Obtenez votre clé sur https://mcp-forge.vulcai.io puis :\n"
            "  mcp-forge set-license mfg_live_...\n"
            "  (Relancez depuis le dossier où se trouve votre .env)"
        )

    payload = DiscoveryPayload.from_discovery_result(result)

    try:
        response = httpx.post(
            f"{api_url}/v1/generate",
            json=payload.model_dump(mode="json"),
            headers={
                "Authorization": f"Bearer {license_key}",
                "Content-Type": "application/json",
            },
            timeout=_GENERATE_TIMEOUT,
            verify=True,
        )
    except httpx.ConnectError:
        raise RemoteError(f"Impossible de joindre l'API ({api_url}). Vérifiez votre connexion.")
    except httpx.TimeoutException:
        raise RemoteError(
            f"L'API n'a pas répondu dans les délais ({int(_GENERATE_TIMEOUT)}s). "
            "Réessayez plus tard."
        )

    if response.status_code == 401:
        raise RemoteError("Clé de licence invalide ou expirée.")
    if response.status_code == 429:
        raise RemoteError("Quota atteint pour votre plan. Contactez contact@vulcai.io.")
    if response.status_code != 200:
        raise RemoteError(f"Erreur API ({response.status_code}) : {response.text[:200]}")

    data = response.json()
    return _download_and_write(data, license_key, config)


def _download_and_write(data: dict, license_key: str, config: ForgeConfig) -> GeneratedServer:
    """Télécharge le bundle ZIP via bundle_url et extrait les fichiers localement.

    Format attendu de l'API :
      { "success": bool, "server_name": str, "tools_count": int,
        "bundle_url": "https://api.mcp-forge.vulcai.io/v1/generations/{id}/download" }
    """
    api_server_name = data.get("server_name", "mcp_server")
    if config.server_name:
        # --name fourni par l'utilisateur → toujours déterministe
        folder_name = config.server_name
    else:
        # Dériver du hostname de la source pour la reproductibilité CI/CD
        # ex: "https://petstore.swagger.io/v2" → "petstore_swagger_io"
        import re
        from urllib.parse import urlparse
        raw = config.source or api_server_name
        try:
            hostname = urlparse(raw).hostname or raw
        except Exception:
            hostname = raw
        folder_name = re.sub(r"[^a-z0-9]+", "_", hostname.lower()).strip("_") or api_server_name
    server_name = api_server_name  # nom Python interne (reste LLM-généré)
    output_dir = Path(config.output_dir) / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    bundle_url: str | None = data.get("bundle_url")
    files: dict[str, str] = {}

    if bundle_url:
        try:
            zip_response = httpx.get(
                bundle_url,
                headers={"Authorization": f"Bearer {license_key}"},
                timeout=_TIMEOUT,
                verify=True,
            )
        except httpx.ConnectError:
            raise RemoteError("Impossible de télécharger le bundle ZIP. Vérifiez votre connexion.")
        except httpx.TimeoutException:
            raise RemoteError("Timeout lors du téléchargement du bundle ZIP.")

        if zip_response.status_code != 200:
            raise RemoteError(
                f"Erreur lors du téléchargement du bundle ({zip_response.status_code})."
            )

        buf = io.BytesIO(zip_response.content)
        with zipfile.ZipFile(buf, "r") as zf:
            for name in zf.namelist():
                content = zf.read(name).decode("utf-8", errors="replace")
                files[name] = content
                dest = output_dir / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
    else:
        keys = list(data.keys()) if isinstance(data, dict) else repr(data)[:120]
        raise RemoteError(
            f"La réponse de l'API ne contient pas de bundle_url.\n"
            f"  Clés reçues : {keys}\n"
            f"  success={data.get('success')}, tools_count={data.get('tools_count')}, "
            f"  errors={data.get('errors', [])}"
        )

    tools_count = data.get("tools_count", 0)
    console.print(f"[green][OK] Serveur généré dans : {output_dir}[/green]")

    return GeneratedServer(
        server_name=server_name,
        output_dir=str(output_dir),
        files=files,
        tools_count=tools_count,
        success=True,
        eval_report=data.get("eval_report"),
    )
