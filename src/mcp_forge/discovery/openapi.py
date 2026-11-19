"""
Discovery à partir d'une spec OpenAPI/Swagger (fichier local ou URL).
Supporte OpenAPI 2.x (Swagger) et 3.x.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import yaml
from rich.console import Console
from rich.markup import escape

from mcp_forge.discovery import download
from mcp_forge.discovery.limits import (
    EXCLUDED_BY_FILTER,
    EXCLUDED_OVER_LIMIT,
    EXCLUDED_TOO_MANY_PARAMETERS,
    MAX_TOOLS,
    OperationFilter,
    group_options,
    top_tags,
)
from mcp_forge.discovery.response_schema import openapi_response_schema
from mcp_forge.discovery.spec_resource import build_index, clean_spec
from mcp_forge.models import (
    AuthScheme,
    AuthType,
    DiscoveredTool,
    DiscoveryResult,
    ForgeConfig,
    ParameterType,
    SourceType,
    ToolParameter,
)

console = Console()

_TYPE_MAP: dict[str, ParameterType] = {
    "string": ParameterType.STRING,
    "integer": ParameterType.INTEGER,
    "number": ParameterType.NUMBER,
    "boolean": ParameterType.BOOLEAN,
    "array": ParameterType.ARRAY,
    "object": ParameterType.OBJECT,
}


# Utilitaires de robustesse (lot A, recommandation 2 du rapport du 2026-10-24 : 170 specs
# de l'annuaire APIs.guru faisaient planter la découverte)


def _as_dict(obj: Any) -> dict:
    """Un schéma qui n'est pas un objet (booléen JSON Schema, liste…) compte pour vide."""
    return obj if isinstance(obj, dict) else {}


def _text(value: Any) -> str:
    """Texte d'un champ que YAML peut lire comme autre chose (version 2021-01-01 → date,
    swagger: 2.0 → nombre)."""
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _json_type(schema: dict) -> ParameterType:
    """Type d'un schéma ; `type: [integer, "null"]` (OpenAPI 3.1) donne integer."""
    kind = schema.get("type", "string")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "string")
    return _TYPE_MAP.get(kind, ParameterType.STRING) if isinstance(kind, str) else ParameterType.STRING


def _enum_text(values: Any) -> list[str]:
    """Valeurs permises en texte JSON (`[10, 50]` → `["10", "50"]`, `true` → `"true"`) :
    le contrat entre la CLI et l'API (enum_values: list[str]) ne change pas. `null` n'est pas
    un choix que l'appelant envoie : retiré."""
    if not isinstance(values, list):
        return []
    return [v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
            for v in values if v is not None]


def _looks_like_spec(data: Any) -> bool:
    """Document OpenAPI ou Swagger : un objet avec `openapi`, `swagger` ou `paths`."""
    return isinstance(data, dict) and any(k in data for k in ("openapi", "swagger", "paths"))


def _load_yaml(content: str) -> Any:
    """YAML par le chargeur C de PyYAML (environ 5 fois plus rapide : 183 s contre 920 s sur
    l'annuaire APIs.guru), le chargeur Python en secours : le C refuse quelques fichiers que
    le Python accepte. Lot A, recommandation 6."""
    loader = getattr(yaml, "CSafeLoader", None)
    if loader is not None:
        try:
            return yaml.load(content, Loader=loader)  # nosec B506 - CSafeLoader est un chargeur sûr
        except yaml.YAMLError:
            pass
    return yaml.safe_load(content)


_FORM_MEDIA = ("application/x-www-form-urlencoded", "multipart/form-data")


def _pick_body_media(content: dict) -> str:
    """Type de média du corps à décrire : application/json d'abord, puis tout type JSON
    (application/vnd.api+json, application/merge-patch+json, application/json;
    charset=utf-8…), puis les formulaires ; "" sinon. Lot A, recommandation 5 : 10 843
    paramètres de corps d'un autre type de média JSON n'étaient pas lus."""
    if "application/json" in content:
        return "application/json"
    for media in content:
        if "json" in str(media).lower():
            return media
    for media in _FORM_MEDIA:
        if media in content:
            return media
    return ""


