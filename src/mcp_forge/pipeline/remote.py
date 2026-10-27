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
import time
import zipfile
from pathlib import Path

import httpx
from rich.console import Console

from mcp_forge.models import DiscoveryResult, ForgeConfig, GeneratedServer, SourceType

console = Console(stderr=True)
from mcp_forge.schemas.payload import DiscoveryPayload

_DEFAULT_API_URL = "https://api.mcp-forge.vulcai.io"
_TIMEOUT = 60.0
# POST /v1/generate s'arrête à 220 s côté API (SYNC_GENERATE_TIMEOUT dans
# api/services/generate.py), sous la coupure à 240 s de l'ingress Azure : le
# client attend un peu plus que cette coupure pour recevoir la réponse,
# quelle qu'elle soit. L'évaluation n'en fait plus partie depuis 0.4.0 : elle
# est attendue ensuite (wait_for_evaluation).
_GENERATE_TIMEOUT = 250.0


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
    if result.source_type == SourceType.CODEBASE:
        # Codebase : souvent volumineuse (enrichissement LLM long). Passe par
        # un job asynchrone, sans la limite de 220 s de POST /v1/generate.
        data = _generate_via_job(api_url, license_key, payload)
        return _download_and_write(data, license_key, config)

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

    _raise_for_status(response, ok=(200,))
    data = response.json()
    return _download_and_write(data, license_key, config)


def _raise_for_status(response: httpx.Response, ok: tuple[int, ...]) -> None:
    if response.status_code == 401:
        raise RemoteError("Clé de licence invalide ou expirée.")
    if response.status_code == 429:
        raise RemoteError("Quota atteint pour votre plan. Contactez contact@vulcai.io.")
    if response.status_code not in ok:
        raise RemoteError(f"Erreur API ({response.status_code}) : {response.text[:200]}")


_JOB_WAIT_TIMEOUT = 900.0


def _generate_via_job(api_url: str, license_key: str, payload: DiscoveryPayload) -> dict:
    """POST /v1/jobs, attente de la fin du job (affichage d'avancement),
    puis GET /v1/jobs/{id}/result : même réponse que POST /v1/generate."""
    headers = {"Authorization": f"Bearer {license_key}"}
    try:
        created = httpx.post(f"{api_url}/v1/jobs", json=payload.model_dump(mode="json"),
                             headers=headers, timeout=_TIMEOUT, verify=True)
    except httpx.ConnectError:
        raise RemoteError(f"Impossible de joindre l'API ({api_url}). Vérifiez votre connexion.")
    except httpx.TimeoutException:
        raise RemoteError("L'API n'a pas accepté la génération dans les délais. Réessayez plus tard.")
    _raise_for_status(created, ok=(200, 202))
    job_id = created.json()["job_id"]

    started = time.monotonic()
    with console.status("Génération du serveur…") as status:
        while True:
            try:
                job = httpx.get(f"{api_url}/v1/jobs/{job_id}", headers=headers, timeout=_TIMEOUT, verify=True)
            except httpx.HTTPError as exc:
                raise RemoteError(f"Impossible de lire l'état de la génération : {exc}")
            _raise_for_status(job, ok=(200,))
            state = job.json().get("status")
            if state == "failed":
                errors = job.json().get("errors") or []
                messages = "; ".join(e.get("message", "") for e in errors) or "raison inconnue"
                raise RemoteError(f"La génération a échoué : {messages}")
            if state == "success":
                break
            elapsed = time.monotonic() - started
            if elapsed > _JOB_WAIT_TIMEOUT:
                raise RemoteError(
                    f"La génération n'est pas terminée après {int(_JOB_WAIT_TIMEOUT)} s (job {job_id}). "
                    "Réessayez plus tard."
                )
            status.update(f"Génération du serveur ({'en file' if state == 'pending' else 'en cours'})… {int(elapsed)} s")
            time.sleep(_POLL_INTERVAL)

    try:
        res = httpx.get(f"{api_url}/v1/jobs/{job_id}/result", headers=headers, timeout=_TIMEOUT, verify=True)
    except httpx.HTTPError as exc:
        raise RemoteError(f"Impossible de lire le résultat de la génération : {exc}")
    _raise_for_status(res, ok=(200,))
    return res.json()


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
    if not bundle_url:
        keys = list(data.keys()) if isinstance(data, dict) else repr(data)[:120]
        raise RemoteError(
            f"La réponse de l'API ne contient pas de bundle_url.\n"
            f"  Clés reçues : {keys}\n"
            f"  success={data.get('success')}, tools_count={data.get('tools_count')}, "
            f"  errors={data.get('errors', [])}"
        )
    files = _download_bundle(bundle_url, license_key, output_dir)

    tools_count = data.get("tools_count", 0)
    eval_report = data.get("eval_report")
    eval_status = data.get("eval_status")
    if eval_status in _PENDING:
        # API asynchrone (0.4.0) : ce qui vient d'être écrit est la version
        # provisoire ; la version finale et sa note arrivent après évaluation.
        if config.wait_for_eval:
            evaluation_url = data.get("evaluation_url") or (
                f"{os.environ.get('FORGE_API_URL', _DEFAULT_API_URL).rstrip('/')}"
                f"/v1/generations/{data.get('generation_id')}/evaluation")
            view = wait_for_evaluation(evaluation_url, license_key)
            if view.get("refined"):
                files = _download_bundle(view["bundle_url"], license_key, output_dir)
            eval_report = view.get("eval_report")
            _print_evaluation(view)
            console.print(f"[green][OK] Version finale écrite dans : {output_dir}[/green]")
        else:
            console.print(f"[yellow]Version provisoire écrite dans : {output_dir}[/yellow] (évaluation en cours)")
            console.print(
                "  Pour récupérer la version finale et sa note :\n"
                f"  mcp-forge status {data.get('generation_id')} --output {output_dir}"
            )
    else:
        console.print(f"[green][OK] Serveur généré dans : {output_dir}[/green]")

    return GeneratedServer(
        server_name=server_name,
        output_dir=str(output_dir),
        files=files,
        tools_count=tools_count,
        success=True,
        eval_report=eval_report,
    )


