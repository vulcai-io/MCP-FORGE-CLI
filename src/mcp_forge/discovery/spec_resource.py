"""
Resource « spec » des serveurs OpenAPI (lot D, D6, 2026-11-01).

Le serveur généré expose une copie de la spec (resource MCP
`spec://openapi`), faite au moment de la génération (décision du PO,
2026-10-30) : jamais téléchargée par le serveur. Copie **nettoyée** :
- exemples retirés (`example`, `examples`) : ils contiennent souvent de
  vraies données ;
- extensions `x-*` retirées : elles peuvent porter des URL ou des
  intégrations internes (ex. `x-amazon-apigateway-integration`) ;
- `servers` internes retirés (localhost, adresses IP privées ou de
  boucle locale, noms en `.local`, `.internal`, `.lan`, `.corp`, `.intranet`,
  `.localhost`, ou sans point) ; en v2, `host` interne retiré ;
- caractères invisibles retirés de tous les textes.
Taille bornée (MAX_SPEC_BYTES une fois sérialisée) : au-delà, pas de
resource (None).

Index allégé (resource `spec://openapi/index`, décision du PO,
2026-11-01), servi pour tout serveur OpenAPI : la liste des opérations
(méthode, chemin, operationId, résumé, nom du tool généré), sans les
schémas. Mêmes nettoyages ; un résumé qui contient un motif
d'empoisonnement (mêmes motifs que l'évaluateur) est retiré, l'entrée
reste. Borné à MAX_SPEC_BYTES : au-delà, résumés retirés, puis pas de
resource.
"""
from __future__ import annotations

import ipaddress
import json
from typing import Any
from urllib.parse import urlparse

from mcp_forge.instructions import visible

MAX_SPEC_BYTES = 1_000_000
_DROPPED_KEYS = {"example", "examples"}
_INTERNAL_SUFFIXES = (".local", ".internal", ".lan", ".corp", ".intranet", ".localhost", ".home", ".localdomain")


def is_internal_host(host: str) -> bool:
    host = (host or "").strip().lower().split(":")[0].strip("[]")
    if not host:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified
    except ValueError:
        pass
    return host == "localhost" or "." not in host or host.endswith(_INTERNAL_SUFFIXES)


def _public_server(server: Any) -> bool:
    if not isinstance(server, dict):
        return False
    url = str(server.get("url") or "")
    if "{" in url:  # variables de serveur : on ne peut pas juger, on retire
        return False
    parsed = urlparse(url)
    if not parsed.netloc:  # URL relative (« /api/v3 ») : sans hôte, rien d'interne
        return url.startswith("/") or url == ""
    return parsed.scheme in ("http", "https") and not is_internal_host(parsed.hostname or "")


def _clean(node: Any) -> Any:
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            key = visible(str(key))
            if key in _DROPPED_KEYS or key.lower().startswith("x-"):
                continue
            if key == "servers" and isinstance(value, list):
                value = [s for s in value if _public_server(s)]
                if not value:
                    continue
            out[key] = _clean(value)
        return out
    if isinstance(node, list):
        return [_clean(v) for v in node]
    if isinstance(node, str):
        return visible(node)
    return node


def clean_spec(spec: Any) -> dict | None:
    """Copie nettoyée de la spec, ou None (pas un objet, ou trop grosse)."""
    if not isinstance(spec, dict):
        return None
    cleaned = _clean(spec)
    if "host" in cleaned and is_internal_host(str(cleaned.get("host"))):
        del cleaned["host"]
    try:
        size = len(json.dumps(cleaned, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return None
    return cleaned if size <= MAX_SPEC_BYTES else None


# ----------------------------------------------------------------------
# Index allégé : spec://openapi/index
# ----------------------------------------------------------------------

MAX_INDEX_OPERATIONS = 5000
MAX_SUMMARY = 200
_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
_INDEX_FIELDS = (("method", 10), ("path", 500), ("operationId", 200), ("summary", MAX_SUMMARY), ("tool", 128))


def _index_entry(raw: Any) -> dict[str, str] | None:
    from mcp_forge.eval_annotations import _poison_findings

    if not isinstance(raw, dict):
        return None
    entry = {}
    for field, limit in _INDEX_FIELDS:
        value = raw.get(field)
        if isinstance(value, str) and visible(value).strip():
            entry[field] = visible(value).strip()[:limit]
    entry["method"] = entry.get("method", "").upper()
    if entry["method"] not in _METHODS or not entry.get("path"):
        return None
    if "summary" in entry and _poison_findings(entry["summary"]):
        del entry["summary"]
    return entry


def clean_index(raw: Any) -> list[dict[str, str]]:
    """Entrées valides de l'index (au plus MAX_INDEX_OPERATIONS) ; les
    autres sont écartées."""
    if not isinstance(raw, list):
        return []
    entries = (_index_entry(item) for item in raw[:MAX_INDEX_OPERATIONS])
    return [e for e in entries if e is not None]


def build_index(spec: Any) -> list[dict[str, str]]:
    """Opérations de la spec, dans l'ordre des chemins."""
    paths = spec.get("paths") if isinstance(spec, dict) else None
    if not isinstance(paths, dict):
        return []
    raw = []
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method, operation in item.items():
            # Clés qui ne sont pas des méthodes (parameters, x-*) : écartées par clean_index
            if isinstance(operation, dict):
                raw.append({"method": str(method), "path": str(path), "operationId": operation.get("operationId"),
                            "summary": operation.get("summary")})
    return clean_index(raw)


def index_document(entries: list[dict[str, str]]) -> dict[str, Any] | None:
    """Document servi par la resource, borné à MAX_SPEC_BYTES : résumés
    retirés d'abord, puis None."""
    if not entries:
        return None
    document: dict[str, Any] = {"operations": entries}
    if len(json.dumps(document, ensure_ascii=False).encode("utf-8")) <= MAX_SPEC_BYTES:
        return document
    document = {"summaries_removed": True,
                "operations": [{k: v for k, v in e.items() if k != "summary"} for e in entries]}
    if len(json.dumps(document, ensure_ascii=False).encode("utf-8")) <= MAX_SPEC_BYTES:
        return document
    return None
