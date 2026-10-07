"""
Discovery à partir d'un endpoint GraphQL via introspection.

Stratégie :
  1. Envoyer la requête d'introspection standard
  2. Extraire les Query fields >> tools de lecture
  3. Extraire les Mutation fields >> tools d'écriture
  4. Convertir les arguments GraphQL en ToolParameter
"""
from __future__ import annotations

import re
from typing import Any

import httpx
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

_INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    types {
      kind
      name
      description
      fields(includeDeprecated: false) {
        name
        description
        args {
          name
          description
          type { ...TypeRef }
          defaultValue
        }
        type { ...TypeRef }
      }
      inputFields {
        name
        description
        type { ...TypeRef }
        defaultValue
      }
    }
  }
}
fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType { kind name }
    }
  }
}
"""

def _gql_type_str(gql_type: dict) -> str:
    """Convertit un TypeRef GraphQL en string de type GraphQL (ex: 'String!', '[Int!]!')."""
    if not gql_type:
        return "String"
    kind = gql_type.get("kind", "")
    of_type = gql_type.get("ofType")
    if kind == "NON_NULL":
        return f"{_gql_type_str(of_type)}!"
    if kind == "LIST":
        return f"[{_gql_type_str(of_type)}]"
    return gql_type.get("name") or "String"


_GQL_TYPE_MAP: dict[str, ParameterType] = {
    "String": ParameterType.STRING,
    "ID": ParameterType.STRING,
    "Int": ParameterType.INTEGER,
    "Float": ParameterType.NUMBER,
    "Boolean": ParameterType.BOOLEAN,
}


class GraphQLDiscovery:
    def __init__(self, config: ForgeConfig):
        self.config = config
        self.endpoint = config.source

    def discover(self) -> DiscoveryResult:
        console.print("[bold]>> Introspection GraphQL...[/bold]")

        schema = self._introspect()
        if not schema:
            raise ValueError(f"Impossible d'introspecter le schéma GraphQL : {self.endpoint}")

        gql_schema = schema.get("data", {}).get("__schema", {})
        types_by_name = {t["name"]: t for t in gql_schema.get("types", [])}

        query_type_name = (gql_schema.get("queryType") or {}).get("name", "Query")
        mutation_type_name = (gql_schema.get("mutationType") or {}).get("name")

        tools: list[DiscoveredTool] = []

        # Queries >> tools de lecture
        query_type = types_by_name.get(query_type_name)
        if query_type:
            for field in query_type.get("fields") or []:
                tools.append(self._field_to_tool(field, "query", types_by_name))
            console.print(f"[dim]  {len(tools)} query(ies) trouvée(s)[/dim]")

        # Mutations >> tools d'écriture
        mutations_count = 0
        if mutation_type_name:
            mutation_type = types_by_name.get(mutation_type_name)
            if mutation_type:
                for field in mutation_type.get("fields") or []:
                    tools.append(self._field_to_tool(field, "mutation", types_by_name))
                    mutations_count += 1
                console.print(f"[dim]  {mutations_count} mutation(s) trouvée(s)[/dim]")

        console.print(f"[green][OK] {len(tools)} outil(s) MCP extrait(s)[/green]")

        auth_schemes = self._detect_auth(tools)

        return DiscoveryResult(
            source_type=SourceType.GRAPHQL,
            source_url=self.endpoint,
            title="API GraphQL",
            base_url=self.endpoint,
            tools=tools,
            auth_schemes=auth_schemes,
        )

    # ------------------------------------------------------------------
    # Détection de l'authentification
    # ------------------------------------------------------------------

    def _detect_auth(self, tools: list[DiscoveredTool]) -> list[AuthScheme]:
        """Détecte si l'endpoint GraphQL requiert une auth.

        Stratégie :
        1. Tente l'introspection sans auth → si 401/403 → Bearer requis
        2. Cherche des mutations login/authenticate → indique une auth Bearer
        """
        try:
            probe = httpx.post(
                self.endpoint,
                json={"query": "{ __typename }"},
                headers={"Content-Type": "application/json", **self.config.extra_headers},
                timeout=10,
                follow_redirects=True,
            )
            if probe.status_code in (401, 403):
                console.print("[dim]  Auth requise (401/403 sur probe) → Bearer token[/dim]")
                return [AuthScheme(type=AuthType.BEARER, param_name="Authorization",
                                   param_in="header", env_var="BEARER_TOKEN")]
        except Exception:
            pass

        # Cherche des mutations d'authentification dans les tools découverts
        auth_keywords = re.compile(r"login|signin|sign_in|authenticate|get.?token|access.?token", re.IGNORECASE)
        has_auth_mutation = any(
            t.tags and "mutation" in t.tags and auth_keywords.search(t.name)
            for t in tools
        )
        if has_auth_mutation:
            console.print("[dim]  Mutation d'auth détectée → Bearer token probable[/dim]")
            return [AuthScheme(type=AuthType.BEARER, param_name="Authorization",
                               param_in="header", env_var="BEARER_TOKEN")]

        return []

    # ------------------------------------------------------------------
    # Introspection HTTP
    # ------------------------------------------------------------------

    def _introspect(self) -> dict | None:
        try:
            response = httpx.post(
                self.endpoint,
                json={"query": _INTROSPECTION_QUERY},
                headers={"Content-Type": "application/json", "Accept": "application/json",
                         **self.config.extra_headers},
                timeout=15,
                follow_redirects=True,
            )
            response.raise_for_status()
            data = response.json()
            if "errors" in data and not data.get("data"):
                console.print(f"[red]  [FAIL] Erreurs GraphQL : {data['errors']}[/red]")
                return None
            return data
        except Exception as e:
            console.print(f"[red]  [FAIL] Échec introspection : {e}[/red]")
            return None

    # ------------------------------------------------------------------
    # Conversion field GraphQL >> DiscoveredTool
    # ------------------------------------------------------------------

    def _field_to_tool(
        self,
        field: dict[str, Any],
        operation: str,  # "query" ou "mutation"
        types_by_name: dict[str, Any],
    ) -> DiscoveredTool:
        name = field.get("name", "unknown")
        description = field.get("description") or f"GraphQL {operation} : {name}"
        args = field.get("args") or []
        parameters = [self._arg_to_param(arg, types_by_name) for arg in args]

        gql_args = [(a["name"], _gql_type_str(a.get("type", {}))) for a in args]
        return_type_name = self._unwrap_type_name(field.get("type", {}))
        gql_selection = self._build_selection_set(return_type_name, types_by_name)

        return DiscoveredTool(
            name=name,
            description=description,
            parameters=parameters,
            http_method="POST",
            endpoint=self.endpoint,
            base_url=self.endpoint,
            tags=[operation],
            response_description=self._describe_return_type(field.get("type", {})),
            metadata={
                "operation": operation,
                "field_name": name,
                "gql_args": gql_args,
                "gql_selection": gql_selection,
            },
        )

    # Profondeur/largeur bornées : assez pour couvrir le cas courant d'un
    # objet avec un sous-objet imbriqué (ex: Country.continent.name) sans
    # risquer une requête énorme ou une récursion sur un type auto-référent.
    _MAX_SELECTION_DEPTH = 2
    _MAX_FIELDS_PER_LEVEL = 12

    def _build_selection_set(
        self,
        type_name: str,
        types_by_name: dict[str, Any],
        depth: int = 0,
        visited: frozenset[str] | None = None,
    ) -> str:
        """Construit un selection set GraphQL réel à partir du schéma introspecté.

        Root cause du bug corrigé ici : le template générait toujours
        `{ __typename }`, quel que soit le type de retour réel — chaque
        outil généré ne renvoyait donc jamais que le nom du type, aucune
        donnée utile (trouvé dans chaque rapport d'éval GraphQL du batch de
        tests). Sélectionne maintenant les champs scalaires/enum du type (et,
        une profondeur plus loin, ceux de ses sous-objets), en ignorant les
        champs qui exigent eux-mêmes des arguments (impossible à satisfaire
        sans les demander à l'appelant).
        """
        visited = visited or frozenset()
        if depth >= self._MAX_SELECTION_DEPTH or type_name in visited:
            return "__typename"
        node_type = types_by_name.get(type_name)
        if not node_type or node_type.get("kind") not in ("OBJECT", "INTERFACE"):
            return "__typename"

        parts: list[str] = []
        for f in (node_type.get("fields") or [])[: self._MAX_FIELDS_PER_LEVEL]:
            fname = f.get("name")
            if not fname or fname.startswith("__") or f.get("args"):
                continue
            sub_type_name = self._unwrap_type_name(f.get("type", {}))
            sub_type = types_by_name.get(sub_type_name)
            if sub_type and sub_type.get("kind") in ("OBJECT", "INTERFACE"):
                sub_selection = self._build_selection_set(
                    sub_type_name, types_by_name, depth + 1, visited | {type_name}
                )
                parts.append(f"{fname} {{ {sub_selection} }}")
            else:
                parts.append(fname)

        return " ".join(parts) if parts else "__typename"

    def _arg_to_param(self, arg: dict[str, Any], types_by_name: dict[str, Any]) -> ToolParameter:
        name = arg.get("name", "")
        description = arg.get("description") or ""
        default = arg.get("defaultValue")

        ptype, required = self._resolve_type(arg.get("type", {}))

        type_name = self._unwrap_type_name(arg.get("type", {}))
        if types_by_name.get(type_name, {}).get("kind") == "INPUT_OBJECT":
            description = description or f"Objet de type {type_name}"

        return ToolParameter(
            name=name,
            type=ptype,
            description=description,
            required=required,
            default=default,
        )

    def _resolve_type(self, gql_type: dict) -> tuple[ParameterType, bool]:
        """Résout un TypeRef GraphQL >> (ParameterType, is_required)."""
        required = False
        node = gql_type
        if node.get("kind") == "NON_NULL":
            required = True
            node = node.get("ofType") or {}
        if node.get("kind") == "LIST":
            return ParameterType.ARRAY, required
        type_name = node.get("name", "")
        return _GQL_TYPE_MAP.get(type_name, ParameterType.OBJECT), required

    @staticmethod
    def _unwrap_type_name(gql_type: dict) -> str:
        node = gql_type
        while node.get("ofType"):
            node = node["ofType"]
        return node.get("name", "")

    @staticmethod
    def _describe_return_type(gql_type: dict) -> str:
        node = gql_type
        while node.get("ofType"):
            node = node["ofType"]
        name = node.get("name", "")
        return f"Retourne un objet de type {name}" if name else ""
