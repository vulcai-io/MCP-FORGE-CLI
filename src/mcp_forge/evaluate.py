"""
mcp-forge evaluate — Évaluation automatique d'un serveur MCP généré.
Usage : mcp-forge evaluate <server.py> [options]
"""
from __future__ import annotations

import json
import os
import re
import sys
import textwrap  # utilisé dans _SYSTEM_PROMPT
from pathlib import Path

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text

from mcp_forge.groq_models import resolve_groq_model

_console = Console()
# 1500 s'est avéré trop court pour un rapport complet (6 scores + points forts +
# bugs détaillés + verdict) dès que le modèle est un peu verbeux — observé en
# production sur des sources CLI/GraphQL/website (json.loads plantait avec
# "Expecting value"/"Expecting ',' delimiter", la réponse étant coupée en
# plein milieu par le fournisseur). Les générations OpenAPI passaient par
# chance sous la barre des 1500 tokens plus souvent que les autres sources.
# 3000 -> 4000 (2026-10-13) : avec la checklist et les justifications (P4),
# le plus long rapport mesuré atteignait 2723 tokens, soit 91 % de l'ancienne
# limite. La limite ne coûte que si elle est réellement utilisée.
_MAX_TOKENS = 4000
_HTTP_TIMEOUT = 180.0
_CODE_CHAR_LIMIT = 200_000

# Providers supportés — détectés automatiquement depuis les variables d'environnement.
# Ordre de priorité : Anthropic > Groq > OpenAI > Mistral > LLM_BASE_URL (Ollama/LM Studio...)
_PROVIDERS = [
    {
        "name": "Anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "url": "https://api.anthropic.com/v1/messages",
        "model": "claude-sonnet-4-6",
        "format": "anthropic",
    },
    {
        "name": "Groq",
        "env_key": "GROQ_API_KEY",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "format": "openai",
    },
    {
        "name": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
        "format": "openai",
    },
    {
        "name": "Mistral",
        "env_key": "MISTRAL_API_KEY",
        "url": "https://api.mistral.ai/v1/chat/completions",
        "model": "mistral-small-latest",
        "format": "openai",
    },
]

CRITERIA = {
    "structure":  "Code structure (readability, organisation, FastMCP idioms)",
    "coverage":   "Endpoint coverage (all tools present and correct)",
    "auth":       "Auth & security (env vars, headers, no hardcoded secrets)",
    "docs":       "Description quality (docstrings, tool names, Args)",
    "fidelity":   "Spec fidelity (types, body vs params, path params)",
    "robustness": "Robustness (timeout, error handling, default values)",
}

# Checklist sécurité obligatoire (P4) : chaque point reçoit un statut
# justifié par une preuve tirée du code. Un "probleme" doit aussi figurer
# dans bugs_critiques et déclenche le plafond de son critère — appliqué par
# le code (_apply_scoring_rules), pas seulement demandé au LLM.
SECURITY_CHECKLIST = {
    "token_header_only": "Access token read ONLY from the Authorization: Bearer header (never the query string)",
    "all_mcp_routes_authenticated": "Every MCP route/request is authenticated (no route or empty token let through)",
    "login_page_escaped": "Every request value written into the login/consent HTML is escaped",
    "no_token_passthrough": "The MCP client's token is never forwarded to the downstream API outside an explicit proxy mode",
    "literals_escaped_for_target_language": "Tool arguments written into generated source code are escaped for THAT language (quotes, interpolation, control characters)",
    "no_shell": "External programs run without a shell (argument list, shell=False)",
    "no_option_injection": "A tool argument cannot be read as an option of the command it is passed to",
    "origin_validated": "The Origin header of MCP HTTP requests is validated",
    "token_audience_and_expiry_checked": "Access tokens issued for another resource, or expired, are refused",
}
_CAPPED_CRITERION = {
    "token_header_only": "auth", "all_mcp_routes_authenticated": "auth", "login_page_escaped": "auth",
    "no_token_passthrough": "auth", "origin_validated": "auth", "token_audience_and_expiry_checked": "auth",
    "literals_escaped_for_target_language": "robustness", "no_shell": "robustness", "no_option_injection": "robustness",
}
_CAPS = {"auth": 6.0, "robustness": 5.0}
_MAJOR_BUG_CAP = 6.0  # un bug majeur/bloquant plafonne le critère qu'il touche
_BLOCKING_GLOBAL_CAP = 6.0
_CHECKLIST_STATUSES = ("ok", "probleme", "non_verifiable", "non_applicable")

# Schéma JSON du rapport, utilisé pour forcer une sortie structurée côté
# fournisseur (Anthropic tool-use, Groq/OpenAI response_format=json_object)
# plutôt que de faire confiance à du texte libre. Root cause du bug observé
# en prod : un modèle qui génère lui-même le JSON en texte libre échappe mal
# les guillemets à l'intérieur d'une description (fréquent sur du contenu
# CLI/GraphQL/website, ex: `git commit -m "message"`), ce qui casse
# json.loads en plein milieu de la réponse — jamais une histoire de longueur
# tronquée malgré les apparences.
_REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        # Ordre voulu : constater (checklist, bugs), justifier, PUIS noter.
        "checklist_securite": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "point": {"type": "string", "enum": list(SECURITY_CHECKLIST)},
                    "statut": {"type": "string", "enum": list(_CHECKLIST_STATUSES)},
                    "preuve": {"type": "string"},
                },
                "required": ["point", "statut", "preuve"],
            },
        },
        "bugs_critiques": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "ligne": {"type": ["integer", "null"]},
                    "severite": {"type": "string", "enum": ["bloquant", "majeur", "mineur"]},
                    "critere": {"type": "string", "enum": list(CRITERIA)},
                    "extrait_code": {"type": "string"},
                },
                "required": ["description", "severite", "critere", "extrait_code"],
            },
        },
        "justifications_par_critere": {
            "type": "object",
            "properties": {k: {"type": "string"} for k in CRITERIA},
            "required": list(CRITERIA.keys()),
        },
        "scores_par_critere": {
            "type": "object",
            "properties": {k: {"type": "number"} for k in CRITERIA},
            "required": list(CRITERIA.keys()),
        },
        "score_global": {"type": "number"},
        "points_forts": {"type": "array", "items": {"type": "string"}},
        "ameliorations_prioritaires": {"type": "array", "items": {"type": "string"}},
        "verdict_beta": {"type": "string"},
    },
    "required": [
        "checklist_securite", "bugs_critiques", "justifications_par_critere",
        "scores_par_critere", "score_global", "points_forts", "ameliorations_prioritaires", "verdict_beta",
    ],
}

_SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert in MCP (Model Context Protocol) and Python code quality.
    You evaluate MCP servers automatically generated by mcp-forge (a VulcAi tool, beta version).
    Your role is to provide a structured, honest and actionable evaluation.

    IMPORTANT CONTEXT — read before evaluating:
    1. HTTP methods (GET, POST, PUT, PATCH, DELETE) are extracted directly from the OpenAPI/Swagger spec.
       Do NOT flag an HTTP method as wrong unless the code uses a different method than what is declared
       in the function name or docstring. The spec is the ground truth — trust it.
    1b. The choice of `params=` (query string), `json=`/`data=` (request body — JSON vs
       form-urlencoded) and header injection (values merged into the `httpx.Client(headers=...)`
       call, e.g. via `_extra_headers`) was derived deterministically from the source spec's
       parameter locations (`in: query/path/header/body`/`formData`), not guessed. Trust it as
       ground truth exactly like the HTTP method: do NOT suggest switching `params=` to
       `data=`/`json=` or vice versa, and do NOT suggest moving a parameter already merged into
       headers to a query string or body, purely based on generic REST conventions (e.g. "a POST
       endpoint should use a body"). Only flag it if the code is internally inconsistent — e.g. the
       same parameter is referenced in both `params=` and `json=` for the same call, or a value the
       code itself declares as a header is also duplicated into `params=`.
    2. This is an MCP server: tools receive text/JSON values from an LLM, never raw binary data.
       File upload parameters are correctly represented as `file_path: str` (the caller passes a local path).
       Do NOT flag file_path parameters or `open(file_path, "rb")` patterns as incorrect.
    3. The code is auto-generated from a spec. Patterns like `{k: v for k, v in {...}.items() if v is not None}`
       are intentional and correct — do not flag them as style issues.
    4. Severity rules — be strict:
       - "bloquant": code that will raise an exception or crash at runtime (SyntaxError, NameError, etc.)
       - "majeur": incorrect API behavior (wrong endpoint, missing required param, broken auth)
       - "mineur": style, readability, or minor improvements only
       Only report bugs you are confident about. Prefer fewer, accurate bugs over many speculative ones.
    5. `_BEARER_TOKEN = os.getenv("BEARER_TOKEN", "")` reads from an environment variable — this is NOT
       a hardcoded secret. Do NOT flag it as a security vulnerability.
    6. Checks like `if email is None or email == "": return "Error: ..."` ARE valid input validation for
       an MCP server. Do NOT flag them as missing or insufficient validation.
    7. The remote HTTP mode (`_build_http_app()`, launched from `if __name__ == "__main__":`, MCP served
       over Streamable HTTP on `/mcp`) implements a complete OAuth 2.0 Authorization Code + PKCE server (login page, /oauth/authorize, /oauth/token,
       PKCE S256 verification, CORS, rate limiting). Do NOT suggest "adding OAuth" or "using a more secure
       authentication method": its PRESENCE is a given. Whether this implementation CONFORMS to the MCP
       specification is a separate question, judged with rule 14.
    8. Explicit timeouts (`timeout=30`, `timeout=120`) are correct and intentional. Do NOT flag them as
       potential timeout issues or suggest changing them.
    9. `_request_token: ContextVar[str]` is a standard per-async-task token mechanism. It is NOT a
       security vulnerability and NOT shared between users.
    10. If `_check_rate_limit` is present in the code, the OAuth endpoints already have rate limiting —
        do NOT flag it as missing. If it is absent, you may flag it as a minor improvement.
    11. `_verify_pkce` wraps `code_verifier.encode("ascii")` in a try/except — this is correct and safe.
        Do NOT flag it as a security vulnerability.
    12. Codebase servers (tools that compile/run source code, e.g. Java, COBOL, C++, via a driver):
        the parameter and return types written in the tool (e.g. `_java_literal(x, "Key")`) were
        extracted from the real source signatures — trust them as ground truth, like the HTTP method
        in rule 1. Object-typed parameters are built at runtime by a generic converter (enum constant,
        static String factory such as valueOf/of/fromString/parse, or a public String constructor —
        e.g. `Throwable(String)`): do NOT claim a conversion will fail unless you are certain the
        target type has none of these. A method that needs a live host runtime (e.g. an application
        singleton that is only initialised inside a running server) returns the Java exception
        message instead of a result: this is an inherent limit of calling a library outside its
        host, at most "mineur", not a generation bug.
    13. Very large servers are shown as an EXCERPT: the beginning (all infrastructure and the first
        tools) and the end (auth, entry point), with an explicit marker stating how many tool
        definitions were omitted in between. Omitted tools follow the same pattern as the ones shown.
        Do NOT report anything as missing, absent or inconsistent unless it would necessarily appear
        in the parts you can see, and do NOT cite tools you have not seen. Score coverage from the
        stated number of tools plus the ones shown.
    14. Conformity with the MCP specification (2026-07-28) for HTTP servers — check:
        - the access token is read ONLY from the `Authorization: Bearer` header; a token accepted
          from the URI query string (e.g. `?token=`) is a "majeur" bug, never a strength;
        - the RFC 9728 metadata endpoint `/.well-known/oauth-protected-resource` exists, and 401
          responses carry `resource_metadata="..."` in `WWW-Authenticate`;
        - the token audience is validated (RFC 8707: a token issued for another resource is refused);
        - HTTP status codes: 401 for a missing/invalid/expired token, 403 for insufficient
          permissions (only relevant if scopes are managed), 400 for a malformed authorization request;
        - every MCP request is authenticated, not only the opening of a stream;
        - transport: Streamable HTTP (single MCP endpoint). Serving MCP over the deprecated SSE transport
          (`/sse` + `/messages/`) is "mineur".
        Report a gap only when it is certain in the visible code (consistent with rules 4 and 13).
    15. SECURITY CHECKLIST (mandatory, field `checklist_securite`). Before scoring, answer EVERY point below
        with "ok", "probleme", "non_verifiable" (only when the relevant code is outside the excerpt, rule
        13) or "non_applicable", and give as `preuve` the line number or a short code excerpt you relied on.
        When "Tool facts" precede the code, they were established by executing or analysing the server:
        they are authoritative — copy them for the matching checklist points and never contradict them. A point that does
        not apply is "ok" with the reason as proof (e.g. "no generated source code: HTTP API wrapper").
        The proof must be the code line that actually performs the operation, found by following the real
        call path (which function is called with the value, what it returns). A comment, a docstring, a
        name, or a helper that exists in the file but is not called on that path is NOT proof.
        Rule 4 asks you not to speculate; it does NOT allow skipping a checklist point: answer each one from
        the code you can see. Every "probleme" MUST also appear in `bugs_critiques` (severity "majeur" at
        least) and caps the matching criterion (rule 17).
        - token_header_only: access token read ONLY from the Authorization: Bearer header (never the query string)
        - all_mcp_routes_authenticated: every MCP route/request is authenticated (no route or empty token let through)
        - login_page_escaped: every request value written into the login/consent HTML is escaped
        - no_token_passthrough: the MCP client's token is never forwarded to the downstream API outside an explicit proxy mode
        - literals_escaped_for_target_language: tool arguments written into generated source code are escaped for THAT language
        - no_shell: external programs run without a shell
        - no_option_injection: a tool argument cannot be read as an option of the command it is passed to
        - origin_validated: the Origin header of MCP HTTP requests is validated
        - token_audience_and_expiry_checked: access tokens issued for another resource, or expired, are refused
    16. ANCHORED SCORING GRID — choose the band from the evidence, then the score within it. Use the whole
        scale: 7-8 means "correct, with small defects", it is not a default.
        - structure: 9-10 coherent generated code, factored helpers, one mechanism per need; 7-8 a few
          harmless redundancies (duplicate import); 4-6 competing mechanisms, logic copied per tool;
          0-3 does not import, tools not registered.
        - coverage: 9-10 every operation of the source exposed by a working tool, exclusions justified;
          7-8 a few useful operations missing or redundant tools; 4-6 a notable share of tools cannot work;
          0-3 most tools unusable. A tool that WOULD work once its host application is running (rule 12)
          does not count as non-working; a tool that can never execute (it always refuses, is a stub, or
          cannot be called in isolation) DOES count as non-working.
        - auth: 9-10 secrets only from the environment, token from the header only, EVERY MCP request
          authenticated, token audience checked, RFC 9728 metadata, no passthrough, escaped login page,
          Origin validated; 7-8 conformant, minor gaps; 4-6 ONE major gap (token in the query string, MCP
          route without auth or empty token accepted, audience not checked, passthrough, unescaped login
          page); 0-3 hardcoded secret, bypassable auth, several major gaps.
        - docs: 9-10 faithful description for every tool, parameters and return described, destructive
          actions flagged; 7-8 correct but generic in places; 4-6 truncated, misleading or missing for a
          notable share; 0-3 unusable.
        - fidelity: 9-10 types and parameter locations identical to the source (rules 1, 1b, 12), literals
          valid for the target language; 7-8 inaccuracies with no effect on common calls; 4-6 a defect that
          breaks part of the calls (wrong type, invalid literal, wrong native return type, instantiating an
          abstract class); 0-3 most calls do not match the source.
        - robustness: 9-10 timeouts, clear errors, bounded inputs, NO injection path (literals escaped per
          language, no shell, no injectable option); 7-8 robust, a few unclear errors; 4-6 ONE injection
          path (code, command or argument) or a reproducible crash on a common input; 0-3 trivial arbitrary
          code execution, systematic crash.
    17. CAPS (also enforced by the tool after your answer): each bug names the criterion it affects
        (field `critere`) and quotes, in `extrait_code`, the exact line(s) of the file it is about, copied
        verbatim. A "majeur" or "bloquant" bug caps that criterion at 6 ONLY if the tool finds the quote in
        the file or confirms the bug mechanically; a claim contradicted by the tool's checks (compilation,
        import, names, standard library) is downgraded to "a_verifier". A "probleme" on token_header_only,
        all_mcp_routes_authenticated, login_page_escaped, no_token_passthrough or origin_validated caps
        auth at 6; a "probleme" on literals_escaped_for_target_language, no_shell or no_option_injection
        caps robustness at 5; any "bloquant" bug caps score_global at 6. score_global is the mean of the six
        criteria after caps, rounded to one decimal (lower only if the global cap applies).
    18. JUSTIFICATIONS (field `justifications_par_critere`): for each criterion, one or two sentences written
        BEFORE choosing its score, naming the band and the bug or code element that places it there.
    19. EXCESSIVE AGENCY (OWASP LLM): a tool that performs a destructive or high-impact action (deletion,
        overwrite, sending, payment, irreversible reset...) without saying so in its docstring is reported,
        at most as "mineur".
    20. Never claim that a function or module of the target language's standard library does not exist.
        When in doubt, do not report it.
    21. Security consequences are "majeur" at least: exposure of secrets or credentials (in logs, responses
        or to third parties), access to files or network destinations chosen by the caller, and execution
        of caller-controlled code or commands.

    Respond ONLY with valid JSON, no markdown, no text before or after.
    Expected exact structure:

    {
      "checklist_securite": [
        {"point": "<one of the rule 15 points>", "statut": "ok|probleme|non_verifiable", "preuve": "<line or code>"}
      ],
      "bugs_critiques": [
        {"description": "...", "ligne": <int or null>, "severite": "bloquant|majeur|mineur",
         "critere": "structure|coverage|auth|docs|fidelity|robustness", "extrait_code": "<exact line from the file>"}
      ],
      "justifications_par_critere": {
        "structure": "...", "coverage": "...", "auth": "...", "docs": "...", "fidelity": "...", "robustness": "..."
      },
      "scores_par_critere": {
        "structure":  <float 0-10>,
        "coverage":   <float 0-10>,
        "auth":       <float 0-10>,
        "docs":       <float 0-10>,
        "fidelity":   <float 0-10>,
        "robustness": <float 0-10>
      },
      "score_global": <float 0-10>,
      "points_forts": ["...", "..."],
      "ameliorations_prioritaires": ["...", "..."],
      "verdict_beta": "..."
    }
