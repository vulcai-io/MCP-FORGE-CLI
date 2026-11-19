"""
Discovery à partir d'un site web ou d'une API REST non documentée.

Stratégie (par ordre de précision) :
  1. Chercher une spec OpenAPI/Swagger (chemins courants + liens dans le HTML)
  2. Détecter les appels API dans les scripts JavaScript inline
  3. Analyser les formulaires HTML >> tools POST
  4. Analyser la navigation et les liens >> tools GET
  5. Fallback Playwright pour les pages rendues côté client (SPA)
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
from rich.console import Console
from rich.markup import escape

from mcp_forge.discovery import download
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

# Chemins courants où une spec OpenAPI peut se trouver
_OPENAPI_PATHS = [
    "/openapi.json", "/openapi.yaml", "/openapi.yml",
    "/swagger.json", "/swagger.yaml",
    "/api/openapi.json", "/api/openapi.yaml",
    "/api-docs", "/api-docs/swagger.json",
    "/v1/openapi.json", "/v2/openapi.json", "/v3/openapi.json",
    "/docs/openapi.json",
    "/.well-known/openapi.json",
]

# Mots-clés dans les href qui pointent vers une doc API
_API_DOC_KEYWORDS = re.compile(
    r"(swagger|openapi|api[-_]?docs?|redoc|graphql)", re.IGNORECASE
)

# Patterns pour détecter des appels API dans le JS inline
_JS_FETCH_PATTERNS = [
    re.compile(r'fetch\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'axios\s*\.\s*(get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'(?:url|endpoint|path)\s*[:=]\s*["\']([/][^"\']+)["\']', re.IGNORECASE),
    re.compile(r'\$\.(?:get|post|ajax)\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE),
]

# Patterns JS indiquant une authentification
_JS_BEARER_RE = re.compile(r'["\']?[Aa]uthorization["\']?\s*:\s*["\']?Bearer', re.IGNORECASE)
_JS_APIKEY_RE = re.compile(r'["\']?[Xx]-[Aa][Pp][Ii]-[Kk]ey["\']?\s*:', re.IGNORECASE)
_JS_OAUTH_RE  = re.compile(r'oauth|client.?(?:id|secret)|token.?url', re.IGNORECASE)
_JS_BASIC_RE  = re.compile(r'["\']?[Aa]uthorization["\']?\s*:\s*["\']?Basic', re.IGNORECASE)

# Types HTML input >> ParameterType
_INPUT_TYPE_MAP: dict[str, ParameterType] = {
    "text": ParameterType.STRING,
    "email": ParameterType.STRING,
    "url": ParameterType.STRING,
    "search": ParameterType.STRING,
    "tel": ParameterType.STRING,
    "password": ParameterType.STRING,
    "number": ParameterType.NUMBER,
    "range": ParameterType.NUMBER,
    "checkbox": ParameterType.BOOLEAN,
    "date": ParameterType.STRING,
    "datetime-local": ParameterType.STRING,
    "file": ParameterType.STRING,
    "hidden": ParameterType.STRING,
}


# À partir de combien de tools (ou moins) la découverte d'un site dit ce qu'elle sait faire
# (demande du PO du 2026-11-18, avant Show HN : un visiteur essaiera un site)
FEW_TOOLS = 3

WEBSITE_SCOPE = (
    "Website discovery reads one page, the URL you give: its HTML forms, its links to other "
    "pages of the same site and the API calls spotted in its scripts. It also uses an OpenAPI "
    "spec if the site publishes one at a usual path (/openapi.json, /swagger.json...), links to "
    "one from that page, or if the page is a Swagger UI or Redoc page. It does not follow "
    "links to further pages and does not log in."
)
API_ADVICE = (
    "If the site has an API described by an OpenAPI spec or a GraphQL schema, generate the "
    "server from that instead: it gives one tool per operation (mcp-forge run <spec URL>, or "
    "mcp-forge run <GraphQL endpoint> --type graphql)."
)


def few_tools_hint(count: int, sep: str = " ") -> str | None:
    """Message en anglais quand un site donne peu de tools (FEW_TOOLS ou moins), sinon None.
    `sep` sépare le constat, la portée et le conseil (une ligne chacun dans le terminal)."""
    if count > FEW_TOOLS:
        return None
    found = "No tool found on this page." if count == 0 else f"Only {count} tool(s) found on this page."
    return sep.join((found, WEBSITE_SCOPE, API_ADVICE))


_KIND_LABELS = (("origin", "start page"), ("form", "form(s)"), ("nav", "link(s) to pages of the site"),
                ("js", "call(s) spotted in the scripts"))


def _found_summary(endpoints: list[_RawEndpoint]) -> str:
    """Ce que la page a donné, par sorte (« 2 form(s), 5 link(s) to pages of the site »)."""
    counts = {kind: sum(1 for e in endpoints if e.source == kind) for kind, _ in _KIND_LABELS}
    parts = [label if kind == "origin" else f"{counts[kind]} {label}"
             for kind, label in _KIND_LABELS if counts[kind]]
    return ", ".join(parts) or "no form and no link to another page of the site"


# Plafond de tools d'un site (correction D, PO, 2026-11-18) : une page aux centaines de liens
# ne doit pas donner des centaines de tools. Ordre gardé : page de départ, formulaires, appels
# des scripts, groupes de liens, puis liens dans l'ordre de la page (navigation d'abord).
WEBSITE_MAX_TOOLS = 30
_KEEP_ORDER = {"origin": 0, "form": 1, "js": 2}


def _cap(endpoints: list[_RawEndpoint]) -> list[_RawEndpoint]:
    def rank(item: tuple[int, _RawEndpoint]) -> tuple[int, int]:
        index, ep = item
        if ep.source in _KEEP_ORDER:
            return _KEEP_ORDER[ep.source], index
        return (3 if ep.params else 4), index
    kept = sorted(enumerate(endpoints), key=rank)[:WEBSITE_MAX_TOOLS]
    return [ep for _, ep in sorted(kept, key=lambda item: item[0])]


def _same_page(path: str, start_path: str) -> bool:
    """Lien vers la page de départ elle-même (`/` et `/index.html` sont la même page)."""
    def norm(p: str) -> str:
        p = re.sub(r"/index\.(html?|php)$", "/", p, flags=re.IGNORECASE)
        return p.rstrip("/") or "/"
    return bool(start_path) and norm(path) == norm(start_path)


def _slug_values(template: str, members: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """(valeur du segment {slug}, libellé) de chaque lien d'un groupe."""
    position = [s for s in template.split("/") if s].index("{slug}")
    return [([s for s in path.split("/") if s][position], label) for path, label in members]


