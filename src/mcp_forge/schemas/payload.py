"""
Contrat JSON entre le CLI (discovery locale) et l'API Azure (enrichissement + génération).

Ce modèle est une vue sanitisée de DiscoveryResult :
- Aucun chemin absolu (source_path exclu)
- headers jamais inclus (vecteur potentiel de fuite de credentials)
- metadata filtrée : seules les clés connues et nécessaires à la génération
- cmd_args réduit au nom du binaire uniquement (pas de chemin absolu)
- coverage : chiffres de couverture du générateur (codebase), bornés, et
  raisons d'exclusion limitées à une liste fermée (voir CoveragePayload)
- language : langage de la codebase, dans une liste fermée (choisit le
  template côté API ; sans lui, toute codebase était générée en Python)
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from mcp_forge.discovery.limits import (
    EXCLUSION_REASONS,
    MAX_OPTION_PARAMETERS,
    MAX_TOOL_PARAMETERS,
    MAX_TOOLS,
)
from mcp_forge.discovery.response_schema import sanitize as sanitize_response_schema
from mcp_forge.discovery.spec_resource import clean_index, clean_spec, index_document
from mcp_forge.instructions import (
    MAX_SERVER_INSTRUCTIONS,
    clean_instructions,
    clean_tool_instructions,
)
from mcp_forge.models import (
    AuthScheme,
    DiscoveredTool,
    DiscoveryResult,
    ParameterType,
    SourceType,
    ToolParameter,
)

# Clés de metadata autorisées par source_type.
# Toute clé absente de cette liste est silencieusement supprimée.
_ALLOWED_METADATA: dict[SourceType, set[str]] = {
    # Types de média du corps (binaire, JSON non standard) : le serveur généré les envoie
    # dans Content-Type ; valeur vérifiée par _MEDIA_TYPE (lot A, 2026-11-16)
    SourceType.OPENAPI:   {"body_media_type", "json_media_type"},
    SourceType.WEBSITE:   {"body_media_type", "json_media_type"},
    SourceType.GRAPHQL:   {"operation", "field_name", "gql_args", "gql_selection"},
    SourceType.CLI_APP:   {"cmd", "param_flags"},
    # Codebase : clés communes ; les clés propres à chaque langage sont dans
    # _CODEBASE_METADATA_BY_LANGUAGE.
    SourceType.CODEBASE:  {"file", "function", "language"},
}

# Langages de codebase acceptés : liste fermée, identique aux clés de
# _LANGUAGE_EXTENSIONS (mcp_forge/discovery/codebase/__init__.py), vérifié par
# tests/test_codebase_language_payload.py.
CODEBASE_LANGUAGES: frozenset[str] = frozenset({
    "bash", "cobol", "cpp", "csharp", "dart", "elixir", "fortran", "go",
    "groovy", "java", "javascript", "julia", "kotlin", "lua", "php",
    "powershell", "python", "r", "ruby", "rust", "scala", "swift", "typescript",
})

# Clés de metadata propres à chaque langage, en plus des clés communes : celles
# qu'écrit le parseur du langage (vérifié par le même test).
_CODEBASE_METADATA_BY_LANGUAGE: dict[str, set[str]] = {
    "bash":       set(),
    "cobol":      {"type", "cobol_params", "cobol_output", "cobol_source_format"},
    "cpp":        {"class", "return_type", "is_header", "cpp_params_full"},
    "csharp":     {"class", "return_type"},
    "dart":       {"class"},
    "elixir":     {"module"},
    "fortran":    {"module", "type"},
    "go":         {"package"},
    "groovy":     {"class"},
    "java":       {"class", "return_type", "is_static", "java_package",
                   "java_param_types", "java_source_root"},
    "javascript": set(),
    "julia":      {"module"},
    "kotlin":     {"receiver"},
    "lua":        set(),
    "php":        {"class"},
    "powershell": set(),
    "python":     {"class", "is_async", "posonly_count"},
    "r":          set(),
    "ruby":       {"class"},
    "rust":       {"module", "impl_type"},
    "scala":      {"type"},
    "swift":      {"type"},
    "typescript": {"module"},
}

# Clés qui contiennent un chemin : relatif à la racine de la codebase
# uniquement (jamais de chemin absolu ni de remontée `..`).
_PATH_METADATA_KEYS: frozenset[str] = frozenset({"file", "java_source_root"})

# Type de média accepté dans la metadata : type/sous-type, paramètres simples ; rien qui
# sorte d'une chaîne d'en-tête (ni guillemet, ni retour à la ligne, ni accolade)
_MEDIA_TYPE_KEYS: frozenset[str] = frozenset({"body_media_type", "json_media_type"})
_MEDIA_TYPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}"
                         r"(?:\s*;\s*[A-Za-z0-9_.-]{1,40}=[A-Za-z0-9_.+-]{1,60}){0,3}")


# Raisons d'exclusion connues (parseurs de codebase et enrichissement LLM).
# Les chiffres de couverture vont dans le prompt de l'évaluateur : une raison
# en texte libre venue du client serait un vecteur d'injection de prompt.
# Toute raison hors de cette liste est regroupée sous OTHER_EXCLUSION_REASON.
# tests/test_coverage_payload.py vérifie que chaque raison écrite par un
# parseur (`exclusions["..."]`) figure ici.
KNOWN_EXCLUSION_REASONS: frozenset[str] = frozenset({
    "abstract or interface methods (no body to execute)",
    "instance methods of types that cannot be instantiated with new X()",
    "methods with a parameter type that cannot be built from a tool argument",
    "test source files (src/test/), not counted as operations",
    "template functions (no exported symbol under their name)",
    "class methods (mangled name, no `this`: not callable through ctypes)",
    "CALL stubs replaced by the matching subprogram",
    "tools removed as semantically redundant during LLM enrichment",
    *EXCLUSION_REASONS,
})
OTHER_EXCLUSION_REASON = "other reasons reported by the client (not recognised by the server)"
_MAX_COUNT = 1_000_000


class CoveragePayload(BaseModel):
    """Chiffres de couverture du générateur (voir
    mcp_forge.discovery.codebase.coverage_summary), transmis à l'évaluateur."""
    discovered: int = Field(ge=0, le=_MAX_COUNT)
    generated: int = Field(ge=0, le=_MAX_COUNT)
    excluded: dict[str, int] = Field(default_factory=dict, max_length=50)

    @field_validator("excluded")
    @classmethod
    def _known_reasons_only(cls, value: dict[str, int]) -> dict[str, int]:
        clean: dict[str, int] = {}
        for reason, count in value.items():
            if not isinstance(count, int) or count < 0:
                continue
            key = reason if reason in KNOWN_EXCLUSION_REASONS else OTHER_EXCLUSION_REASON
            clean[key] = min(clean.get(key, 0) + count, _MAX_COUNT)
        return clean


