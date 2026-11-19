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
from pydantic import ValidationError
from rich.console import Console

from mcp_forge.models import DiscoveryResult, ForgeConfig, GeneratedServer, SourceType
from mcp_forge.schemas.payload import DiscoveryPayload

console = Console(stderr=True)

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


def _payload_error_message(exc: ValidationError) -> str:
    """Message lisible pour un payload refusé par sa propre validation."""
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(x) for x in first.get("loc", ())) or "payload"
    return (f"The source exceeds an API limit ({where}: {first.get('msg', 'invalid')}).\n"
            "  Generate fewer operations: --include-tags / --include-paths "
            "(or --exclude-tags / --exclude-paths).")


def run_remote(result: DiscoveryResult, config: ForgeConfig) -> GeneratedServer:
    """Envoie le payload à l'API Azure et écrit les fichiers générés localement."""
    api_url = os.environ.get("FORGE_API_URL", _DEFAULT_API_URL).rstrip("/")
    license_key = os.environ.get("FORGE_LICENSE_KEY", "")

    if not license_key:
        raise RemoteError(
            "FORGE_LICENSE_KEY missing.\n"
            "  Get your key at https://mcp-forge.vulcai.io, then:\n"
            "  mcp-forge set-license mfg_live_...\n"
            "  (Run again from the folder that holds your .env)"
        )

    try:
        payload = DiscoveryPayload.from_discovery_result(
            result, instructions=config.server_instructions, tool_instructions=config.tool_instructions,
            use_llm=not config.no_llm, no_output_schema=config.no_output_schema)
    except ValidationError as exc:
        # Dernier recours : la découverte respecte déjà les limites du payload
        # (mcp_forge/discovery/limits.py) ; jamais de trace Python brute
        raise RemoteError(_payload_error_message(exc)) from exc
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
        raise RemoteError(f"Could not reach the API ({api_url}). Check your connection.") from None
    except httpx.TimeoutException:
        raise RemoteError(
            f"The API did not respond in time ({int(_GENERATE_TIMEOUT)} s). "
            "Try again later."
        ) from None

    _raise_for_status(response, ok=(200,))
    data = response.json()
    return _download_and_write(data, license_key, config)


def _api_detail(response: httpx.Response) -> str | None:
    """Champ `detail` (texte) d'une réponse d'erreur de l'API : une ligne, sans caractère de
    contrôle, 500 caractères au plus ; None s'il manque."""
    try:
        detail = response.json().get("detail")
    except Exception:
        return None
    if not isinstance(detail, str):
        return None
    text = " ".join("".join(c if c.isprintable() else " " for c in detail).split())
    return text[:500] or None


def _raise_for_status(response: httpx.Response, ok: tuple[int, ...]) -> None:
    if response.status_code == 401:
        raise RemoteError("Invalid or expired license key.")
    if response.status_code == 429:
        # Message de l'API tel quel (limite journalière de générations, quota de domaines, limite
        # de débit) : il dit lequel et quand réessayer (0.4.4 ; avant, toujours « quota »)
        raise RemoteError(_api_detail(response) or "Too many requests (HTTP 429). Contact contact@vulcai.io.")
    if response.status_code not in ok:
        raise RemoteError(f"API error ({response.status_code}): {response.text[:200]}")


_JOB_WAIT_TIMEOUT = 900.0