# --- Pages de documentation d'API (Swagger UI, Redoc) : retrouver la spec affichée -------------
# Demande du PO du 2026-11-18 : une URL de page Swagger UI ou Redoc génère depuis la spec.
_DOC_PAGE_RE = re.compile(r"swagger-ui|SwaggerUIBundle|<redoc\b|Redoc\.init|redoc\.standalone", re.IGNORECASE)
# Scripts de configuration à lire (jamais le bundle de Swagger UI, lourd et sans URL de spec)
_DOC_CONFIG_SCRIPT_RE = re.compile(r"(swagger-initializer|swagger-config|swagger-ui-init|initializer)[^/]*\.js$",
                                   re.IGNORECASE)
# URL données explicitement : clé `url` (dont `urls[].url`), attribut spec-url, Redoc.init, fetch
_EXPLICIT_SPEC_RES = (
    re.compile(r"""(?<![A-Za-z_])["']?url["']?\s*:\s*["']([^"'\s]+)["']"""),
    re.compile(r"""spec-url\s*=\s*["']([^"'\s]+)["']""", re.IGNORECASE),
    re.compile(r"""Redoc\.init\(\s*["']([^"'\s]+)["']"""),
    re.compile(r"""fetch\(\s*["']([^"'\s]+)["']"""),
)
_CONFIG_URL_RE = re.compile(r"""(?<![A-Za-z_])["']?configUrl["']?\s*:\s*["']([^"'\s]+)["']""")
# Toute autre chaîne qui ressemble à l'URL d'une spec (absolue, ou chemin commençant par /)
_SPEC_LIKE_RE = re.compile(r"""(https?://[^\s"'`,;)<>]+|(?<=["'`])/[^\s"'`,;)<>]+)""")
_SPEC_HINT_RE = re.compile(r"openapi|swagger|api-docs|/schema/?$|\.(json|ya?ml)(\?|$)", re.IGNORECASE)
_NOT_SPEC_RE = re.compile(r"validator|oauth2-redirect|\.(js|css|png|svg|ico|html?|map)(\?|$)", re.IGNORECASE)
_MAX_SPEC_CANDIDATES = 3
_MAX_CONFIG_SCRIPTS = 2


def _spec_candidates(texts: list[str], page_url: str) -> tuple[list[str], list[str]]:
    """(URL de spec candidates, URL de configuration `configUrl`) trouvées dans les textes
    d'une page de doc (HTML, scripts). Les URL données explicitement passent d'abord, puis les
    chaînes qui ressemblent à une spec, celles du même hôte que la page d'abord."""
    explicit: list[str] = []
    configs: list[str] = []
    loose: list[str] = []
    query_url = parse_qs(urlparse(page_url).query).get("url")
    if query_url:
        explicit.append(query_url[0])  # petstore.swagger.io/?url=…
    for text in texts:
        for regex in _EXPLICIT_SPEC_RES:
            explicit += [m.group(1) for m in regex.finditer(text)]
        configs += [m.group(1) for m in _CONFIG_URL_RE.finditer(text)]
        loose += [m.group(1) for m in _SPEC_LIKE_RE.finditer(text)]
    host = urlparse(page_url).netloc

    def usable(u: str) -> bool:
        return bool(_SPEC_HINT_RE.search(u)) and not _NOT_SPEC_RE.search(u)

    absolute = [urljoin(page_url, u) for u in explicit if not _NOT_SPEC_RE.search(u) and not u.startswith("#")]
    others = sorted({urljoin(page_url, u) for u in loose if usable(u)} - set(absolute),
                    key=lambda u: (urlparse(u).netloc != host, u))
    seen: list[str] = []
    for u in [*absolute, *others]:
        if u.startswith(("http://", "https://")) and u not in seen:
            seen.append(u)
    return seen, [urljoin(page_url, u) for u in dict.fromkeys(configs)]