_MAX_PARAM_DESCRIPTION = 2_000
_MAX_ENUM_VALUES = 100
_MAX_TOOL_DESCRIPTION = 5_000
_MAX_RESPONSE_DESCRIPTION = 2_000
_MAX_TAGS = 20


class ToolParameterPayload(BaseModel):
    name: str                     = Field(max_length=200)
    type: ParameterType           = ParameterType.STRING
    description: str              = Field(default="", max_length=_MAX_PARAM_DESCRIPTION)
    required: bool                = False
    default: Any                  = None
    enum_values: list[str]        = Field(default_factory=list, max_length=_MAX_ENUM_VALUES)
    items_type: ParameterType | None = None
    # Emplacement du paramètre dans la requête HTTP ("query"|"header"|"path"|
    # "body"|"body_array"|"formData"|"file_upload") — calculé côté CLI par la
    # discovery à partir de la spec source. Sans ce champ, l'API régénère le
    # serveur avec un param_in vide et devine la mauvaise forme de requête
    # (params= vs json= vs data=, header vs query) pour chaque paramètre.
    param_in: str                 = Field(default="", max_length=20)


class DiscoveredToolPayload(BaseModel):
    name: str                          = Field(max_length=200)
    description: str                   = Field(max_length=_MAX_TOOL_DESCRIPTION)
    parameters: list[ToolParameterPayload] = Field(default_factory=list, max_length=MAX_TOOL_PARAMETERS)
    # Paramètres facultatifs regroupés dans `options` (tool de plus de
    # MAX_TOOL_PARAMETERS paramètres, voir mcp_forge/discovery/limits.py)
    option_parameters: list[ToolParameterPayload] = Field(default_factory=list, max_length=MAX_OPTION_PARAMETERS)
    http_method: str | None            = Field(default=None, max_length=10)
    endpoint: str | None               = Field(default=None, max_length=2_048)
    base_url: str | None               = Field(default=None, max_length=2_048)
    response_description: str          = Field(default="", max_length=_MAX_RESPONSE_DESCRIPTION)
    # Schéma descriptif de la réponse (lot D, D5) : réduit ici aux clés
    # description/properties/items, borné (il finit dans le code généré)
    response_schema: dict[str, Any] | None = None
    tags: list[str]                    = Field(default_factory=list, max_length=_MAX_TAGS)
    metadata: dict[str, Any]           = Field(default_factory=dict)
    enabled: bool                      = True
    # headers : intentionnellement absent

    @field_validator("response_schema")
    @classmethod
    def _bounded_response_schema(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return sanitize_response_schema(value)


class InstructionsFields(BaseModel):
    """Instructions personnalisées (lot D, D4) : pour tout le serveur, et
    par tool (clé : nom MCP). Nettoyées et bornées ici, à l'entrée de l'API
    comme dans la CLI (voir mcp_forge/instructions.py)."""
    instructions:      str | None = Field(default=None, max_length=MAX_SERVER_INSTRUCTIONS * 2)
    tool_instructions: dict[str, str] = Field(default_factory=dict)

    @field_validator("instructions")
    @classmethod
    def _clean_instructions(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return clean_instructions(value, MAX_SERVER_INSTRUCTIONS, "instructions") or None

    @field_validator("tool_instructions")
    @classmethod
    def _clean_tool_instructions(cls, value: dict[str, str]) -> dict[str, str]:
        return clean_tool_instructions(value or {})


class DiscoveryPayload(InstructionsFields):
    """Payload envoyé par le CLI vers l'API Azure."""
    # False (--no-llm, CLI ≥ 0.4.1) : aucun appel LLM côté API, ni
    # enrichissement, ni évaluation, ni raffinement. Absent (CLI antérieures) :
    # True, comportement inchangé.
    use_llm:       bool = True
    # Copie nettoyée de la spec OpenAPI (lot D, D6) : resource spec://openapi
    # du serveur généré. Nettoyée et bornée de nouveau ici (clean_spec).
    spec_document: dict[str, Any] | None = None
    # Index allégé des opérations (resource spec://openapi/index), nettoyé
    # et borné de nouveau ici (clean_index, index_document)
    spec_index:    list[dict[str, Any]] | None = None
    # --no-output-schema : aucun outputSchema dans les tools générés
    no_output_schema: bool = False
    source_type:   SourceType
    title:         str = Field(default="", max_length=500)
    description:   str = Field(default="", max_length=10_000)
    base_url:      str = Field(default="", max_length=2_048)
    tools:         list[DiscoveredToolPayload] = Field(default_factory=list, max_length=MAX_TOOLS)
    auth_schemes:  list[AuthScheme] = Field(default_factory=list, max_length=20)
    forge_version: str = Field(default="", max_length=50)
    # Couverture du générateur (sources codebase) ; None pour les autres
    # sources et pour les CLI antérieures à 0.4.0.
    coverage:      CoveragePayload | None = None
    # Langage de la codebase (CODEBASE_LANGUAGES) ; None pour les autres
    # sources et pour les CLI antérieures à 0.4.0 (l'API refuse alors une
    # codebase : voir _require_codebase_language dans api/main.py).
    language:      str | None = Field(default=None, max_length=20)
    # source_path / source_url : intentionnellement absents

    @field_validator("spec_document")
    @classmethod
    def _clean_spec_document(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return clean_spec(value) if value is not None else None

    @field_validator("spec_index")
    @classmethod
    def _clean_spec_index(cls, value: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        entries = clean_index(value)
        return entries if index_document(entries) is not None else None

    @field_validator("language")
    @classmethod
    def _known_language_only(cls, value: str | None) -> str | None:
        if value is not None and value not in CODEBASE_LANGUAGES:
            raise ValueError(f"unsupported codebase language: {value[:20]!r}")
        return value

    @model_validator(mode="after")
    def _filter_tools_metadata(self) -> DiscoveryPayload:
        # Appliqué aussi côté API : un client modifié ne peut faire passer ni
        # clé hors liste ni chemin absolu au générateur.
        if self.source_type != SourceType.CODEBASE:
            self.language = None
        allowed = _allowed_metadata(self.source_type, self.language)
        for tool in self.tools:
            tool.metadata = _filter_metadata(tool.metadata, allowed)
        return self

    @classmethod
    def from_discovery_result(
        cls, result: DiscoveryResult, *,
        instructions: str | None = None, tool_instructions: dict[str, str] | None = None,
        use_llm: bool = True, no_output_schema: bool = False,
    ) -> DiscoveryPayload:
        """Construit un payload sécurisé depuis un DiscoveryResult."""
        from mcp_forge import __version__
        language = _language_of(result)
        return cls(
            source_type=result.source_type,
            title=result.title,
            description=result.description,
            base_url=result.base_url,
            tools=[_sanitize_tool(t, result.source_type, language) for t in result.tools],
            auth_schemes=result.auth_schemes,
            forge_version=__version__,
            coverage=_coverage_of(result),
            language=language,
            instructions=instructions,
            tool_instructions=tool_instructions or {},
            use_llm=use_llm,
            no_output_schema=no_output_schema,
            spec_document=(result.metadata or {}).get("spec_document")
            if result.source_type == SourceType.OPENAPI else None,
            spec_index=(result.metadata or {}).get("spec_index")
            if result.source_type == SourceType.OPENAPI else None,
        )


def _language_of(result: DiscoveryResult) -> str | None:
    if result.source_type != SourceType.CODEBASE:
        return None
    language = (result.metadata or {}).get("language")
    return language if language in CODEBASE_LANGUAGES else None


def _allowed_metadata(source_type: SourceType, language: str | None) -> set[str]:
    allowed = _ALLOWED_METADATA.get(source_type, set())
    if source_type == SourceType.CODEBASE and language:
        allowed = allowed | _CODEBASE_METADATA_BY_LANGUAGE[language]
    return allowed


def _coverage_of(result: DiscoveryResult) -> CoveragePayload | None:
    coverage = (result.metadata or {}).get("coverage")
    if not isinstance(coverage, dict):
        return None
    try:
        return CoveragePayload.model_validate(coverage)
    except ValueError:
        return None  # chiffres incohérents : on n'envoie rien plutôt que de bloquer la génération


def _sanitize_parameter(p: ToolParameter) -> ToolParameterPayload:
    """Bornée ici plutôt que refusée par la validation (une seule valeur trop
    longue faisait échouer toute la génération, ex. Stripe : 117 valeurs
    permises) : description coupée ; liste de valeurs permises trop longue
    retirée (tronquée, elle ferait refuser des valeurs valides)."""
    return ToolParameterPayload(
        name=p.name,
        type=p.type,
        description=(p.description or "")[:_MAX_PARAM_DESCRIPTION],
        required=p.required,
        default=p.default,
        enum_values=p.enum_values if len(p.enum_values) <= _MAX_ENUM_VALUES else [],
        items_type=p.items_type,
        param_in=p.param_in,
    )


def _sanitize_tool(
    tool: DiscoveredTool, source_type: SourceType, language: str | None = None,
) -> DiscoveredToolPayload:
    """Convertit un DiscoveredTool en version sanitisée pour le payload."""
    metadata = _filter_metadata(tool.metadata, _allowed_metadata(source_type, language))

    return DiscoveredToolPayload(
        name=tool.name,
        description=(tool.description or "")[:_MAX_TOOL_DESCRIPTION],
        parameters=[_sanitize_parameter(p) for p in tool.parameters],
        option_parameters=[_sanitize_parameter(p) for p in tool.option_parameters],
        http_method=tool.http_method,
        endpoint=tool.endpoint,
        base_url=tool.base_url,
        response_description=(tool.response_description or "")[:_MAX_RESPONSE_DESCRIPTION],
        response_schema=tool.response_schema,
        tags=tool.tags[:_MAX_TAGS],
        metadata=metadata,
        enabled=tool.enabled,
    )


def _filter_metadata(
    metadata: dict[str, Any],
    allowed_keys: set[str],
) -> dict[str, Any]:
    """Filtre et neutralise les champs sensibles du metadata."""
    if not metadata or not allowed_keys:
        return {}

    filtered: dict[str, Any] = {}
    for key in allowed_keys:
        if key not in metadata:
            continue
        value = metadata[key]

        if key == "cmd" and isinstance(value, list) and value:
            # Garde uniquement le nom du binaire, pas le chemin absolu
            # ["/opt/interne/outil", "sous-cmd"] → ["outil", "sous-cmd"]. PureWindowsPath
            # découpe sur « \ » comme sur « / » : sous Linux (l'API), Path gardait entier un
            # chemin Windows (C:\Program Files\…\tool.exe) ; vu par la suite complète sous Linux
            # (tests.yml, 2026-11-18)
            filtered["cmd"] = [PureWindowsPath(str(value[0])).name] + list(value[1:])

        elif key == "posonly_count":
            # Paramètres positionnels seuls (lot C) : un petit entier, rien d'autre
            if isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 64:
                filtered[key] = value

        elif key in _MEDIA_TYPE_KEYS:
            if isinstance(value, str) and _MEDIA_TYPE.fullmatch(value):
                filtered[key] = value

        elif key in _PATH_METADATA_KEYS:
            if not isinstance(value, str):
                continue
            if _is_relative_inside(value):
                filtered[key] = value
            elif key == "file":
                # Chemin absolu ou remontée : seul le nom du fichier est gardé
                filtered["file"] = PureWindowsPath(value).name
            # java_source_root hors de la codebase : supprimé

        else:
            filtered[key] = value

    return filtered


def _is_relative_inside(value: str) -> bool:
    """Vrai pour un chemin relatif qui reste dans la racine de la codebase
    (ni absolu Unix ou Windows, ni lecteur, ni `..`)."""
    posix = PurePosixPath(value.replace("\\", "/"))
    return not (
        posix.is_absolute()
        or PureWindowsPath(value).drive
        or ".." in posix.parts
    )