""").strip()




# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

_TAIL_SHARE = 0.3


def _excerpt_code(code: str, limit: int = _CODE_CHAR_LIMIT) -> str:
    """Code montré à l'évaluateur : intégral s'il tient dans `limit`, sinon
    le DÉBUT et la FIN, avec le milieu omis explicitement.

    2026-10-13 — trouvé sur un vrai gros serveur (une vraie API Java de plugins, 1316
    tools, 768 Ko) : une simple coupe des 200 premiers Ko cachait toute la
    fin du fichier, où vivent l'auth OAuth 2.0 + PKCE et le point d'entrée.
    L'évaluateur notait alors "auth" 5/10 pour une "absence totale
    d'authentification" qu'il ne pouvait tout simplement pas voir. Le
    milieu omis n'est fait que de définitions de tools répétant le même
    motif que celles montrées au début."""
    if len(code) <= limit:
        return code
    tail_len = int(limit * _TAIL_SHARE)
    head = code[:limit - tail_len]
    head = head[:head.rfind("\n") + 1] or head
    tail = code[-tail_len:]
    tail = tail[tail.find("\n") + 1:] or tail
    middle = code[len(head):len(code) - len(tail)]
    omitted_tools = middle.count("@mcp.tool(")
    note = f"# ... [{len(middle)} chars omitted"
    if omitted_tools:
        note += f": {omitted_tools} more @mcp.tool definitions following the same pattern as those above"
    note += " — the end of the file follows, unabridged] ...\n"
    return head + note + tail


def _facts_section(facts: dict | None) -> str:
    """Faits établis par l'outil (exécution / analyse), donnés au LLM avant
    le code. Vide si aucun fait n'a été établi."""
    if not facts:
        return ""
    parts = []
    compiled = facts.get("compile")
    if compiled is not None:
        parts.append("- compilation: " + ("OK" if compiled.get("ok") else f"FAILED ({compiled.get('error')})"))
        imported = facts.get("import")
        if imported is not None:
            if imported.get("ok"):
                parts.append("- import of the module in an isolated subprocess: OK")
            else:
                parts.append(f"- import of the module in an isolated subprocess: FAILED "
                             f"({imported.get('kind')}: {imported.get('error')})")
        undefined = facts.get("undefined_names")
        if undefined is not None:
            parts.append("- undefined names (pyflakes): " + (", ".join(undefined) if undefined else "none"))
    if facts.get("dynamic") is not None:
        from mcp_forge.eval_dynamic import facts_text
        parts.append(facts_text(facts["dynamic"]))
    if facts.get("static_analyzers") is not None:
        from mcp_forge.eval_static import facts_text as static_text
        parts.append(static_text(facts["static_analyzers"]))
    return ("Tool facts (authoritative):\n" + "\n".join(parts) + "\n") if parts else ""


