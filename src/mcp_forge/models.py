"""
Modèles de données partagés entre tous les modules de mcp-forge.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

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


class DiscoveredTool(BaseModel):
    """Représente un outil MCP découvert depuis une source."""
    name: str
    stable_name: str = ""  # nom figé depuis la discovery (operationId, nom de fonction...) — jamais modifié par le LLM
    description: str
    parameters: list[ToolParameter] = Field(default_factory=list)
    # Métadonnées pour la génération de code
    http_method: str | None = None       # GET, POST, etc.
    endpoint: str | None = None          # /api/users/{id}
    base_url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    response_description: str = ""
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


class GeneratedServer(BaseModel):
    """Résultat de la génération d'un serveur MCP."""
    server_name: str
    output_dir: str
    files: dict[str, str] = Field(default_factory=dict)  # chemin -> contenu
    tools_count: int = 0
    success: bool = False
    errors: list[str] = Field(default_factory=list)
    eval_report: dict | None = None   # rapport d'évaluation automatique (score, bugs, etc.)