def _generate_via_job(api_url: str, license_key: str, payload: DiscoveryPayload) -> dict:
    """POST /v1/jobs, attente de la fin du job (affichage d'avancement),
    puis GET /v1/jobs/{id}/result : même réponse que POST /v1/generate."""
    headers = {"Authorization": f"Bearer {license_key}"}
    try:
        created = httpx.post(f"{api_url}/v1/jobs", json=payload.model_dump(mode="json"),
                             headers=headers, timeout=_TIMEOUT, verify=True)
    except httpx.ConnectError:
        raise RemoteError(f"Could not reach the API ({api_url}). Check your connection.") from None
    except httpx.TimeoutException:
        raise RemoteError("The API did not accept the generation in time. Try again later.") from None
    _raise_for_status(created, ok=(200, 202))
    job_id = created.json()["job_id"]

    started = time.monotonic()
    with console.status("Generating the server…") as status:
        while True:
            try:
                job = httpx.get(f"{api_url}/v1/jobs/{job_id}", headers=headers, timeout=_TIMEOUT, verify=True)
            except httpx.HTTPError as exc:
                raise RemoteError(f"Could not read the generation status: {exc}") from exc
            _raise_for_status(job, ok=(200,))
            state = job.json().get("status")
            if state == "failed":
                errors = job.json().get("errors") or []
                messages = "; ".join(e.get("message", "") for e in errors) or "unknown reason"
                raise RemoteError(f"The generation failed: {messages}")
            if state == "success":
                break
            elapsed = time.monotonic() - started
            if elapsed > _JOB_WAIT_TIMEOUT:
                raise RemoteError(
                    f"The generation is not finished after {int(_JOB_WAIT_TIMEOUT)} s (job {job_id}). "
                    "Try again later."
                )
            status.update(f"Generating the server ({'queued' if state == 'pending' else 'running'})… {int(elapsed)} s")
            time.sleep(_POLL_INTERVAL)

    try:
        res = httpx.get(f"{api_url}/v1/jobs/{job_id}/result", headers=headers, timeout=_TIMEOUT, verify=True)
    except httpx.HTTPError as exc:
        raise RemoteError(f"Could not read the generation result: {exc}") from exc
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
            f"The API response has no bundle_url.\n"
            f"  Keys received: {keys}\n"
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
            console.print(f"[green][OK] Final version written to: {output_dir}[/green]")
        else:
            console.print(f"[yellow]Provisional version written to: {output_dir}[/yellow] (evaluation running)")
            console.print(
                "  To get the final version and its score:\n"
                f"  mcp-forge status {data.get('generation_id')} --output {output_dir}"
            )
    else:
        console.print(f"[green][OK] Server generated in: {output_dir}[/green]")

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
        raise RemoteError("Could not download the ZIP bundle. Check your connection.") from None
    except httpx.TimeoutException:
        raise RemoteError("Timed out while downloading the ZIP bundle.") from None

    if zip_response.status_code != 200:
        raise RemoteError(
            f"Error while downloading the bundle ({zip_response.status_code})."
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
_STATUS_LABEL = {"queued": "queued", "running": "running"}


def get_evaluation(evaluation_url: str, license_key: str) -> dict:
    try:
        resp = httpx.get(evaluation_url, headers={"Authorization": f"Bearer {license_key}"},
                         timeout=_TIMEOUT, verify=True)
    except httpx.HTTPError as exc:
        raise RemoteError(f"Could not read the evaluation status: {exc}") from exc
    if resp.status_code == 404:
        raise RemoteError("Generation not found (expired, or from another account).")
    if resp.status_code != 200:
        raise RemoteError(f"API error ({resp.status_code}): {resp.text[:200]}")
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
    with console.status("Evaluating the generated server…") as status:
        while True:
            view = get_evaluation(evaluation_url, license_key)
            if view.get("status") not in _PENDING:
                return view
            elapsed = time.monotonic() - started
            if elapsed > timeout:
                raise RemoteError(
                    f"The evaluation is not finished after {int(timeout)} s. The provisional version is "
                    "written; run \"mcp-forge status <id> --output <folder>\" later."
                )
            attempt = view.get("attempts") or 0
            retry = ", retrying" if attempt > 1 else ""
            status.update(f"Evaluation {_STATUS_LABEL.get(view['status'], view['status'])}{retry}… {int(elapsed)} s")
            time.sleep(poll_interval)


def _print_evaluation(view: dict) -> None:
    st = view.get("status")
    if st == "done":
        refined = " (fixed after evaluation)" if view.get("refined") else ""
        console.print(f"[bold]Evaluation score: {view.get('score')}/10[/bold]{refined}")
    elif st == "failed":
        console.print("[yellow]The evaluation failed: the delivered version has no score.[/yellow]")
    elif st == "skipped":
        reason = {"EVAL_DAILY_LIMIT": "daily evaluation limit reached",
                  "LLM_DISABLED": "LLM evaluation off (--no-llm)"}.get(view.get("error") or "",
                                                                             view.get("error") or "")
        console.print(f"[dim]Server not evaluated{f' ({reason})' if reason else ''}.[/dim]")