def _download_bundle(bundle_url: str, license_key: str, output_dir: Path) -> dict[str, str]:
    """Télécharge le bundle ZIP et l'extrait dans output_dir (écrase)."""
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

    files: dict[str, str] = {}
    root = output_dir.resolve()
    buf = io.BytesIO(zip_response.content)
    with zipfile.ZipFile(buf, "r") as zf:
        for name in zf.namelist():
            dest = (output_dir / name).resolve()
            if root not in dest.parents:  # chemin hors du dossier (../, absolu) : ignoré
                continue
            content = zf.read(name).decode("utf-8", errors="replace")
            files[name] = content
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
    return files


_PENDING = ("queued", "running")
_POLL_INTERVAL = 3.0
_EVAL_WAIT_TIMEOUT = 900.0
_STATUS_LABEL = {"queued": "en file", "running": "en cours"}


def get_evaluation(evaluation_url: str, license_key: str) -> dict:
    try:
        resp = httpx.get(evaluation_url, headers={"Authorization": f"Bearer {license_key}"},
                         timeout=_TIMEOUT, verify=True)
    except httpx.HTTPError as exc:
        raise RemoteError(f"Impossible de lire l'état de l'évaluation : {exc}")
    if resp.status_code == 404:
        raise RemoteError("Génération introuvable (expirée, ou d'un autre compte).")
    if resp.status_code != 200:
        raise RemoteError(f"Erreur API ({resp.status_code}) : {resp.text[:200]}")
    return resp.json()


def wait_for_evaluation(
    evaluation_url: str,
    license_key: str,
    *,
    poll_interval: float = _POLL_INTERVAL,
    timeout: float = _EVAL_WAIT_TIMEOUT,
) -> dict:
    """Attend la fin de l'évaluation asynchrone, avec affichage d'avancement.
    Retourne la vue finale ; lève RemoteError au-delà de `timeout`."""
    started = time.monotonic()
    with console.status("Évaluation du serveur généré…") as status:
        while True:
            view = get_evaluation(evaluation_url, license_key)
            if view.get("status") not in _PENDING:
                return view
            elapsed = time.monotonic() - started
            if elapsed > timeout:
                raise RemoteError(
                    f"L'évaluation n'est pas terminée après {int(timeout)} s. La version provisoire est "
                    "écrite ; relancez plus tard « mcp-forge status <id> --output <dossier> »."
                )
            attempt = view.get("attempts") or 0
            retry = " — relance" if attempt > 1 else ""
            status.update(f"Évaluation {_STATUS_LABEL.get(view['status'], view['status'])}{retry}… {int(elapsed)} s")
            time.sleep(poll_interval)


def _print_evaluation(view: dict) -> None:
    st = view.get("status")
    if st == "done":
        refined = " (corrigée après évaluation)" if view.get("refined") else ""
        console.print(f"[bold]Note d'évaluation : {view.get('score')}/10[/bold]{refined}")
    elif st == "failed":
        console.print("[yellow]L'évaluation a échoué : la version livrée n'est pas notée.[/yellow]")
    elif st == "skipped":
        reason = {"EVAL_DAILY_LIMIT": "limite journalière d'évaluations atteinte"}.get(view.get("error") or "", view.get("error") or "")
        console.print(f"[dim]Serveur non évalué{f' ({reason})' if reason else ''}.[/dim]")
