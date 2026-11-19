"""
Discovery à partir d'un endpoint GraphQL via introspection.

Stratégie :
  1. Envoyer la requête d'introspection standard
  2. Extraire les Query fields >> tools de lecture
  3. Extraire les Mutation fields >> tools d'écriture
  4. Convertir les arguments GraphQL en ToolParameter
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.markup import escape

from mcp_forge.discovery import download
from mcp_forge.discovery.response_schema import from_graphql
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


class GraphQLAuthRequired(ValueError):
    """Introspection refusée (401/403) sans en-tête d'authentification donné."""

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
      enumValues(includeDeprecated: false) { name }
      possibleTypes { name }
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
      ofType {
        kind
        name
        ofType {
          kind
          name
          ofType {
            kind
            name
            ofType {
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
          }
        }
      }
    }
  }
}
"""
# Lot B (recommandation 7 du rapport du 2026-10-24) : TypeRef sur 10 niveaux (avant : 4,
# `[[Float!]!]!` était tronqué en `[[String]!]!`) ;
# enumValues (valeurs des enums, perdues avant) et possibleTypes (fragments des unions).

_COMPOSITE = ("OBJECT", "INTERFACE", "UNION")
# Schéma GraphQL en fichier local (SDL) : lu par graphql-core, sans point d'accès à interroger
SDL_SUFFIXES = (".graphql", ".graphqls", ".gql", ".sdl")
# En-tête d'authentification passé par l'utilisateur (nom, en minuscules) : sa valeur sert à
# l'introspection et n'est jamais écrite dans le serveur généré (seul le schéma l'est)
_AUTH_HEADER_HINT = re.compile(r"key|token|auth|secret", re.IGNORECASE)


def is_local_sdl(source: str) -> bool:
    """Source GraphQL donnée en fichier de schéma (SDL) plutôt qu'en point d'accès HTTP."""
    return (not source.lower().startswith(("http://", "https://"))
            and source.lower().endswith(SDL_SUFFIXES))


def _bearer() -> AuthScheme:
    return AuthScheme(type=AuthType.BEARER, param_name="Authorization", param_in="header",
                      env_var="BEARER_TOKEN")
# Scalaires personnalisés qui portent un objet JSON ; les autres (DateTime, URI, BigInt…)
# s'écrivent en texte dans une requête GraphQL
_JSON_SCALARS = frozenset({"json", "jsonobject", "jsonvalue", "object", "map"})

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

        local_sdl = is_local_sdl(self.endpoint)
        schema = self._introspect_sdl() if local_sdl else self._introspect()
        if not schema:
            raise ValueError(f"Could not introspect the GraphQL schema: {self.endpoint}")

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
            console.print(f"[dim]  {len(tools)} query(ies) found[/dim]")

        # Mutations >> tools d'écriture
        mutations_count = 0
        if mutation_type_name:
            mutation_type = types_by_name.get(mutation_type_name)
            if mutation_type:
                for field in mutation_type.get("fields") or []:
                    tools.append(self._field_to_tool(field, "mutation", types_by_name))
                    mutations_count += 1
                console.print(f"[dim]  {mutations_count} mutation(s) found[/dim]")

        console.print(f"[green][OK] {len(tools)} MCP tool(s) extracted[/green]")

        auth_schemes = self._detect_auth(tools, probe=not local_sdl)

        # SDL local : aucun point d'accès connu ; le serveur généré le lit dans GRAPHQL_ENDPOINT
        endpoint = "" if local_sdl else self.endpoint
        return DiscoveryResult(
            source_type=SourceType.GRAPHQL,
            source_url=endpoint or None,
            source_path=self.endpoint if local_sdl else None,
            title="API GraphQL",
            base_url=endpoint,
            tools=tools,
            auth_schemes=auth_schemes,
        )

    # ------------------------------------------------------------------
    # Détection de l'authentification
    # ------------------------------------------------------------------

    def _detect_auth(self, tools: list[DiscoveredTool], probe: bool = True) -> list[AuthScheme]:
        """Authentification du point d'accès (lot B, recommandation 7 ; 1 cas juste sur 4 au banc
        avant) :

        1. les en-têtes donnés par l'utilisateur (extra_headers, --header) : Authorization
           Bearer ou Basic, ou un en-tête de clé (X-API-Key, X-Auth-Token…) ;
        2. sinon, une requête sans en-tête refusée en 401/403 : Bearer.

        Une mutation login/signin ne suffit plus : elle n'indique pas que le point d'accès
        exige un jeton (un point d'accès public avec login passait pour protégé)."""
        schemes = self._auth_from_headers()
        if schemes or not probe:
            return schemes
        try:
            # Limites communes (mcp_forge/discovery/download.py) : une petite réponse attendue
            response = download.fetch(self.endpoint, method="POST", json={"query": "{ __typename }"},
                                      headers={"Content-Type": "application/json"},
                                      max_bytes=download.CONFIG_MAX_BYTES, deadline_s=download.PAGE_DEADLINE_S)
            if response.status_code in (401, 403):
                console.print("[dim]  Authentication required (401/403 on the probe) → Bearer token[/dim]")
                return [_bearer()]
        except (httpx.HTTPError, download.DownloadTooLarge, download.DownloadTooSlow):
            pass
        return []

    def _auth_from_headers(self) -> list[AuthScheme]:
        schemes: list[AuthScheme] = []
        for name, value in (self.config.extra_headers or {}).items():
            lower = name.strip().lower()
            if lower == "authorization":
                scheme = str(value).strip().split(" ", 1)[0].lower()
                if scheme == "basic":
                    schemes.append(AuthScheme(type=AuthType.BASIC, param_name="Authorization",
                                              param_in="header", env_var="BASIC_AUTH"))
                else:  # Bearer, ou jeton sans schéma : envoyé tel quel derrière « Bearer »
                    schemes.append(_bearer())
            elif _AUTH_HEADER_HINT.search(lower):
                env_var = re.sub(r"[^A-Za-z0-9]+", "_", name.strip()).strip("_").upper() or "API_KEY"
                schemes.append(AuthScheme(type=AuthType.APIKEY, param_name=name.strip(),
                                          param_in="header", env_var=env_var))
        return schemes

    # ------------------------------------------------------------------
    # Introspection HTTP
    # ------------------------------------------------------------------

    def _introspect(self) -> dict | None:
        try:
            # Limites communes (mcp_forge/discovery/download.py, 2026-11-18) : le schéma, comme
            # une spec (32 Mio, 60 s au total), lu en flux ; avant, 15 s entre deux lectures
            # seulement, sans taille maximale
            response = download.fetch(
                self.endpoint, method="POST", json={"query": _INTROSPECTION_QUERY},
                headers={"Content-Type": "application/json", "Accept": "application/json",
                         **self.config.extra_headers},
                max_bytes=download.SPEC_MAX_BYTES, deadline_s=download.SPEC_DEADLINE_S,
            )
            if response.status_code in (401, 403) and not self.config.extra_headers:
                raise GraphQLAuthRequired(
                    f"The GraphQL endpoint requires authentication (HTTP {response.status_code}): "
                    "give the token with --header \"Authorization: Bearer <token>\" "
                    "(used for introspection only, never written to the generated server)")
            if response.status_code >= 400:
                raise ValueError(f"HTTP {response.status_code} for {self.endpoint}")
            data = json.loads(response.text)
            if "errors" in data and not data.get("data"):
                console.print(f"[red]  [FAIL] GraphQL errors: {escape(str(data['errors']))}[/red]")
                return None
            return data
        except (download.DownloadTooLarge, download.DownloadTooSlow) as exc:
            # Refus explicite : la raison (taille, durée) est donnée à l'utilisateur
            raise ValueError(f"Could not introspect the GraphQL schema: {exc}") from exc
        except GraphQLAuthRequired:
            raise
        except Exception as e:
            console.print(f"[red]  [FAIL] Introspection failed: {e}[/red]")
            return None

    def _introspect_sdl(self) -> dict | None:
        """Schéma en fichier local (SDL) : introspection par graphql-core, sur le même
        schéma que celui qu'aurait renvoyé le point d'accès."""
        try:
            from graphql import build_schema, graphql_sync
        except ImportError as exc:  # pragma: no cover - dépendance du paquet
            raise ValueError("Reading a GraphQL schema file needs graphql-core: "
                             "pip install graphql-core") from exc
        path = Path(self.endpoint)
        if not path.is_file():
            raise ValueError(f"GraphQL schema file not found: {self.endpoint}")
        try:
            schema = build_schema(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Invalid GraphQL schema file {path.name}: {str(exc).splitlines()[0][:200]}") from exc
        result = graphql_sync(schema, _INTROSPECTION_QUERY)
        if result.errors:
            raise ValueError(f"GraphQL schema introspection failed: {result.errors[0].message}")
        return {"data": result.data}

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
        # Pas de sélection sur un scalaire ou un enum (`hello { __typename }` est refusé)

        gql_args = [(a["name"], _gql_type_str(a.get("type", {}))) for a in args]
        return_type_name = self._unwrap_type_name(field.get("type", {}))
        gql_selection = self._build_selection_set(return_type_name, types_by_name)

        return DiscoveredTool(
            name=name,
            description=description,
            parameters=parameters,
            http_method="POST",
            endpoint="" if is_local_sdl(self.endpoint) else self.endpoint,
            base_url="" if is_local_sdl(self.endpoint) else self.endpoint,
            tags=[operation],
            response_description=self._describe_return_type(field.get("type", {})),
            response_schema=from_graphql(name, field.get("type", {}), types_by_name, self._MAX_SELECTION_DEPTH,
                                         self._MAX_FIELDS_PER_LEVEL, field.get("description") or ""),
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

        Lot B (2026-11-17) : "" pour un scalaire ou un enum (aucune sélection permise) ;
        une union reçoit `__typename` et un fragment `... on X { … }` par type possible
        (avant : champ d'union sans sous-sélection, 339 opérations invalides sur Artsy).
        """
        visited = visited or frozenset()
        if type_name in _GQL_TYPE_MAP:
            return ""
        node_type = types_by_name.get(type_name)
        if not node_type:
            return "__typename"
        kind = node_type.get("kind")
        if kind not in _COMPOSITE:
            return ""
        if depth >= self._MAX_SELECTION_DEPTH or type_name in visited:
            return "__typename"
        if kind == "UNION":
            names = [n for n in ((p or {}).get("name") for p in (node_type.get("possibleTypes") or [])) if n]
            names = names[: self._MAX_FIELDS_PER_LEVEL]
            # Un champ de même nom et de types différents dans deux fragments est refusé par
            # GraphQL (« Fields 'title' conflict… ») : écarté de tous les fragments
            seen: dict[str, set[str]] = {}
            for pname in names:
                for f in self._selectable_fields(pname, types_by_name):
                    seen.setdefault(f["name"], set()).add(_gql_type_str(f.get("type", {})))
            ambiguous = frozenset(n for n, kinds in seen.items() if len(kinds) > 1)
            parts = ["__typename"]
            for pname in names:
                fields = self._field_selection(pname, types_by_name, depth, visited | {type_name}, ambiguous)
                if fields:
                    parts.append(f"... on {pname} {{ {fields} }}")
            return " ".join(parts)
        return self._field_selection(type_name, types_by_name, depth, visited) or "__typename"

    def _selectable_fields(self, type_name: str, types_by_name: dict[str, Any]) -> list[dict]:
        """Champs sélectionnables d'un objet ou d'une interface : sans argument (impossible à
        satisfaire sans les demander à l'appelant), parmi les premiers du type."""
        node_type = types_by_name.get(type_name) or {}
        return [f for f in (node_type.get("fields") or [])[: self._MAX_FIELDS_PER_LEVEL]
                if f.get("name") and not f["name"].startswith("__") and not f.get("args")]

    def _field_selection(self, type_name: str, types_by_name: dict[str, Any], depth: int,
                         visited: frozenset[str], skip: frozenset[str] = frozenset()) -> str:
        """Champs sélectionnables d'un objet ou d'une interface (sauf `skip`) ; un champ
        composé reçoit sa propre sélection (un niveau plus bas)."""
        parts: list[str] = []
        for f in self._selectable_fields(type_name, types_by_name):
            fname = f["name"]
            if fname in skip:
                continue
            sub_type_name = self._unwrap_type_name(f.get("type", {}))
            # Type absent de l'introspection : feuille, comme avant le lot B
            sub_selection = (self._build_selection_set(sub_type_name, types_by_name, depth + 1,
                                                       visited | {type_name})
                             if sub_type_name in types_by_name else "")
            parts.append(f"{fname} {{ {sub_selection} }}" if sub_selection else fname)
        return " ".join(parts)

    def _arg_to_param(self, arg: dict[str, Any], types_by_name: dict[str, Any]) -> ToolParameter:
        name = arg.get("name", "")
        description = arg.get("description") or ""
        default = arg.get("defaultValue")

        ptype, required = self._resolve_type(arg.get("type", {}), types_by_name)

        type_name = self._unwrap_type_name(arg.get("type", {}))
        named = types_by_name.get(type_name) or {}
        if named.get("kind") == "INPUT_OBJECT":
            description = description or f"Object of type {type_name}"
        # Valeurs d'un enum (argument simple, pas une liste) : lot B, perdues avant
        enum_values = ([v["name"] for v in named.get("enumValues") or [] if isinstance(v, dict) and v.get("name")]
                       if named.get("kind") == "ENUM" and ptype == ParameterType.STRING else [])

        return ToolParameter(
            name=name,
            type=ptype,
            description=description,
            required=required,
            default=default,
            enum_values=enum_values,
        )

    def _resolve_type(self, gql_type: dict,
                      types_by_name: dict[str, Any] | None = None) -> tuple[ParameterType, bool]:
        """Résout un TypeRef GraphQL >> (ParameterType, is_required).

        Enum et scalaire personnalisé (DateTime, URI…) : texte (lot B ; avant : objet, la
        valeur envoyée était refusée par le serveur). Scalaire JSON : objet."""
        required = False
        node = gql_type
        if node.get("kind") == "NON_NULL":
            required = True
            node = node.get("ofType") or {}
        if node.get("kind") == "LIST":
            return ParameterType.ARRAY, required
        type_name = node.get("name", "")
        if type_name in _GQL_TYPE_MAP:
            return _GQL_TYPE_MAP[type_name], required
        kind = node.get("kind") or ((types_by_name or {}).get(type_name) or {}).get("kind")
        if kind == "ENUM":
            return ParameterType.STRING, required
        if kind == "SCALAR":
            return (ParameterType.OBJECT if type_name.lower() in _JSON_SCALARS else ParameterType.STRING), required
        return ParameterType.OBJECT, required

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
        return f"Returns an object of type {name}" if name else ""