def _build_prompt(code: str, context: str | None, facts: dict | None = None) -> str:
    lines = []
    if context:
        lines.append(f"Context: {context}\n")
    section = _facts_section(facts)
    if section:
        lines.append(section)
    lines.append("Server code to evaluate:\n```python")
    lines.append(_excerpt_code(code))
    lines.append("```")
    lines.append("\nEvaluate this server and return only the requested JSON.")
    return "\n".join(lines)


def _select_provider(name: str, model: str | None, forced_keys: dict[str, str | None]) -> tuple[dict, str]:
    """Fournisseur d'évaluation imposé par son nom (anthropic, groq, openai,
    mistral, local), avec un modèle éventuellement imposé. La clé vient de
    `forced_keys` (clé passée explicitement) ou de l'environnement.

    Sert à évaluer avec un autre fournisseur/modèle que celui qui a généré
    le serveur (biais d'auto-préférence d'un juge LLM)."""
    wanted = name.strip().lower()
    if wanted in ("local", "openai-compat", "llm_base_url"):
        base_url = os.getenv("LLM_BASE_URL", "")
        if not base_url:
            raise RuntimeError("Evaluation provider 'local' needs LLM_BASE_URL.")
        chosen = model or os.getenv("LLM_MODEL", "llama3.2")
        return {"name": f"OpenAI-compat ({chosen})", "env_key": "LLM_BASE_URL", "url": base_url,
                "model": chosen, "format": "openai"}, "local"
    provider = next((p for p in _PROVIDERS if p["name"].lower() == wanted), None)
    if provider is None:
        names = ", ".join(p["name"].lower() for p in _PROVIDERS) + ", local"
        raise RuntimeError(f"Unknown evaluation provider '{name}' (expected one of: {names}).")
    key = forced_keys.get(provider["name"]) or os.getenv(provider["env_key"], "")
    if not key:
        raise RuntimeError(f"Evaluation provider '{provider['name']}' needs {provider['env_key']}.")
    if model:
        provider = {**provider, "model": model}
    elif provider["name"] == "Groq":
        provider = {**provider, "model": resolve_groq_model(key)}
    return provider, key