@dataclass
class _RawEndpoint:
    """Endpoint brut détecté avant conversion en DiscoveredTool."""
    method: str
    path: str
    description: str = ""
    params: list[ToolParameter] = field(default_factory=list)
    source: str = ""  # "form", "js", "nav"


class WebDiscovery:
    def __init__(self, config: ForgeConfig, url_guard: Callable[[str], None] | None = None):
        self.config = config
        self.base_url = self._extract_base(config.source)
        # Contrôle de chaque URL lue en plus de la page de départ (spec, script ou
        # configuration d'une page de doc) : l'API passe sa garde anti-SSRF
        # (api/services/ssrf_guard.py) ; la CLI, aucune (localhost est un usage légitime).
        self.url_guard = url_guard

    def _allowed(self, url: str) -> bool:
        if self.url_guard is None:
            return True
        try:
            self.url_guard(url)
        except Exception:
            console.print(f"[dim]  Skipped, not a public address: {escape(url)}[/dim]")
            return False
        return True

    def discover(self) -> DiscoveryResult:
        console.print("[bold]>> Analyzing the website...[/bold]")

        # --- Étape 1 : OpenAPI ---
        result = self._try_openapi_discovery()
        if result:
            return result

        # --- Étape 2-4 : Scraping HTML (httpx + BeautifulSoup) ---
        html, final_url, is_js_heavy = self._fetch_page(self.config.source)

        if is_js_heavy:
            console.print("[dim]  JS-heavy page detected, trying Playwright...[/dim]")
            html_js = self._fetch_with_playwright(self.config.source)
            if html_js:
                html = html_js

        if not html:
            console.print("[yellow]⚠ Could not load the page.[/yellow]")
            return DiscoveryResult(
                source_type=SourceType.WEBSITE,
                source_url=self.config.source,
                title="Website",
            )

        soup = BeautifulSoup(html, "html.parser")
        title, description = self._extract_meta(soup)

        # Re-tenter la détection OpenAPI via les liens dans le HTML
        openapi_link = self._find_openapi_link_in_html(soup)
        if openapi_link:
            result = self._try_openapi_from_url(openapi_link)
            if result:
                result.title = result.title or title
                return result

        # Page de documentation d'API (Swagger UI, Redoc) : la spec qu'elle affiche
        if _DOC_PAGE_RE.search(html):
            result = self._try_doc_page(soup, html, final_url or self.config.source)
            if result:
                result.title = result.title or title
                return result

        # Calculé avant l'extraction de nav : utilisé à la fois pour le tool
        # dédié à la page de départ (ci-dessous) ET pour détecter les liens
        # d'action-sur-page-arbitraire qui ne se répètent qu'une fois (voir
        # _generalize_templated_links).
        source_path = urlparse(final_url or self.config.source).path or "/"
        origin_last_segment = source_path.rsplit("/", 1)[-1] if source_path != "/" else ""

        # Collecte des endpoints bruts
        endpoints: list[_RawEndpoint] = []
        endpoints += self._extract_from_js(soup)
        endpoints += self._extract_from_forms(soup)
        endpoints += self._extract_from_navigation(soup, origin_last_segment, source_path)
        # La page de DÉPART elle-même (l'URL que l'utilisateur a donnée à
        # mcp-forge) n'a aucune raison de se trouver dans ses propres liens
        # de nav — sans ce tool dédié, un LLM qui veut "le contenu de cette
        # page précise" devait deviner le bon paramètre d'un tool générique
        # (`/wiki/{slug}`) plutôt que d'avoir un accès direct. Signalé par
        # l'évaluateur qualité comme un manque de pertinence fonctionnelle,
        # générique à tout site (pas seulement Wikipedia). Correction C
        # (2026-11-18) : aussi pour la racine du site (example.com donnait 0 tool).
        endpoints.append(_RawEndpoint(
            method="GET",
            path=source_path,
            description=f"Gets the content of the start page: {title or source_path}",
            source="origin",
        ))

        # Déduplique, plafonne et convertit
        endpoints = self._deduplicate(endpoints)
        if len(endpoints) > WEBSITE_MAX_TOOLS:
            console.print(f"[yellow]  ⚠ {len(endpoints)} tools found on the page: only {WEBSITE_MAX_TOOLS} are "
                          "kept (start page, forms, script calls and link groups first)[/yellow]")
            endpoints = _cap(endpoints)
        tools = [self._endpoint_to_tool(e) for e in endpoints]

        console.print(f"[green][OK] {len(tools)} MCP tool(s) extracted from the page: "
                      f"{_found_summary(endpoints)}[/green]")
        hint = few_tools_hint(len(tools), sep="\n  ")
        if hint:
            console.print(f"[yellow]⚠ {escape(hint)}[/yellow]")

        auth_schemes = self._detect_auth_from_html(html)

        return DiscoveryResult(
            source_type=SourceType.WEBSITE,
            source_url=final_url or self.config.source,
            title=title,
            description=description,
            base_url=self.base_url,
            tools=tools,
            auth_schemes=auth_schemes,
        )

    # ------------------------------------------------------------------
    # Détection de l'authentification
    # ------------------------------------------------------------------

    def _detect_auth_from_html(self, html: str) -> list[AuthScheme]:
        """Détecte le type d'auth depuis les scripts JS inline de la page."""
        soup = BeautifulSoup(html, "html.parser")
        js_text = " ".join(
            s.get_text() for s in soup.find_all("script", src=False) if s.get_text().strip()
        )
        if not js_text:
            return []

        if _JS_OAUTH_RE.search(js_text):
            return [AuthScheme(type=AuthType.OAUTH2, param_name="Authorization",
                               param_in="header", env_var="OAUTH2_TOKEN")]
        if _JS_BASIC_RE.search(js_text):
            return [AuthScheme(type=AuthType.BASIC, param_name="Authorization",
                               param_in="header", env_var="BASIC_AUTH")]
        if _JS_BEARER_RE.search(js_text):
            return [AuthScheme(type=AuthType.BEARER, param_name="Authorization",
                               param_in="header", env_var="BEARER_TOKEN")]
        if _JS_APIKEY_RE.search(js_text):
            return [AuthScheme(type=AuthType.APIKEY, param_name="X-Api-Key",
                               param_in="header", env_var="API_KEY")]
        return []

    # ------------------------------------------------------------------
    # Étape 1 : OpenAPI
    # ------------------------------------------------------------------

    def _try_openapi_discovery(self) -> DiscoveryResult | None:
        from .openapi import OpenAPIDiscovery
        console.print("[dim]  Looking for an OpenAPI spec published by the site...[/dim]")
        try:
            sub_config = self.config.model_copy(update={"source_type": SourceType.OPENAPI})
            result = OpenAPIDiscovery(sub_config, probe=True, url_guard=self.url_guard).discover()
        except Exception:
            console.print("[dim]  No OpenAPI spec at the usual paths: reading the page[/dim]")
            return None
        # Résultat OpenAPI tel quel (2026-11-19) : même serveur que depuis l'URL de la spec
        # (gabarit OpenAPI, spec.json et spec_index.json, métadonnées des tools gardées dans le
        # payload). Le type « website » donnait le gabarit des sites et retirait tout cela.
        console.print("[green][OK] The site publishes an OpenAPI spec: the tools come from it[/green]")
        return result

    def _find_openapi_link_in_html(self, soup: BeautifulSoup) -> str | None:
        """Cherche un lien vers une doc OpenAPI dans les balises <a> et <link>."""
        # Jamais un fichier statique : `swagger-ui.css`, `redoc.standalone.js`,
        # `swagger-ui-bundle.js` sont l'interface de la doc, pas la spec (ils étaient
        # téléchargés comme des specs, puis les chemins usuels réessayés ; 2026-11-18)
        static = re.compile(r"\.(js|mjs|css|png|svg|ico|woff2?|map)(\?|$)", re.IGNORECASE)
        for tag in soup.find_all(["a", "link"], href=True):
            href = tag["href"]
            if _API_DOC_KEYWORDS.search(href) and not static.search(href):
                return urljoin(self.base_url, href)
        return None

    def _try_openapi_from_url(self, url: str) -> DiscoveryResult | None:
        from .openapi import OpenAPIDiscovery
        if not self._allowed(url):  # lien vers un autre hôte : même garde que la page de départ
            return None
        try:
            sub_config = self.config.model_copy(
                update={"source": url, "source_type": SourceType.OPENAPI}
            )
            result = OpenAPIDiscovery(sub_config, probe=True, url_guard=self.url_guard).discover()
            # Résultat OpenAPI tel quel : voir _try_openapi_discovery
            console.print(f"[green][OK] The page links to an OpenAPI spec, the tools come from it: "
                          f"{escape(url)}[/green]")
            return result
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Étape 1 ter : page de documentation d'API (Swagger UI, Redoc)
    # ------------------------------------------------------------------

    def _try_doc_page(self, soup: BeautifulSoup, html: str, page_url: str) -> DiscoveryResult | None:
        """Spec affichée par une page Swagger UI ou Redoc : URL donnée dans la page, dans son
        script de configuration (`swagger-initializer.js`…) ou par `configUrl`. Chaque URL lue
        passe par `url_guard`, comme la page de départ ; au plus _MAX_SPEC_CANDIDATES specs
        essayées."""
        from .openapi import OpenAPIDiscovery, _looks_like_spec

        console.print("[dim]  API documentation page (Swagger UI or Redoc): looking for the spec it shows...[/dim]")
        texts = [html]
        scripts = [urljoin(page_url, tag["src"]) for tag in soup.find_all("script", src=True)
                   if _DOC_CONFIG_SCRIPT_RE.search(urlparse(tag["src"]).path)]
        for script_url in scripts[:_MAX_CONFIG_SCRIPTS]:
            text = self._fetch_text(script_url)
            if text:
                texts.append(text)
        candidates, config_urls = _spec_candidates(texts, page_url)
        for config_url in config_urls[:1]:  # springdoc : configUrl → {"url": …} ou {"urls": […]}
            text = self._fetch_text(config_url)
            try:
                config = json.loads(text) if text else {}
            except ValueError:
                config = {}
            if isinstance(config, dict):
                urls = [config.get("url")] + [u.get("url") for u in config.get("urls") or [] if isinstance(u, dict)]
                candidates = [urljoin(config_url, u) for u in urls if isinstance(u, str) and u] + candidates

        for spec_url in list(dict.fromkeys(candidates))[:_MAX_SPEC_CANDIDATES]:
            text = self._fetch_text(spec_url, spec=True)
            if not text:
                continue
            loader = OpenAPIDiscovery(self.config.model_copy(update={"source": spec_url,
                                                                   "source_type": SourceType.OPENAPI}),
                                      probe=True, url_guard=self.url_guard)
            try:
                spec = loader._parse_content(text, spec_url)
            except Exception:
                continue
            if not _looks_like_spec(spec):
                continue
            try:
                loader.preloaded_spec = spec
                result = loader.discover()
            except Exception as exc:
                console.print(f"[dim]  {escape(spec_url)}: unreadable spec ({escape(str(exc)[:120])})[/dim]")
                continue
            # Résultat OpenAPI tel quel : voir _try_openapi_discovery
            console.print(f"[green][OK] The page shows the OpenAPI spec {escape(spec_url)}: "
                          "the tools come from it[/green]")
            return result
        console.print("[dim]  No spec found for this documentation page: reading the page itself[/dim]")
        return None

    def _fetch_text(self, url: str, spec: bool = False) -> str | None:
        """Texte d'une URL annexe (script, configuration, spec), après `url_guard` ; None si
        refusée, en échec, trop grande ou trop longue. Limites communes (download.py) : spec
        comme une spec donnée par URL, script ou configuration CONFIG_MAX_BYTES."""
        if not url.startswith(("http://", "https://")) or not self._allowed(url):
            return None
        max_bytes, deadline = ((download.SPEC_MAX_BYTES, download.SPEC_DEADLINE_S) if spec
                               else (download.CONFIG_MAX_BYTES, download.PAGE_DEADLINE_S))
        try:
            response = download.fetch(url, max_bytes=max_bytes, deadline_s=deadline,
                                      headers={"Accept": "application/json, application/yaml, text/plain, */*"})
        except (download.DownloadTooLarge, download.DownloadTooSlow) as exc:
            console.print(f"[yellow]  ⚠ Skipped: {escape(str(exc))}[/yellow]")
            return None
        except Exception:
            return None
        return response.text if response.status_code == 200 else None

    # ------------------------------------------------------------------
    # Étape 2 : Détection d'appels API dans le JS inline
    # ------------------------------------------------------------------

    def _extract_from_js(self, soup: BeautifulSoup) -> list[_RawEndpoint]:
        endpoints: list[_RawEndpoint] = []
        seen: set[str] = set()

        for script in soup.find_all("script", src=False):
            js_text = script.get_text()
            if not js_text.strip():
                continue

            # Pattern axios.get/post/...
            for m in re.finditer(
                r'axios\s*\.\s*(get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)["\']',
                js_text, re.IGNORECASE
            ):
                method, path = m.group(1).upper(), m.group(2)
                key = f"{method}:{path}"
                if key not in seen and self._looks_like_api_path(path):
                    seen.add(key)
                    endpoints.append(_RawEndpoint(method=method, path=path, source="js"))

            # Pattern fetch(url)
            for m in re.finditer(
                r'fetch\s*\(\s*["\']([^"\']+)["\'](?:\s*,\s*\{[^}]*method\s*:\s*["\'](\w+)["\'])?',
                js_text, re.IGNORECASE
            ):
                path = m.group(1)
                method = (m.group(2) or "GET").upper()
                key = f"{method}:{path}"
                if key not in seen and self._looks_like_api_path(path):
                    seen.add(key)
                    endpoints.append(_RawEndpoint(method=method, path=path, source="js"))

            # Pattern url/endpoint = "/api/..."
            for m in re.finditer(
                r'(?:url|endpoint|path|apiUrl)\s*[:=]\s*["\']([/][^"\']+)["\']',
                js_text, re.IGNORECASE
            ):
                path = m.group(1)
                key = f"GET:{path}"
                if key not in seen and self._looks_like_api_path(path):
                    seen.add(key)
                    endpoints.append(_RawEndpoint(method="GET", path=path, source="js"))

        if endpoints:
            console.print(f"[dim]  {len(endpoints)} endpoint(s) detected in the JS[/dim]")
        return endpoints

    # ------------------------------------------------------------------
    # Étape 3 : Formulaires HTML >> tools POST
    # ------------------------------------------------------------------

    def _extract_from_forms(self, soup: BeautifulSoup) -> list[_RawEndpoint]:
        endpoints: list[_RawEndpoint] = []

        for form in soup.find_all("form"):
            action = form.get("action", "")
            method = (form.get("method", "GET")).upper()
            if not action or action.startswith(("javascript:", "mailto:", "#")):
                continue

            path = urljoin(self.base_url, action)
            if not path.startswith(self.base_url):
                continue  # formulaire externe

            path = urlparse(path).path  # on garde seulement le path

            # Description depuis le contexte du formulaire
            legend = form.find("legend")
            label_h = form.find(["h1", "h2", "h3", "h4", "label"])
            aria_label = form.get("aria-label", "")
            description = (
                (legend.get_text(strip=True) if legend else "")
                or (label_h.get_text(strip=True) if label_h else "")
                or aria_label
                or f"Formulaire {method} {path}"
            )

            params = self._extract_form_params(form)
            endpoints.append(_RawEndpoint(
                method=method,
                path=path,
                description=description,
                params=params,
                source="form",
            ))

        if endpoints:
            console.print(f"[dim]  {len(endpoints)} form(s) found[/dim]")
        return endpoints

    def _extract_form_params(self, form: BeautifulSoup) -> list[ToolParameter]:
        params: list[ToolParameter] = []
        seen: set[str] = set()

        for form_field in form.find_all(["input", "select", "textarea"]):
            name = form_field.get("name") or form_field.get("id", "")
            if not name or name in seen:
                continue
            if form_field.get("type") in ("submit", "reset", "button", "image"):
                continue
            seen.add(name)

            input_type = form_field.get("type", "text") if form_field.name == "input" else "string"
            ptype = _INPUT_TYPE_MAP.get(input_type, ParameterType.STRING)

            # Description depuis un <label> associé
            label_tag = form.find("label", attrs={"for": form_field.get("id", "")})
            desc = (
                (label_tag.get_text(strip=True) if label_tag else "")
                or form_field.get("placeholder", "")
                or form_field.get("aria-label", "")
                or name
            )

            required = form_field.has_attr("required") or form_field.get("aria-required") == "true"
            default = form_field.get("value") if input_type != "password" else None

            # Options de <select>
            enum_values = []
            if form_field.name == "select":
                enum_values = [
                    opt.get("value", opt.get_text(strip=True))
                    for opt in form_field.find_all("option")
                    if opt.get("value") not in ("", None)
                ]

            params.append(ToolParameter(
                name=name,
                type=ptype,
                description=desc,
                required=required,
                default=default,
                enum_values=enum_values,
            ))

        return params

    # ------------------------------------------------------------------
    # Étape 4 : Navigation >> tools GET de contenu
    # ------------------------------------------------------------------

    # Nombre minimum de liens partageant le même "préfixe" (tous les segments
    # sauf le dernier) pour les généraliser en UN seul outil paramétré
    # (`/wiki/{slug}`) plutôt que de créer un outil en dur par lien trouvé.
    # En dessous de ce seuil, 2-3 liens qui se ressemblent par coïncidence
    # (ex: /about et /contact n'ont pas de préfixe commun donc ne comptent
    # pas) ne justifient pas la généralisation — ça reste des pages uniques.
    _NAV_TEMPLATE_MIN_COUNT = 3

    def _extract_from_navigation(self, soup: BeautifulSoup, origin_last_segment: str = "",
                                 start_path: str = "") -> list[_RawEndpoint]:
        # Toute la page, <nav> et <header> d'abord (correction A, 2026-11-18) : avant, seuls
        # <nav> et <header> étaient lus quand la page en avait ; sur books.toscrape.com, le
        # <header> n'a que le lien d'accueil et les 73 autres liens étaient ignorés. L'ordre
        # garde la navigation en tête quand le plafond de tools s'applique (correction D).
        containers = [*soup.find_all(["nav", "header"]), soup]

        raw_links: list[tuple[str, str]] = []  # (path, label)
        seen_paths: set[str] = set()
        for container in containers:
            for link in container.find_all("a", href=True):
                href = link["href"]
                if href.startswith(("javascript:", "mailto:", "tel:", "#")):
                    continue
                full_url = urljoin(self.base_url, href)
                if not full_url.startswith(self.base_url):
                    continue  # lien externe

                path = urlparse(full_url).path
                if path in seen_paths or path in ("/", "") or _same_page(path, start_path):
                    continue
                # Ignore les fichiers statiques
                if re.search(r"\.(css|js|png|jpg|gif|svg|ico|woff|ttf)$", path, re.IGNORECASE):
                    continue

                seen_paths.add(path)
                label = link.get_text(strip=True) or link.get("title", "") or path
                raw_links.append((path, label))

        endpoints = self._generalize_templated_links(raw_links, origin_last_segment)

        if endpoints:
            console.print(f"[dim]  {len(endpoints)} link(s) or link group(s) to pages of the site[/dim]")
        return endpoints

    def _generalize_templated_links(
        self, raw_links: list[tuple[str, str]], origin_last_segment: str = "",
    ) -> list[_RawEndpoint]:
        """Regroupe les liens qui partagent le même préfixe de chemin
        (ex: /wiki/Python, /wiki/Java, /wiki/Rust...) en UN seul outil
        paramétré (`/wiki/{slug}`) au lieu d'un outil en dur par lien.

        Sans ça, un site avec une navigation riche (wiki, blog, doc) génère
        des dizaines de tools quasi-identiques ne couvrant chacun qu'UNE
        page en dur, et aucun moyen pour le LLM de récupérer une page dont
        le lien n'était pas présent sur la page de départ — signalé par
        l'évaluateur qualité comme un vrai manque de couverture, pas
        spécifique à un site en particulier (n'importe quel site avec une
        structure d'URL répétée a ce même problème).

        Correction B (2026-11-18) : ensuite, pour les liens restants, un seul
        segment du milieu peut varier (`/catalogue/category/books/travel_2/
        index.html` → `/catalogue/category/books/{slug}/index.html`). Le
        dernier segment passe d'abord : les regroupements d'avant ne changent
        pas."""
        groups: dict[tuple[str, ...], list[tuple[str, str]]] = {}
        for path, label in raw_links:
            segments = [s for s in path.split("/") if s]
            if len(segments) < 2:
                continue  # pas de préfixe significatif (ex: "/about")
            prefix = tuple(segments[:-1])
            groups.setdefault(prefix, []).append((segments[-1], label))

        # Liste (ordre stable) et non ensemble : l'ordre des tools ne dépend plus du hachage
        templated_prefixes = [
            prefix for prefix, items in groups.items()
            if (
                # Insensible à la casse : /wiki/Foo et /wiki/FOO comptent comme
                # la même "famille" de page, pas deux pages distinctes — c'est
                # justement ce qui créait des outils quasi-dupliqués avant.
                len({last.lower() for last, _ in items}) >= self._NAV_TEMPLATE_MIN_COUNT
                # OU : un seul lien de ce groupe suffit s'il se termine
                # exactement par le même segment que la page de départ
                # elle-même (ex: /wiki/Special:WhatLinksHere/Python_(...)
                # et /wiki/Special:RecentChangesLinked/Python_(...) sur la
                # page Python) — signal fort qu'il s'agit d'une action
                # applicable à N'IMPORTE QUELLE page, pas d'un lien figé,
                # même si cette page précise n'apparaît qu'une seule fois
                # dans chacune de ces deux familles. Signalé par
                # l'évaluateur qualité : laissés en dur, ces outils à usage
                # unique étaient parfois jugés "majeur" (inutilisables pour
                # toute autre page) — d'où la variance de score observée
                # sur plusieurs exécutions du même site.
                or (origin_last_segment and any(last == origin_last_segment for last, _ in items))
            )
        ]
        templated = set(templated_prefixes)

        remaining = [(path, label) for path, label in raw_links
                     if tuple(s for s in path.split("/") if s)[:-1] not in templated]
        middle = self._middle_segment_groups(remaining)
        in_middle = {path for _, members in middle for path, _ in members}

        endpoints: list[_RawEndpoint] = []
        for path, label in remaining:
            if path in in_middle:
                continue  # remplacé plus bas par un seul outil générique
            endpoints.append(_RawEndpoint(
                method="GET",
                path=path,
                description=f"Gets the content of the page: {label}",
                source="nav",
            ))

        for prefix in templated_prefixes:
            examples = [last for last, _ in groups[prefix][:3]]
            template_path = "/" + "/".join(prefix) + "/{slug}"
            endpoints.append(_RawEndpoint(
                method="GET",
                path=template_path,
                description=(
                    f"Gets the content of any page under /{'/'.join(prefix)}/ "
                    f"from its identifier (e.g. {', '.join(examples)})."
                ),
                params=[ToolParameter(
                    name="slug",
                    type=ParameterType.STRING,
                    description=f"Identifier of the page under /{'/'.join(prefix)}/ (e.g. {examples[0]}).",
                    required=True,
                )],
                source="nav",
            ))

        for template_path, members in middle:
            examples = [value for value, _ in _slug_values(template_path, members)[:3]]
            endpoints.append(_RawEndpoint(
                method="GET",
                path=template_path,
                description=(f"Gets the content of any page {template_path} from its identifier "
                             f"(e.g. {', '.join(examples)})."),
                params=[ToolParameter(
                    name="slug",
                    type=ParameterType.STRING,
                    description=f"Identifier in {template_path} (e.g. {examples[0]}).",
                    required=True,
                )],
                source="nav",
            ))

        return endpoints

    def _middle_segment_groups(
        self, links: list[tuple[str, str]],
    ) -> list[tuple[str, list[tuple[str, str]]]]:
        """Groupes de liens qui ne diffèrent que par UN segment du milieu (au moins
        _NAV_TEMPLATE_MIN_COUNT valeurs distinctes) : (chemin avec {slug}, liens du groupe).
        Le plus grand groupe d'abord ; un lien n'entre que dans un groupe."""
        candidates: dict[str, list[tuple[str, str]]] = {}
        for path, label in links:
            segments = [s for s in path.split("/") if s]
            trailing = "/" if path.endswith("/") else ""
            for i in range(1, len(segments) - 1):
                template = "/" + "/".join([*segments[:i], "{slug}", *segments[i + 1:]]) + trailing
                candidates.setdefault(template, []).append((path, label))

        def distinct(template: str, members: list[tuple[str, str]]) -> int:
            return len({value.lower() for value, _ in _slug_values(template, members)})

        groups: list[tuple[str, list[tuple[str, str]]]] = []
        taken: set[str] = set()
        for template in sorted(candidates, key=lambda t: -distinct(t, candidates[t])):
            members = [(p, lab) for p, lab in candidates[template] if p not in taken]
            if distinct(template, members) >= self._NAV_TEMPLATE_MIN_COUNT:
                groups.append((template, members))
                taken.update(p for p, _ in members)
        return groups

    # ------------------------------------------------------------------
    # Étape 5 : Fallback Playwright
    # ------------------------------------------------------------------

    def _fetch_with_playwright(self, url: str) -> str | None:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=20000)
                html = page.content()
                browser.close()
                return html
        except ImportError:
            console.print(
                "[yellow]⚠ This site needs Playwright for its JS pages.\n"
                "  Install it with:[/yellow] "
                "[bold]pip install \"vulcai-mcp-forge-cli\\[web]\" && playwright install chromium[/bold]"
            )
            return None
        except Exception as e:
            console.print(f"[dim]  Playwright failed: {e}[/dim]")
            return None

    # ------------------------------------------------------------------
    # Fetch HTTP
    # ------------------------------------------------------------------

    def _fetch_page(self, url: str) -> tuple[str | None, str | None, bool]:
        """Retourne (html, final_url, is_js_heavy)."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; mcp-forge/0.1; +https://github.com/mcp-forge)",
                "Accept": "text/html,application/xhtml+xml,*/*",
            }
            # Limites communes de taille et de temps (mcp_forge/discovery/download.py)
            response = download.fetch(url, max_bytes=download.PAGE_MAX_BYTES,
                                      deadline_s=download.PAGE_DEADLINE_S, headers=headers)
            if response.status_code >= 400:
                raise ValueError(f"HTTP {response.status_code} for {url}")
            html = response.text
            is_js_heavy = self._detect_js_heavy(html)
            return html, str(response.url), is_js_heavy
        except Exception as e:
            console.print(f"[red]  [FAIL] Loading error: {e}[/red]")
            return None, None, False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_meta(self, soup: BeautifulSoup) -> tuple[str, str]:
        title = ""
        description = ""

        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", title)

        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            description = meta_desc.get("content", "")

        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            description = og_desc.get("content", description)

        return title, description

    def _deduplicate(self, endpoints: list[_RawEndpoint]) -> list[_RawEndpoint]:
        """Supprime les doublons méthode+path en priorisant : js > form > nav."""
        priority = {"js": 0, "form": 1, "nav": 2}
        best: dict[str, _RawEndpoint] = {}
        for ep in endpoints:
            key = f"{ep.method}:{ep.path}"
            if key not in best or priority.get(ep.source, 9) < priority.get(best[key].source, 9):
                best[key] = ep
        return list(best.values())

    def _endpoint_to_tool(self, ep: _RawEndpoint) -> DiscoveredTool:
        name = self._path_to_tool_name(ep.method, ep.path)
        return DiscoveredTool(
            name=name,
            description=ep.description or f"{ep.method} {ep.path}",
            parameters=ep.params,
            http_method=ep.method,
            endpoint=ep.path,
            base_url=self.base_url,
            tags=[ep.source],
        )

    @staticmethod
    def _extract_base(url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @staticmethod
    def _looks_like_api_path(path: str) -> bool:
        """Filtre les chemins qui ressemblent à des endpoints API."""
        if not path.startswith("/"):
            return False
        # Ignore les assets statiques
        if re.search(r"\.(js|css|png|jpg|gif|svg|ico|woff|ttf|map)$", path, re.IGNORECASE):
            return False
        return True

    @staticmethod
    def _detect_js_heavy(html: str) -> bool:
        """Détecte si la page est un SPA/JS-heavy (peu de contenu HTML statique)."""
        soup = BeautifulSoup(html, "html.parser")
        text_content = soup.get_text(strip=True)
        script_tags = len(soup.find_all("script"))
        # SPA typique : beaucoup de scripts, peu de texte visible
        return script_tags >= 5 and len(text_content) < 500

    @staticmethod
    def _path_to_tool_name(method: str, path: str) -> str:
        """Transforme GET /api/users/{id} >> get_api_users_by_id."""
        path = re.sub(r"\{(\w+)\}", r"by_\1", path)
        path = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_").lower()
        # Racine du site (page de départ `/`, correction C) : get_home_page
        return f"{method.lower()}_{path}" if path else f"{method.lower()}_home_page"