class OpenAPIDiscovery:
    def __init__(self, config: ForgeConfig, probe: bool = False,
                 url_guard: Callable[[str], None] | None = None):
        self.config = config
        self.source = config.source
        # probe : recherche d'une spec publiée par un site web (mcp_forge/discovery/web.py) ;
        # rien n'est affiché tant qu'aucune spec n'est trouvée
        self.probe = probe
        # Contrôle de chaque URL essayée (garde anti-SSRF de l'API, passée par web.py)
        self.url_guard = url_guard
        # Spec déjà lue (page Swagger UI ou Redoc, web.py) : pas de nouveau téléchargement
        self.preloaded_spec: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Point d'entrée
    # ------------------------------------------------------------------

    def discover(self) -> DiscoveryResult:
        if not self.probe:
            console.print("[bold]>> Loading the OpenAPI spec...[/bold]")
        spec = self._load_spec()

        openapi_version = _text(spec.get("openapi", spec.get("swagger", "")))
        is_v2 = openapi_version.startswith("2")

        info = _as_dict(spec.get("info"))
        base_url = self._extract_base_url(spec, is_v2)

        result = DiscoveryResult(
            source_type=SourceType.OPENAPI,
            source_url=self.source if self.source.startswith("http") else None,
            source_path=self.source if not self.source.startswith("http") else None,
            title=_text(info.get("title")) or "API",
            description=_text(info.get("description")),
            version=_text(info.get("version")),
            base_url=base_url,
        )

        paths = spec.get("paths", {})
        console.print(f"[dim]  {len(paths)} endpoint(s) found[/dim]")

        operations = [
            (path, method.upper(), operation)
            for path, path_item in paths.items() if isinstance(path_item, dict)
            for method, operation in path_item.items()
            if method.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
            and isinstance(operation, dict)
        ]
        # Noms calculés sur toutes les opérations de la spec, avant le filtre et la limite :
        # le nom d'une opération ne dépend ni de l'ordre de la spec ni de --include-tags
        names = self._unique_names(operations)
        excluded = self._select_operations(operations)
        for path, method, operation in operations:
            tool = self._operation_to_tool(
                path=path,
                method=method,
                operation=operation,
                spec=spec,
                base_url=base_url,
                is_v2=is_v2,
                path_item=paths.get(path) or {},
            )
            tool.name = names[(method, path)]
            if group_options(tool):
                result.tools.append(tool)
            else:
                excluded[EXCLUDED_TOO_MANY_PARAMETERS] = excluded.get(EXCLUDED_TOO_MANY_PARAMETERS, 0) + 1
                console.print(f"[yellow]  ⚠ {method} {path} removed: too many required parameters[/yellow]")
        # Couverture : opérations de la spec, tools générés, retirées et pourquoi
        result.metadata["coverage"] = {"discovered": len(result.tools) + sum(excluded.values()),
                                       "generated": len(result.tools), "excluded": excluded}

        result.auth_schemes = self._extract_auth_schemes(spec, is_v2)
        # Copie nettoyée de la spec, servie par le serveur généré (resource
        # spec://openapi, lot D, D6) ; None si trop grosse
        spec_document = clean_spec(spec)
        if spec_document is not None:
            result.metadata["spec_document"] = spec_document
        # Index allégé des opérations (resource spec://openapi/index), même
        # quand la spec est trop grosse pour être copiée
        spec_index = build_index(spec)
        if spec_index:
            result.metadata["spec_index"] = spec_index
        console.print(f"[green][OK] {len(result.tools)} MCP tool(s) extracted[/green]")
        return result

    def _base_name(self, method: str, path: str, operation: dict) -> str:
        """Nom du tool : operationId, sinon méthode + chemin normalisé."""
        op_id = _text(operation.get("operationId"))
        if op_id:
            return self._normalize_name(op_id)
        # Sans operationId : méthode + chemin, paramètres de chemin gardés
        # (GET /pets/{petId} → get_pets_pet_id), sinon GET /pets et
        # GET /pets/{petId} donnaient le même nom (2026-10-30).
        return self._normalize_name(f"{method}_{re.sub(r'[{}]', '_', path)}")

    @classmethod
    def _path_name(cls, method: str, path: str) -> str:
        """Nom tiré de la méthode et du chemin, pour départager deux opérations au même
        nom : GET /users/{id} → get_users_by_id."""
        words = [method.lower()]
        for segment in path.split("/"):
            param = re.fullmatch(r"\{([^}]+)\}", segment)
            words.append(f"by_{param.group(1)}" if param else re.sub(r"[{}]", "_", segment))
        return cls._normalize_name("_".join(w for w in words if w))

    def _unique_names(self, operations: list[tuple[str, str, dict]]) -> dict[tuple[str, str], str]:
        """Nom unique de chaque opération (méthode, chemin), indépendant de leur ordre
        (lot A, demande du PO du 2026-11-16 : un suffixe _2 donné dans l'ordre de la spec
        change si la spec est réordonnée ou si une opération est ajoutée avant).

        1. Le nom de base (operationId, sinon méthode + chemin).
        2. Toutes les opérations d'un nom en double prennent le nom tiré de leur chemin
           (GET /users/{id} → get_users_by_id) ; aucune ne garde le nom commun.
        3. Si deux de ces noms se rejoignent encore (/a-b et /a_b), chacune reçoit
           « _ » et 8 caractères de l'empreinte SHA-256 de « MÉTHODE chemin »."""
        base = {(method, path): self._base_name(method, path, op) for path, method, op in operations}
        counts = Counter(base.values())
        names = {key: name if counts[name] == 1 else self._path_name(*key) for key, name in base.items()}
        renamed = {key for key, name in base.items() if counts[name] > 1}
        counts = Counter(names.values())
        for key in renamed:
            if counts[names[key]] > 1:
                digest = hashlib.sha256(f"{key[0]} {key[1]}".encode()).hexdigest()[:8]
                names[key] = f"{names[key]}_{digest}"
        return names

    def _select_operations(self, operations: list[tuple[str, str, dict]]) -> dict[str, int]:
        """Applique le filtre (tags, chemins) puis la limite de MAX_TOOLS, en
        place ; renvoie les opérations retirées par motif."""
        excluded: dict[str, int] = {}
        selection = OperationFilter.from_config(self.config)
        if selection.active:
            kept = [op for op in operations if selection.keeps(op[0], op[2].get("tags") or [])]
            if len(kept) < len(operations):
                excluded[EXCLUDED_BY_FILTER] = len(operations) - len(kept)
                console.print(f"[dim]  Filter: {len(kept)} operation(s) kept out of {len(operations)}[/dim]")
            operations[:] = kept
        if len(operations) > MAX_TOOLS:
            over = len(operations) - MAX_TOOLS
            excluded[EXCLUDED_OVER_LIMIT] = over
            tags = ", ".join(f"{t} ({n})" for t, n in top_tags(op[2].get("tags") or [] for op in operations))
            console.print(
                f"[yellow]⚠ {len(operations)} operations: only the first {MAX_TOOLS} (spec order) "
                f"are generated, {over} are removed.[/yellow]\n"
                "  Pick the operations you need with --include-tags / --include-paths "
                "(or --exclude-tags / --exclude-paths), for example: --include-tags repos,issues"
                + (f"\n  Most frequent tags: {escape(tags)}" if tags else ""))
            operations[:] = operations[:MAX_TOOLS]
        return excluded

    # ------------------------------------------------------------------
    # Authentification
    # ------------------------------------------------------------------

    def _extract_auth_schemes(self, spec: dict, is_v2: bool) -> list[AuthScheme]:
        """Détecte les schémas d'auth depuis securitySchemes (v3) ou securityDefinitions (v2)."""
        if is_v2:
            raw = spec.get("securityDefinitions", {})
        else:
            raw = spec.get("components", {}).get("securitySchemes", {})

        schemes: list[AuthScheme] = []
        for name, defn in raw.items():
            scheme_type = defn.get("type", "").lower()
            scheme = defn.get("scheme", "").lower()

            if scheme_type == "apikey":
                param_name = defn.get("name", name)
                param_in   = defn.get("in", "header")
                env_var    = param_name.upper().replace("-", "_").replace(" ", "_")
                schemes.append(AuthScheme(
                    type=AuthType.APIKEY,
                    param_name=param_name,
                    param_in=param_in,
                    env_var=env_var,
                ))
            elif scheme_type == "http" and scheme == "bearer":
                schemes.append(AuthScheme(
                    type=AuthType.BEARER,
                    param_name="Authorization",
                    param_in="header",
                    env_var="BEARER_TOKEN",
                ))
            # Basic : `type: http, scheme: basic` en OpenAPI 3, `type: basic` en Swagger 2
            # (forme ignorée jusqu'au 2026-11-17 : les 18 désaccords d'auth du banc complet)
            elif (scheme_type == "http" and scheme == "basic") or scheme_type == "basic":
                schemes.append(AuthScheme(
                    type=AuthType.BASIC,
                    param_name="Authorization",
                    param_in="header",
                    env_var="BASIC_AUTH",
                ))
            elif scheme_type == "oauth2":
                # Extraire tokenUrl depuis les flows (client credentials en priorité)
                flows = defn.get("flows", {})
                token_url = ""
                for flow_name in ("clientCredentials", "password", "authorizationCode", "implicit"):
                    flow = flows.get(flow_name, {})
                    if flow.get("tokenUrl"):
                        token_url = flow["tokenUrl"]
                        break
                # OpenAPI v2 : tokenUrl direct
                if not token_url and "tokenUrl" in defn:
                    token_url = defn["tokenUrl"]
                schemes.append(AuthScheme(
                    type=AuthType.OAUTH2,
                    param_name="Authorization",
                    param_in="header",
                    env_var="OAUTH2_TOKEN",
                    token_url=token_url,
                ))

        return schemes

    # ------------------------------------------------------------------
    # Chargement de la spec
    # ------------------------------------------------------------------

    def _load_spec(self) -> dict[str, Any]:
        if self.preloaded_spec is not None:
            return self.preloaded_spec
        if self.source.startswith("http://") or self.source.startswith("https://"):
            return self._load_from_url(self.source)
        return self._load_from_file(Path(self.source))

    def _load_from_url(self, url: str) -> dict[str, Any]:
        # Essaie d'abord l'URL directe, puis les chemins OpenAPI courants
        candidates = [url]
        parsed = urlparse(url)
        if not parsed.path.endswith((".json", ".yaml", ".yml")):
            base = f"{parsed.scheme}://{parsed.netloc}"
            candidates += [
                urljoin(base, "/openapi.json"),
                urljoin(base, "/openapi.yaml"),
                urljoin(base, "/swagger.json"),
                urljoin(base, "/api/openapi.json"),
                urljoin(base, "/api-docs"),
                urljoin(base, "/v1/openapi.json"),
            ]

        # Une réponse 200 n'est une spec que si son contenu en est une : une page HTML (site
        # web, page de doc) se lit en YAML comme une simple chaîne, et le journal disait
        # « Spec found » pour la page d'accueil d'un site (constat du PO, 2026-11-18).
        for candidate in candidates:
            if self.url_guard is not None:
                try:
                    self.url_guard(candidate)
                except Exception:
                    continue
            try:
                # Limites communes de taille et de temps (mcp_forge/discovery/download.py)
                response = download.fetch(candidate, max_bytes=download.SPEC_MAX_BYTES,
                                          deadline_s=download.SPEC_DEADLINE_S)
                if response.status_code != 200:
                    continue
                try:
                    spec = self._parse_content(response.text, candidate)
                except Exception:
                    spec = None
                if _looks_like_spec(spec):
                    console.print(f"[dim]  OpenAPI spec found: {escape(candidate)}[/dim]")
                    return spec
                if not self.probe:
                    console.print(f"[dim]  {escape(candidate)}: not an OpenAPI spec[/dim]")
            except (download.DownloadTooLarge, download.DownloadTooSlow) as e:
                if candidate == url and not self.probe:
                    # L'URL donnée par l'utilisateur : refus explicite, pas d'essai ailleurs
                    raise ValueError(f"Could not load the OpenAPI spec: {e}") from e
                console.print(f"[yellow]  ⚠ Skipped: {escape(str(e))}[/yellow]")
                continue
            except Exception as e:
                if not self.probe:
                    console.print(f"[dim]  Failed {escape(candidate)}: {escape(str(e))}[/dim]")
                continue

        raise ValueError(f"Could not load an OpenAPI spec from: {url}")

    def _load_from_file(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return self._parse_content(path.read_text(encoding="utf-8"), str(path))

    def _parse_content(self, content: str, source: str) -> dict[str, Any]:
        if source.endswith((".yaml", ".yml")):
            return _load_yaml(content)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return _load_yaml(content)

    # ------------------------------------------------------------------
    # Extraction de l'URL de base
    # ------------------------------------------------------------------

    def _extract_base_url(self, spec: dict, is_v2: bool) -> str:
        if is_v2:
            host = spec.get("host", "")
            base_path = spec.get("basePath", "/")
            schemes = spec.get("schemes", ["https"])
            scheme = schemes[0] if schemes else "https"
            return f"{scheme}://{host}{base_path}" if host else ""
        # OpenAPI 3.x
        servers = spec.get("servers", [])
        if servers and isinstance(servers[0], dict):
            url = _text(servers[0].get("url"))
            # Variables de serveur (https://{region}.api.example.com) : valeur par défaut
            for var, defn in _as_dict(servers[0].get("variables")).items():
                default = _as_dict(defn).get("default")
                if default is not None:
                    url = url.replace("{" + str(var) + "}", _text(default))
            # Relative URL (e.g. "/" or "/api/v3") → rebuild from source domain
            if url.startswith("/") and self.source.startswith("http"):
                parsed = urlparse(self.source)
                url = f"{parsed.scheme}://{parsed.netloc}{url}"
            # Strip trailing slash for consistency (tools append /endpoint themselves)
            url = url.rstrip("/")
            if url:
                return url
        # Fallback: no servers block → derive scheme+host from the source URL
        if self.source.startswith("http"):
            parsed = urlparse(self.source)
            return f"{parsed.scheme}://{parsed.netloc}"
        return ""

    # ------------------------------------------------------------------
    # Conversion operation >> DiscoveredTool
    # ------------------------------------------------------------------

    def _operation_to_tool(
        self,
        path: str,
        method: str,
        operation: dict,
        spec: dict,
        base_url: str,
        is_v2: bool,
        path_item: dict | None = None,
    ) -> DiscoveredTool:
        name = self._base_name(method, path, operation)

        summary = operation.get("summary", "")
        detail  = operation.get("description", "")
        tags    = operation.get("tags", [])

        if summary and detail:
            description = f"{summary.rstrip('.')}. {detail}"
        elif summary:
            description = summary
        elif detail:
            description = detail
        elif tags:
            description = f"{method} {path} [{', '.join(tags)}]"
        else:
            description = f"{method} {path}"

        # Extraction des paramètres
        parameters = self._extract_parameters(operation, spec, is_v2, path_item or {})

        # Réponse
        responses = operation.get("responses", {})
        ok_resp = responses.get("200") or responses.get("201") or {}
        response_desc = ok_resp.get("description", "") if isinstance(ok_resp, dict) else ""

        binary_media = None if is_v2 else self._binary_body_media_type(operation, spec)
        json_media = None if is_v2 else self._json_body_media_type(operation, spec)
        response_schema = openapi_response_schema(operation, lambda obj: self._safe_resolve(obj, spec), is_v2)
        return DiscoveredTool(
            name=name,
            description=description,
            parameters=parameters,
            http_method=method,
            endpoint=path,
            base_url=base_url,
            response_description=response_desc,
            response_schema=response_schema,
            tags=tags,
            metadata=({"body_media_type": binary_media} if binary_media else {})
            | ({"json_media_type": json_media} if json_media else {}),
        )

    def _merged_parameters(self, path_item: dict, operation: dict, spec: dict) -> list[dict]:
        """Paramètres de l'opération, avec ceux déclarés au niveau du path (partagés par
        toutes ses méthodes). Une déclaration de l'opération remplace celle du path de même
        nom et même emplacement. Lot A, recommandation 1 : 268 641 paramètres de l'annuaire
        APIs.guru n'étaient jamais lus. Un paramètre sans nom (référence vers un autre
        fichier, non résolue) est ignoré."""
        merged: dict[tuple[str, str], dict] = {}
        raw = list(_as_dict(path_item).get("parameters") or []) + list(operation.get("parameters") or [])
        for item in raw:
            param = _as_dict(self._safe_resolve(item, spec))
            name = _text(param.get("name"))
            if not name:
                continue
            merged[(name, _text(param.get("in")))] = param
        return list(merged.values())

    def _extract_parameters(self, operation: dict, spec: dict, is_v2: bool,
                            path_item: dict | None = None) -> list[ToolParameter]:
        params: list[ToolParameter] = []
        declared = self._merged_parameters(path_item or {}, operation, spec)

        # Path/query/header params (Swagger 2 : corps et formulaire traités plus bas, une seule
        # fois ; avant, le paramètre `in: body` brut était ajouté en plus de ses propriétés)
        for param in declared:
            if is_v2 and param.get("in") in ("body", "formData"):
                continue
            schema = _as_dict(param.get("schema", param))  # v3 met le type dans schema
            params.append(ToolParameter(
                name=_text(param.get("name")),
                type=_json_type(schema),
                description=_text(param.get("description")),
                required=bool(param.get("required", False)) or param.get("in") == "path",
                default=schema.get("default"),
                enum_values=_enum_text(schema.get("enum")),
                param_in=_text(param.get("in")),
                format=_text(schema.get("format")),
            ))

        # Request body (OpenAPI 3.x)
        if not is_v2:
            request_body = operation.get("requestBody", {})
            if request_body:
                request_body = _as_dict(self._resolve_ref(request_body, spec))
                content = _as_dict(request_body.get("content"))
                schema = {}
                detected_media = _pick_body_media(content)
                if detected_media:
                    schema = _as_dict(self._resolve_ref(_as_dict(content[detected_media]).get("schema", {}), spec))
                params += self._schema_to_params(
                    schema, spec,
                    required_flag=request_body.get("required", False),
                    media_type=detected_media,
                )
                binary_media = self._binary_body_media_type(operation, spec)
                if not detected_media and binary_media:
                    # Corps binaire (application/octet-stream, image/*, PDF…) :
                    # un paramètre fichier, envoyé tel quel (2026-10-30 ; avant,
                    # le tool n'avait aucun paramètre pour le fichier).
                    params.append(ToolParameter(
                        name="file",
                        type=ParameterType.STRING,
                        description=(f"File to send as the request body ({binary_media}): its content in "
                                     "base64, or 'upload:<file name>' for a file placed in the server's "
                                     "MCP_UPLOAD_DIR directory."),
                        required=bool(request_body.get("required", False)),
                        param_in="body_binary",
                    ))

        # Body (Swagger 2.x)
        if is_v2:
            for param in declared:
                if param.get("in") == "body":
                    schema = _as_dict(self._resolve_ref(param.get("schema", {}), spec))
                    params += self._schema_to_params(schema, spec)
                elif param.get("in") == "formData":
                    params.append(ToolParameter(
                        name=_text(param.get("name")),
                        type=_json_type(param),
                        description=_text(param.get("description")),
                        required=bool(param.get("required", False)),
                        enum_values=_enum_text(param.get("enum")),
                        param_in="formData",
                        format=_text(param.get("format")),
                    ))

        return params

    _BINARY_MEDIA_EXACT = frozenset({"application/octet-stream", "application/pdf", "application/zip",
                                     "application/gzip", "application/x-tar", "*/*"})
    _BINARY_MEDIA_PREFIXES = ("image/", "audio/", "video/", "font/")

    def _binary_body_media_type(self, operation: dict, spec: dict) -> str | None:
        """Type de média du corps s'il est binaire (et que le corps n'est ni
        JSON ni un formulaire) ; None sinon. « */* » devient
        application/octet-stream."""
        request_body = _as_dict(self._resolve_ref(operation.get("requestBody") or {}, spec))
        content = _as_dict(request_body.get("content"))
        if _pick_body_media(content):
            return None
        for media_type, media in content.items():
            schema = _as_dict(self._resolve_ref(_as_dict(media).get("schema") or {}, spec))
            if (media_type in self._BINARY_MEDIA_EXACT or media_type.startswith(self._BINARY_MEDIA_PREFIXES)
                    or schema.get("format") == "binary"):
                return "application/octet-stream" if media_type == "*/*" else media_type
        return None

    def _json_body_media_type(self, operation: dict, spec: dict) -> str | None:
        """Type de média JSON du corps quand ce n'est pas application/json
        (application/vnd.api+json…) : le serveur généré l'envoie dans Content-Type, une API
        JSON:API refusant souvent application/json. None sinon."""
        request_body = _as_dict(self._safe_resolve(operation.get("requestBody") or {}, spec))
        media = _pick_body_media(_as_dict(request_body.get("content")))
        return media if media and "json" in media.lower() and media != "application/json" else None

    def _schema_to_params(
        self,
        schema: dict,
        spec: dict,
        required_flag: bool = False,
        media_type: str = "application/json",
    ) -> list[ToolParameter]:
        """Transforme un JSON Schema en liste de ToolParameter.

        Cas particuliers :
        - type:array  → un seul param "body" de type list (l'array entier est le body)
        - multipart/form-data → param_in="formData" pour que le template utilise data= ou files=
        """
        if not schema:
            return []

        schema = self._resolve_ref(schema, spec)
        # multipart/form-data ET application/x-www-form-urlencoded doivent tous les deux
        # être envoyés via `data=` (form-encoded) dans le serveur généré, pas `json=`.
        is_form_encoded = media_type in ("multipart/form-data", "application/x-www-form-urlencoded")

        # Body de type array — ex: POST /user/createWithList
        if schema.get("type") == "array":
            return [ToolParameter(
                name="body",
                type=ParameterType.ARRAY,
                description="List of items to send as the request body.",
                required=required_flag,
                param_in="body_array",
            )]

        props = schema.get("properties", {})
        required_fields = schema.get("required", [])
        if not props:
            composed = self._composed_body(schema, spec)
            if composed == "array":
                return self._schema_to_params({"type": "array"}, spec, required_flag, media_type)
            if composed:
                props, required_fields = composed
        params: list[ToolParameter] = []

        for prop_name, prop_schema in props.items():
            prop_schema = _as_dict(self._safe_resolve(prop_schema, spec))
            is_binary = prop_schema.get("format") == "binary"
            ptype = ParameterType.STRING if is_binary else _json_type(prop_schema)
            desc = _text(prop_schema.get("description", prop_schema.get("title", "")))
            if is_binary:
                desc = desc or f"Local path to the file to upload for '{prop_name}'"
            if is_binary:
                pin = "file_upload"
            elif is_form_encoded:
                pin = "formData"
            else:
                pin = "body"
            params.append(ToolParameter(
                name=_text(prop_name),
                type=ptype,
                description=desc,
                # Seuls les champs listés dans `required` du schéma (D7,
                # 2026-11-12) : un corps obligatoire (requestBody.required)
                # rendait chaque champ obligatoire, et le LLM du client
                # devait inventer une valeur pour chacun (GitHub
                # issues/create : 9 champs exigés au lieu de « title »).
                required=prop_name in required_fields,
                default=prop_schema.get("default"),
                enum_values=_enum_text(prop_schema.get("enum")),
                param_in=pin,
                format=_text(prop_schema.get("format")),
            ))

        return params

    def _composed_body(self, schema: dict, spec: dict, depth: int = 0) -> tuple[dict, list] | str | None:
        """Corps décrit par allOf / oneOf / anyOf à la racine (D7, constat
        GitHub du 2026-11-12 : `issues/add-labels` n'avait aucun paramètre et
        envoyait un POST sans corps). Renvoie (propriétés, obligatoires),
        "array" si seules des variantes tableau existent, ou None.

        - allOf : toutes les parties s'appliquent → propriétés et
          obligatoires fusionnés ;
        - oneOf / anyOf : l'appelant choisit une forme → union des
          propriétés des variantes objet (première définition gardée) ;
          obligatoire seulement si toutes les variantes objet l'exigent.
          Sans variante objet mais avec une variante tableau : corps
          tableau. Les variantes scalaires seules (chaîne…) ne donnent rien.
        """
        if depth > 5:
            return None
        if schema.get("allOf"):
            props: dict = {}
            required: list = []
            for part in schema["allOf"]:
                part = self._resolve_ref(part, spec) or {}
                sub = (part.get("properties"), part.get("required", [])) if part.get("properties") \
                    else self._composed_body(part, spec, depth + 1)
                if isinstance(sub, tuple):
                    for key, value in sub[0].items():
                        props.setdefault(key, value)
                    required += [r for r in sub[1] if r not in required]
            return (props, required) if props else None
        variants = schema.get("oneOf") or schema.get("anyOf")
        if not variants:
            return None
        objects: list[tuple[dict, list]] = []
        has_array = False
        for variant in variants:
            variant = self._resolve_ref(variant, spec) or {}
            if variant.get("properties"):
                objects.append((variant["properties"], variant.get("required", [])))
            elif variant.get("type") == "array":
                has_array = True
            else:
                sub = self._composed_body(variant, spec, depth + 1)
                if isinstance(sub, tuple):
                    objects.append(sub)
        if not objects:
            return "array" if has_array else None
        props = {}
        for variant_props, _ in objects:
            for key, value in variant_props.items():
                props.setdefault(key, value)
        required = [key for key in props if all(key in req for _, req in objects)]
        return props, required

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _safe_resolve(self, obj: Any, spec: dict) -> Any:
        """_resolve_ref sans exception : une référence externe ou mal formée
        donne {} (le schéma de réponse est alors simplement incomplet)."""
        try:
            return self._resolve_ref(obj, spec)
        except (AttributeError, TypeError):
            return {}

    def _resolve_ref(self, obj: Any, spec: dict) -> Any:
        """Résout les $ref dans la spec."""
        if not isinstance(obj, dict):
            return obj
        ref = obj.get("$ref")
        if not ref:
            return obj
        # Résolution locale uniquement (#/components/schemas/Foo)
        parts = ref.lstrip("#/").split("/")
        node = spec
        for part in parts:
            node = node.get(part, {})
        return node

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Transforme une chaîne en snake_case valide pour un nom de tool MCP.

        Gère : camelCase, PascalCase, path params {id}, caractères spéciaux.
        """
        import re
        # Supprime les segments path param : {id} -> ''
        name = re.sub(r"\{[^}]+\}", "", name)
        # camelCase / PascalCase -> snake_case
        name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
        name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        # Remplace tout ce qui n'est pas alphanumérique par _
        name = re.sub(r"[^a-zA-Z0-9]", "_", name)
        name = re.sub(r"_+", "_", name).strip("_").lower()
        return name or "tool"