def _eval_overrides(provider: str | None, model: str | None) -> tuple[str | None, str | None]:
    """Fournisseur / modèle d'évaluation imposés : arguments, sinon variables
    d'environnement MCP_FORGE_EVAL_PROVIDER / MCP_FORGE_EVAL_MODEL."""
    return (provider or os.getenv("MCP_FORGE_EVAL_PROVIDER") or None,
            model or os.getenv("MCP_FORGE_EVAL_MODEL") or None)


def _detect_provider(forced_key: str | None, provider: str | None = None,
                     model: str | None = None) -> tuple[dict, str]:
    """Détecte le premier provider disponible dans l'environnement.

    Si forced_key est fourni, on l'utilise avec Anthropic (comportement --api-key).
    `provider` / `model` (ou MCP_FORGE_EVAL_PROVIDER / MCP_FORGE_EVAL_MODEL)
    imposent le fournisseur et le modèle d'évaluation.
    Retourne (provider_config, api_key) ou lève RuntimeError si aucun provider trouvé.
    """
    provider, model = _eval_overrides(provider, model)
    if provider:
        return _select_provider(provider, model, {"Anthropic": forced_key})
    if forced_key:
        chosen = _PROVIDERS[0]  # Anthropic avec clé explicite
        return ({**chosen, "model": model} if model else chosen), forced_key

    # LLM_BASE_URL en dernier recours (Ollama, LM Studio...)
    llm_base_url = os.getenv("LLM_BASE_URL", "")
    llm_model = os.getenv("LLM_MODEL", "llama3.2")

    for candidate in _PROVIDERS:
        key = os.getenv(candidate["env_key"], "")
        if key:
            if model:
                candidate = {**candidate, "model": model}
            elif candidate["name"] == "Groq":
                candidate = {**candidate, "model": resolve_groq_model(key)}
            return candidate, key

    if llm_base_url:
        chosen = model or llm_model
        return {
            "name": f"OpenAI-compat ({chosen})",
            "env_key": "LLM_BASE_URL",
            "url": llm_base_url,
            "model": chosen,
            "format": "openai",
        }, "local"

    raise RuntimeError(
        "No LLM API key found. Set one of: ANTHROPIC_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, or LLM_BASE_URL"
    )


_EVAL_TOOL_NAME = "submit_evaluation"


