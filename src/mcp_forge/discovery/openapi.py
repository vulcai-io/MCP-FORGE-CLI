"""
Discovery à partir d'une spec OpenAPI/Swagger (fichier local ou URL).
Supporte OpenAPI 2.x (Swagger) et 3.x.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import yaml
from rich.console import Console

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


class OpenAPIDiscovery:
    def __init__(self, config: ForgeConfig):
        self.config = config
        self.source = config.source

    # ------------------------------------------------------------------
    # Point d'entrée
    # ------------------------------------------------------------------

    def discover(self) -> DiscoveryResult:
        console.print("[bold]>> Chargement de la spec OpenAPI...[/bold]")
        spec = self._load_spec()

        openapi_version = spec.get("openapi", spec.get("swagger", ""))
        is_v2 = openapi_version.startswith("2")

        info = spec.get("info", {})
        base_url = self._extract_base_url(spec, is_v2)

        result = DiscoveryResult(
            source_type=SourceType.OPENAPI,
            source_url=self.source if self.source.startswith("http") else None,
            source_path=self.source if not self.source.startswith("http") else None,
            title=info.get("title", "API"),
            description=info.get("description", ""),
            version=info.get("version", ""),
            base_url=base_url,
        )

        paths = spec.get("paths", {})
        console.print(f"[dim]  {len(paths)} endpoint(s) trouvé(s)[/dim]")

        for path, path_item in paths.items():
            for method, operation in path_item.items():
                if method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                    continue
                if not isinstance(operation, dict):
                    continue
                tool = self._operation_to_tool(
                    path=path,
                    method=method.upper(),
                    operation=operation,
                    spec=spec,
                    base_url=base_url,
                    is_v2=is_v2,
                )
                result.tools.append(tool)

        result.auth_schemes = self._extract_auth_schemes(spec, is_v2)
        console.print(f"[green][OK] {len(result.tools)} outil(s) MCP extrait(s)[/green]")
        return result

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
            elif scheme_type == "http" and scheme == "basic":
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

        for candidate in candidates:
            try:
                response = httpx.get(candidate, timeout=10, follow_redirects=True)
                if response.status_code == 200:
                    console.print(f"[dim]  Spec trouvée : {candidate}[/dim]")
                    return self._parse_content(response.text, candidate)
            except Exception as e:
                console.print(f"[dim]  Échec {candidate}: {e}[/dim]")
                continue

        raise ValueError(f"Impossible de charger une spec OpenAPI depuis : {url}")

    def _load_from_file(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Fichier introuvable : {path}")
        return self._parse_content(path.read_text(encoding="utf-8"), str(path))

    def _parse_content(self, content: str, source: str) -> dict[str, Any]:
        if source.endswith((".yaml", ".yml")):
            return yaml.safe_load(content)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return yaml.safe_load(content)

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
        if servers:
            url = servers[0].get("url", "")
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
    ) -> DiscoveredTool:
        # Nom du tool : operationId ou méthode+path normalisé
        op_id = operation.get("operationId", "")
        if op_id:
            name = self._normalize_name(op_id)
        else:
            name = self._normalize_name(f"{method}_{path}")

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
        parameters = self._extract_parameters(operation, spec, is_v2)

        # Réponse
        responses = operation.get("responses", {})
        ok_resp = responses.get("200") or responses.get("201") or {}
        response_desc = ok_resp.get("description", "") if isinstance(ok_resp, dict) else ""

        return DiscoveredTool(
            name=name,
            description=description,
            parameters=parameters,
            http_method=method,
            endpoint=path,
            base_url=base_url,
            response_description=response_desc,
            tags=tags,
        )

    def _extract_parameters(self, operation: dict, spec: dict, is_v2: bool) -> list[ToolParameter]:
        params: list[ToolParameter] = []

        # Path/query/header params
        for param in operation.get("parameters", []):
            param = self._resolve_ref(param, spec)
            if not isinstance(param, dict):
                continue
            schema = param.get("schema", param)  # v3 met le type dans schema
            params.append(ToolParameter(
                name=param.get("name", ""),
                type=_TYPE_MAP.get(schema.get("type", "string"), ParameterType.STRING),
                description=param.get("description", ""),
                required=param.get("required", False),
                default=schema.get("default"),
                enum_values=schema.get("enum", []),
                param_in=param.get("in", ""),
            ))

        # Request body (OpenAPI 3.x)
        if not is_v2:
            request_body = operation.get("requestBody", {})
            if request_body:
                request_body = self._resolve_ref(request_body, spec)
                content = request_body.get("content", {})
                schema = {}
                detected_media = ""
                for media_type in (
                    "application/json",
                    "application/x-www-form-urlencoded",
                    "multipart/form-data",
                ):
                    if media_type in content:
                        schema = self._resolve_ref(
                            content[media_type].get("schema", {}), spec
                        )
                        detected_media = media_type
                        break
                params += self._schema_to_params(
                    schema, spec,
                    required_flag=request_body.get("required", False),
                    media_type=detected_media,
                )

        # Body (Swagger 2.x)
        if is_v2:
            for param in operation.get("parameters", []):
                param = self._resolve_ref(param, spec)
                if param.get("in") == "body":
                    schema = self._resolve_ref(param.get("schema", {}), spec)
                    params += self._schema_to_params(schema, spec)
                elif param.get("in") == "formData":
                    params.append(ToolParameter(
                        name=param.get("name", ""),
                        type=_TYPE_MAP.get(param.get("type", "string"), ParameterType.STRING),
                        description=param.get("description", ""),
                        required=param.get("required", False),
                        param_in="formData",
                    ))

        return params

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
        params: list[ToolParameter] = []

        for prop_name, prop_schema in props.items():
            prop_schema = self._resolve_ref(prop_schema, spec)
            is_binary = prop_schema.get("format") == "binary"
            ptype = ParameterType.STRING if is_binary else _TYPE_MAP.get(prop_schema.get("type", "string"), ParameterType.STRING)
            desc = prop_schema.get("description", prop_schema.get("title", ""))
            if is_binary:
                desc = desc or f"Local path to the file to upload for '{prop_name}'"
            if is_binary:
                pin = "file_upload"
            elif is_form_encoded:
                pin = "formData"
            else:
                pin = "body"
            params.append(ToolParameter(
                name=prop_name,
                type=ptype,
                description=desc,
                required=prop_name in required_fields or required_flag,
                default=prop_schema.get("default"),
                enum_values=prop_schema.get("enum", []),
                param_in=pin,
            ))

        return params

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
