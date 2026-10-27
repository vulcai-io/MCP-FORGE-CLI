"""
Tests de sécurité DYNAMIQUES d'un serveur généré, avant l'évaluation LLM
(2026-10-13) — aucun appel LLM.

Mesuré sur eval_benchmark/ : même avec une checklist obligatoire, le LLM
manquait des failles qui ne se voient qu'en suivant l'exécution (requête
MCP sans token acceptée, token MCP transmis à l'API cible : 4 fois sur 4).
On EXÉCUTE donc la couche HTTP du serveur, en mémoire (Starlette
TestClient, aucun port ouvert), dans un sous-processus isolé :
  - réseau coupé au niveau des sockets (loopback seul), aucun programme
    externe, API cible remplacée par une fausse API qui enregistre les
    en-têtes reçus (voir mcp_forge/_dynamic_runner.py) ;
  - environnement vidé des vraies clés ; secrets de test aléatoires ;
  - limites de CPU (60 s) et de mémoire (1 Gio) : setrlimit en POSIX,
    Job Object sous Windows ; plus un délai d'horloge.

Chaque résultat remplit une ligne de la checklist sécurité : "ok",
"probleme" (bug majeur confirmé, plafond), "non_verifiable" (avec la
raison) ou "non_applicable".
"""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

_RUNNER = Path(__file__).with_name("_dynamic_runner.py")
_SECRET_ENV = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE)
_CPU_SECONDS = 60
_MEMORY_BYTES = 1 << 30
DYNAMIC_POINTS = (
    "all_mcp_routes_authenticated", "token_header_only", "login_page_escaped", "origin_validated",
    "no_token_passthrough", "token_audience_and_expiry_checked",
)


def _posix_limits() -> None:  # pragma: no cover - exécuté dans l'enfant POSIX
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (_CPU_SECONDS, _CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (_MEMORY_BYTES, _MEMORY_BYTES))


def _windows_job(process: subprocess.Popen):
    """Place le processus dans un Job Object limité (CPU, mémoire, tué à la
    fermeture du job). Renvoie le handle du job, à garder ouvert."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    job = kernel32.CreateJobObjectW(None, None)
    info = ExtendedLimits()
    # PROCESS_TIME | PROCESS_MEMORY | KILL_ON_JOB_CLOSE
    info.BasicLimitInformation.LimitFlags = 0x2 | 0x100 | 0x2000
    info.BasicLimitInformation.PerProcessUserTimeLimit = _CPU_SECONDS * 10_000_000  # unités de 100 ns
    info.ProcessMemoryLimit = _MEMORY_BYTES
    kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
    kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle)))
    return job


def _failure_reason(stderr: str, returncode: int) -> str:
    """Cause d'un lancement raté : la dernière ligne d'une trace d'erreur
    (l'exception), sinon le code de sortie. Pas « la dernière ligne de
    stderr », qui peut être un simple avertissement."""
    text = stderr.strip()
    if "Traceback (most recent call last)" in text:
        tail = text.split("Traceback (most recent call last)")[-1].strip().splitlines()
        if tail:
            return tail[-1]
    return f"code de sortie {returncode}"


def run_dynamic_tests(code: str, timeout: float = 90.0) -> dict:
    """{"results": [...], "limits": ...} ou {"error": raison}."""
    if "_build_http_app" not in code:
        return {"error": "pas de couche HTTP générée par mcp-forge (_build_http_app absent)"}
    token = secrets.token_urlsafe(24)
    env = {k: v for k, v in os.environ.items() if not _SECRET_ENV.search(k)}
    for var in ("MCP_PROXY_MODE", "OAUTH_ALLOWED_REDIRECT_HOSTS", "OAUTH_ALLOWED_REDIRECT_URIS", "MCP_ALLOWED_ORIGINS"):
        env.pop(var, None)
    env.update({"MCP_SERVER_TOKEN": token, "MCP_SERVER_URL": "https://mcp.test.example",
                "BEARER_TOKEN": "downstream-test-key"})
    with tempfile.TemporaryDirectory(prefix="mcpforge_dyn_") as tmp:
        server = Path(tmp) / "server.py"
        server.write_text(code, encoding="utf-8")
        config = Path(tmp) / "config.json"
        config.write_text(json.dumps({"server_path": str(server), "mcp_token": token,
                                      "server_url": "https://mcp.test.example"}), encoding="utf-8")
        kwargs = {"cwd": tmp, "env": env, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
        if os.name == "posix":
            kwargs["preexec_fn"] = _posix_limits
            limits = f"setrlimit CPU {_CPU_SECONDS} s, mémoire 1 Gio"
        else:
            limits = f"Job Object CPU {_CPU_SECONDS} s, mémoire 1 Gio"
        # -W ignore : un avertissement (ex. dépréciation émise par Starlette 1.x
        # à l'import de TestClient) n'est pas une erreur du serveur évalué
        process = subprocess.Popen([sys.executable, "-I", "-W", "ignore", str(_RUNNER), str(config)], **kwargs)
        job = _windows_job(process) if os.name == "nt" else None
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            return {"error": f"délai dépassé ({timeout:.0f} s)", "limits": limits}
        finally:
            if job:
                import ctypes
                ctypes.WinDLL("kernel32").CloseHandle(job)
    lines = [line for line in stdout.strip().splitlines() if line.startswith("{")]
    if not lines:
        reason = _failure_reason(stderr, process.returncode)
        return {"error": f"le serveur n'a pas pu être lancé : {reason[:300]}", "limits": limits}
    data = json.loads(lines[-1])
    data["limits"] = limits
    return data


def checklist_items(dynamic: dict) -> list[dict]:
    """Lignes de checklist issues des tests dynamiques (marquées
    `source: test_dynamique` ; un "probleme" est un bug confirmé)."""
    if dynamic.get("error"):
        return [{"point": p, "statut": "non_verifiable", "preuve": f"test dynamique impossible : {dynamic['error']}",
                 "source": "test_dynamique"} for p in DYNAMIC_POINTS]
    items = []
    for res in dynamic.get("results", []):
        items.append({**res, "source": "test_dynamique", "cap_eligible": res["statut"] == "probleme"})
    return items


def facts_text(dynamic: dict) -> str:
    """Résultats présentés au LLM comme des faits établis par l'outil."""
    if dynamic.get("error"):
        return f"Dynamic security tests could not run: {dynamic['error']}."
    lines = [f"- {r['point']}: {r['statut']} — {r['preuve']}" for r in dynamic.get("results", [])]
    return "Dynamic security tests executed by the tool (authoritative):\n" + "\n".join(lines)