def _call_llm(code: str, context: str | None, provider: dict, api_key: str, facts: dict | None = None) -> dict:
    """Appelle le LLM et renvoie le rapport parsé.

    Force une sortie structurée côté fournisseur plutôt que de faire
    confiance à du JSON en texte libre : Anthropic via tool-use (le rapport
    arrive déjà parsé, correctement échappé, dans `content[].input`), les
    providers OpenAI-compatibles (Groq, OpenAI...) via
    `response_format: json_object`. Root cause du bug évité : un modèle qui
    écrit lui-même son JSON en texte libre échappe parfois mal un guillemet
    à l'intérieur d'une description (fréquent sur du contenu CLI/GraphQL/
    website, ex: `git commit -m "message"`), ce qui casse `json.loads` en
    plein milieu de la réponse — la sortie contrainte élimine cette classe
    d'erreur à la source.
    """
    prompt = _build_prompt(code, context, facts)

    if provider["format"] == "anthropic":
        payload = {
            "model": provider["model"],
            "max_tokens": _MAX_TOKENS,
            "system": _SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [{
                "name": _EVAL_TOOL_NAME,
                "description": "Submit the structured MCP server evaluation report.",
                "input_schema": _REPORT_SCHEMA,
            }],
            "tool_choice": {"type": "tool", "name": _EVAL_TOOL_NAME},
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    else:  # openai-compatible (Groq, OpenAI, Ollama...)
        payload = {
            "model": provider["model"],
            "max_tokens": _MAX_TOKENS,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }

    # 60 s ne suffisaient plus (2026-10-13) : avec la checklist, les
    # justifications et 4000 tokens de sortie, l'évaluation d'un gros serveur
    # (~57 000 tokens d'entrée) dépassait la minute (ReadTimeout).
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        response = client.post(provider["url"], json=payload, headers=headers)

    if not response.is_success:
        raise RuntimeError(f"{provider['name']} API — HTTP {response.status_code}: {response.text}")

    data = response.json()
    if provider["format"] == "anthropic":
        tool_use = next(
            (block for block in data.get("content", []) if block.get("type") == "tool_use"),
            None,
        )
        if tool_use is None:
            raise RuntimeError(f"{provider['name']} did not return a tool_use block")
        usage = {"input_tokens": data.get("usage", {}).get("input_tokens"),
                 "output_tokens": data.get("usage", {}).get("output_tokens"), "stop_reason": data.get("stop_reason"),
                 "max_tokens": _MAX_TOKENS}
        return _with_metadata(_finalize(_normalize_report(tool_use["input"]), code, facts), code, provider, usage)

    text = data["choices"][0]["message"]["content"].strip()
    if text.startswith("```"):
        text = "\n".join(
            line for line in text.splitlines()
            if not line.strip().startswith("```")
        ).strip()

    usage = {"input_tokens": (data.get("usage") or {}).get("prompt_tokens"),
             "output_tokens": (data.get("usage") or {}).get("completion_tokens"),
             "stop_reason": data["choices"][0].get("finish_reason"), "max_tokens": _MAX_TOKENS}
    return _with_metadata(_finalize(_normalize_report(json.loads(text)), code, facts), code, provider, usage)


def _with_metadata(report: dict, code: str, provider: dict, usage: dict | None = None) -> dict:
    """Champs informatifs ajoutés au rapport (pas produits par le LLM) :
    qui a évalué (fournisseur et modèle — utile pour séparer générateur et
    juge), et quelle part du code il a réellement vue (extrait au-delà de
    _CODE_CHAR_LIMIT, voir _excerpt_code)."""
    excerpt = _excerpt_code(code)
    omitted = re.search(r"\[(\d+) chars omitted", excerpt)
    report["evaluator"] = {"provider": provider["name"], "model": provider["model"]}
    report["chars_total"] = len(code)
    report["chars_evaluated"] = len(code) - (int(omitted.group(1)) if omitted else 0)
    report["tools_omitted"] = (code.count("@mcp.tool(") - excerpt.count("@mcp.tool(")) if omitted else 0
    # Tokens de sortie réellement consommés et motif d'arrêt : vérifie que
    # le rapport tient dans _MAX_TOKENS (stop_reason "max_tokens" = coupé).
    report["usage"] = usage or {}
    return report


_LIST_FIELDS = ("points_forts", "bugs_critiques", "ameliorations_prioritaires")


def _normalize_report(report: dict) -> dict:
    """Corrige les champs censés être des listes mais renvoyés en chaîne.

    Le mode `json_object` de Groq garantit du JSON top-level valide mais pas
    le respect du schéma imbriqué qu'on lui demande : le modèle renvoie
    parfois un tableau tout entier ré-encodé en une seule chaîne JSON (ex:
    `"bugs_critiques": "[{\\"description\\": ...}]"` au lieu d'un vrai
    tableau). Sans ce filet, chaque caractère de la chaîne finit itéré comme
    un faux "bug" d'un caractère dans render_report()/refine.py.
    """
    for field in _LIST_FIELDS:
        value = report.get(field)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = [value] if value else []
            report[field] = parsed if isinstance(parsed, list) else [parsed]
    # Champs ajoutés par P4 : absents des anciens rapports (avant 2026-10-13)
    # ou d'une réponse incomplète — valeurs neutres, pour que l'affichage et
    # les outils fonctionnent avec les deux formats.
    if not isinstance(report.get("justifications_par_critere"), dict):
        report["justifications_par_critere"] = {}
    checklist = report.get("checklist_securite")
    if isinstance(checklist, str):
        try:
            checklist = json.loads(checklist)
        except json.JSONDecodeError:
            checklist = []
    aliases = {"problem": "probleme", "problème": "probleme", "not_verifiable": "non_verifiable",
               "non vérifiable": "non_verifiable", "non_vérifiable": "non_verifiable"}
    items = []
    for item in checklist if isinstance(checklist, list) else []:
        if isinstance(item, dict) and item.get("point"):
            status = str(item.get("statut", "")).strip().lower()
            items.append({**item, "statut": aliases.get(status, status)})
    report["checklist_securite"] = items
    return report


def _finalize(report: dict, code: str, facts: dict | None) -> dict:
    """Confronte les bugs aux faits mécaniques (eval_checks), puis applique
    les règles de notation. Sans faits (appel direct de _call_llm par un
    test), seules les règles de notation s'appliquent."""
    if facts is not None:
        from mcp_forge.eval_checks import verify_report
        dynamic = facts.get("dynamic")
        if dynamic is not None:
            from mcp_forge.eval_dynamic import checklist_items
            tested = checklist_items(dynamic)
            tested_points = {item["point"] for item in tested}
            report["checklist_securite"] = tested + [
                item for item in report.get("checklist_securite", []) if item.get("point") not in tested_points]
        verify_report(report, code, facts)
    return _apply_scoring_rules(report)


def _apply_scoring_rules(report: dict) -> dict:
    """Règles de notation appliquées par le code (P4), indépendamment de ce
    que le LLM a respecté : un "probleme" de checklist figure dans les bugs
    et plafonne son critère, un bug bloquant plafonne la note globale, et
    la note globale est la moyenne des critères après plafonds. Les notes
    d'origine sont conservées dans `scores_bruts` pour comparaison."""
    scores = report.get("scores_par_critere") or {}
    if not all(isinstance(scores.get(c), (int, float)) for c in CRITERIA):
        return report  # rapport incomplet : rien à recalculer
    report["scores_bruts"] = {"score_global": report.get("score_global"), "scores_par_critere": dict(scores)}
    bugs = report.setdefault("bugs_critiques", [])
    for item in report.get("checklist_securite", []):
        if item.get("statut") != "probleme":
            continue
        point = item.get("point", "")
        criterion = _CAPPED_CRITERION.get(point)
        # Plafond seulement si la preuve est vérifiée (eval_checks) ; un
        # rapport non vérifié (ancien format) garde le comportement d'avant.
        if criterion and item.get("cap_eligible", True):
            scores[criterion] = min(float(scores[criterion]), _CAPS[criterion])
        mentioned = any(point in str(b.get("description", "")) for b in bugs if isinstance(b, dict))
        if not mentioned:
            bugs.append({
                "description": f"[{point}] {SECURITY_CHECKLIST.get(point, point)} — problème relevé dans la "
                               f"checklist : {item.get('preuve', '')}",
                "ligne": None, "severite": "majeur", "critere": criterion or "robustness",
                "cap_eligible": item.get("cap_eligible", True),
                "verification": "issu de la checklist" + ("" if item.get("cap_eligible", True)
                                                          else " (preuve non retrouvée dans le fichier)"),
            })
    for bug in bugs:
        criterion = bug.get("critere") if isinstance(bug, dict) else None
        if (criterion in scores and bug.get("severite") in ("majeur", "bloquant")
                and bug.get("cap_eligible", True)):
            scores[criterion] = min(float(scores[criterion]), _MAJOR_BUG_CAP)
    global_score = round(sum(float(scores[c]) for c in CRITERIA) / len(CRITERIA), 1)
    if any(isinstance(b, dict) and b.get("severite") == "bloquant" and b.get("cap_eligible", True) for b in bugs):
        global_score = min(global_score, _BLOCKING_GLOBAL_CAP)
    report["scores_par_critere"] = scores
    report["score_global"] = global_score
    return report


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _score_style(score: float) -> str:
    if score >= 7.5:
        return "bold green"
    if score >= 5.0:
        return "bold yellow"
    return "bold red"


def _score_bar(score: float, width: int = 20) -> Text:
    filled = round(score / 10 * width)
    style = _score_style(score)
    t = Text()
    t.append(f"{score:.1f}/10", style=style)
    t.append("  ")
    t.append("█" * filled, style=style)
    t.append("░" * (width - filled), style="dim")
    return t


def _severity_style(sev: str) -> tuple[str, str]:
    mapping = {
        "bloquant": ("BLOCKING", "bold red"),
        "majeur":   ("MAJOR",    "bold yellow"),
        "mineur":   ("minor",    "dim"),
        # bug contredit par les vérifications mécaniques (eval_checks) :
        # affiché, mais sans effet sur la note
        "a_verifier": ("TO VERIFY (contradicted by checks)", "italic magenta"),
    }
    return mapping.get(sev.lower(), (sev.upper(), "dim"))


def render_report(result: dict, server_path: str, output_json: bool = False) -> None:
    if output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    score = result.get("score_global", 0)

    # Header
    _console.print()
    _console.print(Panel(
        f"[dim]{server_path}[/dim]",
        title="[bold cyan]mcp-forge evaluate[/bold cyan]",
        border_style="cyan",
        padding=(0, 2),
    ))

    # Global score
    _console.print()
    t = Text("  Global score   ")
    t.append_text(_score_bar(score))
    _console.print(t)
    _console.print()

    # Per criterion table
    table = Table(box=box.SIMPLE, show_header=True, header_style="dim", padding=(0, 2))
    table.add_column("Criterion", style="dim", min_width=45)
    table.add_column("Score", justify="right")
    justifications = result.get("justifications_par_critere") or {}
    if justifications:
        table.add_column("Why", style="dim")
    for key, label in CRITERIA.items():
        s = result.get("scores_par_critere", {}).get(key, 0)
        score_text = Text(f"{s:.1f}/10", style=_score_style(s))
        if justifications:
            table.add_row(label, score_text, str(justifications.get(key, "")))
        else:
            table.add_row(label, score_text)
    _console.print(table)

    # Security checklist (reports from 2026-10-13 on; absent from older ones)
    checklist = result.get("checklist_securite") or []
    if checklist:
        _console.rule(style="dim")
        _console.print("\n[bold]  Security checklist[/bold]")
        marks = {"ok": "[green]ok[/green]", "probleme": "[red]problem[/red]",
                 "non_verifiable": "[yellow]not verifiable[/yellow]"}
        for item in checklist:
            mark = marks.get(item.get("statut"), item.get("statut", "?"))
            _console.print(f"  {mark:28s} {item.get('point', '')} — [dim]{item.get('preuve', '')}[/dim]")

    # Strengths
    pts = result.get("points_forts", [])
    if pts:
        _console.rule(style="dim")
        _console.print("\n[bold]  Strengths[/bold]")
        for p in pts:
            _console.print(f"  [green]✓[/green]  {p}")

    # Bugs
    bugs = result.get("bugs_critiques", [])
    if bugs:
        _console.rule(style="dim")
        _console.print("\n[bold]  Bugs detected[/bold]")
        for b in bugs:
            # Groq's json_object mode only guarantees valid JSON, not that
            # each array item matches the object schema we asked for — it
            # sometimes returns a bare string instead of {description, ligne,
            # severite}. Fall back gracefully instead of crashing the render.
            if not isinstance(b, dict):
                b = {"description": str(b)}
            label, style = _severity_style(b.get("severite", ""))
            ligne = b.get("ligne")
            loc = f" line {ligne}" if ligne else ""
            _console.print(f"  [{style}][{label}][/{style}][dim]{loc}[/dim]  {b.get('description', '')}")

    # Improvements
    amelios = result.get("ameliorations_prioritaires", [])
    if amelios:
        _console.rule(style="dim")
        _console.print("\n[bold]  Priority improvements[/bold]")
        for i, a in enumerate(amelios, 1):
            _console.print(f"  [dim]{i}.[/dim]  {a}")

    # Verdict
    verdict = result.get("verdict_beta", "")
    if verdict:
        _console.rule(style="dim")
        _console.print(Panel(
            verdict,
            title="[bold]Beta verdict[/bold]",
            border_style="dim",
            padding=(0, 2),
        ))

    _console.print()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def coverage_context(coverage: dict | None, code: str) -> str | None:
    """Chiffres de couverture du générateur, rédigés pour l'évaluateur
    (étape 3) : il juge la qualité des tools vus et la pertinence des
    exclusions, au lieu d'estimer leur nombre à partir d'un extrait."""
    if not coverage:
        return None
    exposed = code.count("@mcp.tool(")
    excluded = coverage.get("excluded") or {}
    lines = [
        "Coverage facts from the generator (authoritative): the source analysis found "
        f"{coverage.get('discovered')} callable operations; the server file defines {exposed} tools "
        "(all of them are in the file, even when the excerpt omits some).",
    ]
    if excluded:
        lines.append("Excluded on purpose: " + "; ".join(f"{count} {reason}" for reason, count in excluded.items()) + ".")
    counted = sum(v for k, v in excluded.items() if "not counted as operations" not in k)
    unexplained = (coverage.get("discovered") or 0) - counted - exposed
    if unexplained > 0:
        lines.append(f"{unexplained} other operations are not exposed, without a recorded reason.")
    lines.append("Judge the quality and usefulness of the tools you can see and whether these exclusions are "
                 "justified; do not re-estimate the number of tools from the excerpt.")
    return " ".join(lines)


def _facts(code: str) -> dict:
    """Faits mécaniques sur le serveur évalué (voir mcp_forge/eval_checks.py)."""
    from mcp_forge.eval_checks import static_facts
    from mcp_forge.eval_dynamic import run_dynamic_tests
    facts = static_facts(code)
    if "_build_http_app" in code:
        facts["dynamic"] = run_dynamic_tests(code)
    # Analyseurs statiques (voir mcp_forge/eval_static.py) : actifs par
    # défaut ; MCP_FORGE_STATIC_ANALYZERS=0 les coupe.
    if os.getenv("MCP_FORGE_STATIC_ANALYZERS", "1") != "0":
        from mcp_forge.eval_static import run_static_analyzers
        facts["static_analyzers"] = run_static_analyzers(code)
    return facts


def evaluate_code(code: str, api_key: str | None = None, groq_key: str | None = None,
                  provider: str | None = None, model: str | None = None, context: str | None = None) -> dict:
    """Évalue un serveur MCP depuis son code source (string). Utilisé par l'API.

    Priorité : Anthropic (api_key) → Groq (groq_key) → détection auto depuis env.

    Contrairement à l'enrichissement/refine (où Groq est prioritaire pour le coût),
    l'éval essaie Anthropic en premier ici : le tool-use forcé (voir `_call_llm`)
    garantit une sortie déjà parsée et correctement échappée. Le mode
    `response_format=json_object` de Groq, lui, n'a pas éliminé en pratique les
    erreurs de JSON mal formé observées en production (guillemets non échappés
    dans une description générée en texte libre, ex: du contenu CLI/GraphQL/
    website) — voir tests/test_evaluate_structured_output.py.

    `provider` / `model` (ou MCP_FORGE_EVAL_PROVIDER / MCP_FORGE_EVAL_MODEL)
    imposent le fournisseur et le modèle d'évaluation, par exemple pour
    juger avec un autre modèle que celui qui a généré le serveur.
    """
    provider, model = _eval_overrides(provider, model)
    if provider:
        chosen, key = _select_provider(provider, model, {"Anthropic": api_key, "Groq": groq_key})
        return _call_llm(code, context, chosen, key, _facts(code))
    if model and (api_key or not groq_key):
        chosen, key = _detect_provider(api_key, None, model)
        return _call_llm(code, context, chosen, key, _facts(code))
    if api_key:
        try:
            return _call_llm(code, context, _PROVIDERS[0], api_key, _facts(code))
        except Exception:
            if groq_key:
                groq_provider = {**next(p for p in _PROVIDERS if p["name"] == "Groq"), "model": resolve_groq_model(groq_key)}
                return _call_llm(code, context, groq_provider, groq_key, _facts(code))
            raise
    if groq_key:
        groq_provider = {**next(p for p in _PROVIDERS if p["name"] == "Groq"), "model": resolve_groq_model(groq_key)}
        return _call_llm(code, context, groq_provider, groq_key, _facts(code))
    provider, key = _detect_provider(api_key)
    return _call_llm(code, context, provider, key, _facts(code))


def evaluate(
    server_path: str,
    context: str | None = None,
    output_json: bool = False,
    api_key: str | None = None,
    save: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    """
    Évalue un serveur MCP généré par mcp-forge.

    Le provider LLM est détecté automatiquement depuis les variables d'environnement
    (ANTHROPIC_API_KEY → GROQ_API_KEY → OPENAI_API_KEY → LLM_BASE_URL).

    Args:
        server_path: Chemin vers le server.py à évaluer.
        context:     Contexte additionnel transmis au LLM.
        output_json: Si True, affiche uniquement le JSON brut.
        api_key:     Clé API explicite (force Anthropic, bypass détection auto).
        save:        Chemin optionnel pour sauvegarder le rapport JSON.
        provider:    Fournisseur d'évaluation imposé (anthropic, groq, openai, mistral, local).
        model:       Modèle d'évaluation imposé.
    """
    try:
        provider, key = _detect_provider(api_key, provider, model)
    except RuntimeError as exc:
        _console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    path = Path(server_path)
    if not path.exists():
        _console.print(f"[bold red]Error:[/bold red] file not found — {server_path}")
        sys.exit(1)

    code = path.read_text(encoding="utf-8")

    try:
        if not output_json:
            with _console.status(
                f"[dim]Analysing with [bold]{provider['name']}[/bold] ({provider['model']})… {len(code)} chars[/dim]"
            ):
                result = _call_llm(code, context, provider, key, _facts(code))
        else:
            result = _call_llm(code, context, provider, key, _facts(code))
    except json.JSONDecodeError as exc:
        _console.print(f"[bold red]Error:[/bold red] LLM response is not valid JSON — {exc}")
        sys.exit(1)
    except RuntimeError as exc:
        _console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    render_report(result, server_path, output_json=output_json)

    if save:
        Path(save).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if not output_json:
            _console.print(f"[dim]  Report saved → {save}[/dim]")

    return result
