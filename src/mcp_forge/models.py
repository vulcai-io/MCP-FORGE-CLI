"""
Modèles de données partagés entre tous les modules de mcp-forge.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ForgeMode(str, Enum):
    AUTO = "auto"
    SEMI = "semi"
    GUIDED = "guided"


class NameStyle(str, Enum):
    SHORT = "short"        # get_continent, list_countries
    EXHAUSTIVE = "exhaustive"  # get_continent_by_code, filter_countries_by_criteria


class SourceType(str, Enum):
    OPENAPI = "openapi"
    WEBSITE = "website"
    GRAPHQL = "graphql"
    CLI_APP = "cli_app"
    CODEBASE = "codebase"


class ParameterType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class AuthType(str, Enum):
    NONE   = "none"
    APIKEY = "apiKey"    # X-API-Key header ou query param
    BEARER = "bearer"    # Authorization: Bearer <token>
    BASIC  = "basic"     # Authorization: Basic <base64>
    OAUTH2 = "oauth2"    # Bearer token acquis via OAuth2


class AuthScheme(BaseModel):
    """Schéma d'authentification détecté depuis la spec source."""
    type: AuthType = AuthType.NONE
    # Pour apiKey : nom du header/param et emplacement
    param_name: str = ""          # ex: "X-API-Key", "api_key"
    param_in: str = "header"      # "header" | "query" | "cookie"
    # Nom de la variable d'environnement suggérée
    env_var: str = ""             # ex: "API_KEY", "BEARER_TOKEN"
    # OAuth2 client credentials — URL pour obtenir le token automatiquement
    token_url: str = ""           # ex: "https://api.example.com/oauth/token"


class ToolParameter(BaseModel):
    name: str
    type: ParameterType = ParameterType.STRING
    description: str = ""
    required: bool = False
    default: Any = None
    enum_values: list[str] = Field(default_factory=list)
    items_type: ParameterType | None = None  # pour les arrays
    param_in: str = ""  # "query" | "header" | "path" | "body" — vide si inconnu
    format: str = ""  # format de la spec (date-time, int64, uuid…) — vide si absent


class DiscoveredTool(BaseModel):
    """Représente un outil MCP découvert depuis une source."""
    name: str
    stable_name: str = ""  # nom figé depuis la discovery (operationId, nom de fonction...) — jamais modifié par le LLM
    description: str
    parameters: list[ToolParameter] = Field(default_factory=list)
    # Paramètres facultatifs regroupés dans le paramètre objet `options`
    # (tool de plus de 50 paramètres, voir mcp_forge/discovery/limits.py)
    option_parameters: list[ToolParameter] = Field(default_factory=list)
    # Métadonnées pour la génération de code
    http_method: str | None = None       # GET, POST, etc.
    endpoint: str | None = None          # /api/users/{id}
    base_url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    response_description: str = ""
    # Schéma descriptif de la réponse (lot D, D5) : outputSchema du tool,
    # voir mcp_forge/discovery/response_schema.py
    response_schema: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    # Métadonnées libres (CLI cmd, codebase function/file/class...)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Statut de review (pour les modes semi et guidé)
    enabled: bool = True
    reviewed: bool = False


class DiscoveryResult(BaseModel):
    """Résultat complet de la phase de découverte."""
    source_type: SourceType
    source_url: str | None = None
    source_path: str | None = None
    title: str = ""
    description: str = ""
    version: str = ""
    base_url: str = ""
    tools: list[DiscoveredTool] = Field(default_factory=list)
    auth_schemes: list[AuthScheme] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ForgeConfig(BaseModel):
    """Configuration globale d'une session mcp-forge."""
    mode: ForgeMode = ForgeMode.AUTO
    source_type: SourceType | None = None
    source: str = ""                     # URL ou chemin
    output_dir: str = "./output"
    server_name: str = ""
    server_description: str = ""
    use_llm_enrichment: bool = True
    # --no-llm explicite (CLI ou mcp-forge.yaml) : aucun appel LLM, ni
    # enrichissement ni évaluation, en local comme par l'API (2026-11-01).
    # Distinct de use_llm_enrichment, qui passe aussi à False faute de clé
    # locale (cas normal du mode distant).
    no_llm: bool = False
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None
    # Provider OpenAI-compatible (Ollama, LM Studio, vLLM...) — prioritaire sur Anthropic/Groq
    llm_base_url: str | None = None      # ex: http://localhost:11434/v1/chat/completions
    llm_model: str | None = None         # ex: llama3.2, mistral
    generated_language: str = "python"   # python ou typescript
    name_style: NameStyle = NameStyle.SHORT
    force_local: bool = False            # --local : bypass du pipeline distant
    extra_headers: dict[str, str] = Field(default_factory=dict)  # headers HTTP custom (ex: GraphQL auth)
    lang: str = "en"                     # langue des commentaires générés (en | fr)
    bundle_source: bool = False          # copier la codebase source dans output_dir/source/ (opt-in, --bundle-source)
    wait_for_eval: bool = True           # pipeline distant : attendre l'évaluation asynchrone (--no-wait)
    # Instructions personnalisées pour le LLM (lot D, D4) : tout le serveur
    # (FastMCP instructions) et par tool (clé : nom MCP), voir mcp_forge/instructions.py
    server_instructions: str | None = None
    tool_instructions: dict[str, str] = Field(default_factory=dict)
    # Filtre des opérations OpenAPI (tags, préfixes de chemin), voir
    # mcp_forge/discovery/limits.py
    include_tags: list[str] = Field(default_factory=list)
    exclude_tags: list[str] = Field(default_factory=list)
    include_paths: list[str] = Field(default_factory=list)
    exclude_paths: list[str] = Field(default_factory=list)
    # Aucun outputSchema dans les tools générés (liste des tools plus courte)
    no_output_schema: bool = False
    # Option C : textes de la source qui contiennent une formule d'injection
    # cités comme des données (mcp_forge/source_marking.py) ; False :
    # --no-mark-source-descriptions, le constat de l'évaluateur reste majeur
    mark_source_descriptions: bool = True
    # Qui génère : "cli" (local) ou "api" (api/services/generate.py), écrit
    # dans le fichier VERSION avec la vraie version (mcp_forge/build_info.py)
    generated_by: Literal["cli", "api"] = "cli"


class GeneratedServer(BaseModel):
    """Résultat de la génération d'un serveur MCP."""
    server_name: str
    output_dir: str
    files: dict[str, str] = Field(default_factory=dict)  # chemin -> contenu
    tools_count: int = 0
    success: bool = False
    errors: list[str] = Field(default_factory=list)
    eval_report: dict | None = None   # rapport d'évaluation automatique (score, bugs, etc.)
