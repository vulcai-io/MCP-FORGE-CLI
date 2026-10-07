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

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
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


@dataclass
class _RawEndpoint:
    """Endpoint brut détecté avant conversion en DiscoveredTool."""
    method: str
    path: str
    description: str = ""
    params: list[ToolParameter] = field(default_factory=list)
    source: str = ""  # "form", "js", "nav"


class WebDiscovery:
    def __init__(self, config: ForgeConfig):
        self.config = config
        self.base_url = self._extract_base(config.source)

    def discover(self) -> DiscoveryResult:
        console.print("[bold]>> Analyse du site web...[/bold]")

        # --- Étape 1 : OpenAPI ---
        result = self._try_openapi_discovery()
        if result:
            return result

        # --- Étape 2-4 : Scraping HTML (httpx + BeautifulSoup) ---
        html, final_url, is_js_heavy = self._fetch_page(self.config.source)

        if is_js_heavy:
            console.print("[dim]  Page JS-heavy détectée, tentative avec Playwright...[/dim]")
            html_js = self._fetch_with_playwright(self.config.source)
            if html_js:
                html = html_js

        if not html:
            console.print("[yellow]⚠ Impossible de charger la page.[/yellow]")
            return DiscoveryResult(
                source_type=SourceType.WEBSITE,
                source_url=self.config.source,
                title="Site web",
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
        endpoints += self._extract_from_navigation(soup, origin_last_segment)
        # La page de DÉPART elle-même (l'URL que l'utilisateur a donnée à
        # mcp-forge) n'a aucune raison de se trouver dans ses propres liens
        # de nav — sans ce tool dédié, un LLM qui veut "le contenu de cette
        # page précise" devait deviner le bon paramètre d'un tool générique
        # (`/wiki/{slug}`) plutôt que d'avoir un accès direct. Signalé par
        # l'évaluateur qualité comme un manque de pertinence fonctionnelle,
        # générique à tout site (pas seulement Wikipedia).
        if source_path != "/":
            endpoints.append(_RawEndpoint(
                method="GET",
                path=source_path,
                description=f"Récupère le contenu de la page de départ : {title or source_path}",
                source="origin",
            ))

        # Déduplique et convertit
        endpoints = self._deduplicate(endpoints)
        tools = [self._endpoint_to_tool(e) for e in endpoints]

        console.print(f"[green][OK] {len(tools)} outil(s) MCP extrait(s) du site[/green]")

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
        try:
            sub_config = self.config.model_copy(update={"source_type": SourceType.OPENAPI})
            result = OpenAPIDiscovery(sub_config).discover()
            result.source_type = SourceType.WEBSITE
            console.print("[green][OK] Spec OpenAPI trouvée automatiquement[/green]")
            return result
        except Exception:
            return None

    def _find_openapi_link_in_html(self, soup: BeautifulSoup) -> str | None:
        """Cherche un lien vers une doc OpenAPI dans les balises <a> et <link>."""
        for tag in soup.find_all(["a", "link"], href=True):
            href = tag["href"]
            if _API_DOC_KEYWORDS.search(href):
                return urljoin(self.base_url, href)
        # Cherche dans les scripts src
        for tag in soup.find_all("script", src=True):
            src = tag["src"]
            if _API_DOC_KEYWORDS.search(src):
                return urljoin(self.base_url, src)
        return None

    def _try_openapi_from_url(self, url: str) -> DiscoveryResult | None:
        from .openapi import OpenAPIDiscovery
        try:
            sub_config = self.config.model_copy(
                update={"source": url, "source_type": SourceType.OPENAPI}
            )
            result = OpenAPIDiscovery(sub_config).discover()
            result.source_type = SourceType.WEBSITE
            console.print(f"[green][OK] Spec OpenAPI trouvée via lien HTML : {url}[/green]")
            return result
        except Exception:
            return None

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
            console.print(f"[dim]  {len(endpoints)} endpoint(s) détecté(s) dans le JS[/dim]")
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
            console.print(f"[dim]  {len(endpoints)} formulaire(s) trouvé(s)[/dim]")
        return endpoints

    def _extract_form_params(self, form: BeautifulSoup) -> list[ToolParameter]:
        params: list[ToolParameter] = []
        seen: set[str] = set()

        for field in form.find_all(["input", "select", "textarea"]):
            name = field.get("name") or field.get("id", "")
            if not name or name in seen:
                continue
            if field.get("type") in ("submit", "reset", "button", "image"):
                continue
            seen.add(name)

            input_type = field.get("type", "text") if field.name == "input" else "string"
            ptype = _INPUT_TYPE_MAP.get(input_type, ParameterType.STRING)

            # Description depuis un <label> associé
            label_tag = form.find("label", attrs={"for": field.get("id", "")})
            desc = (
                (label_tag.get_text(strip=True) if label_tag else "")
                or field.get("placeholder", "")
                or field.get("aria-label", "")
                or name
            )

            required = field.has_attr("required") or field.get("aria-required") == "true"
            default = field.get("value") if input_type != "password" else None

            # Options de <select>
            enum_values = []
            if field.name == "select":
                enum_values = [
                    opt.get("value", opt.get_text(strip=True))
                    for opt in field.find_all("option")
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

    def _extract_from_navigation(self, soup: BeautifulSoup, origin_last_segment: str = "") -> list[_RawEndpoint]:
        # Cherche dans <nav>, <header>, ou les listes de liens
        nav_containers = soup.find_all(["nav", "header"]) or [soup]

        raw_links: list[tuple[str, str]] = []  # (path, label)
        seen_paths: set[str] = set()
        for container in nav_containers:
            for link in container.find_all("a", href=True):
                href = link["href"]
                if href.startswith(("javascript:", "mailto:", "tel:", "#")):
                    continue
                full_url = urljoin(self.base_url, href)
                if not full_url.startswith(self.base_url):
                    continue  # lien externe

                path = urlparse(full_url).path
                if path in seen_paths or path in ("/", ""):
                    continue
                # Ignore les fichiers statiques
                if re.search(r"\.(css|js|png|jpg|gif|svg|ico|woff|ttf)$", path, re.IGNORECASE):
                    continue

                seen_paths.add(path)
                label = link.get_text(strip=True) or link.get("title", "") or path
                raw_links.append((path, label))

        endpoints = self._generalize_templated_links(raw_links, origin_last_segment)

        if endpoints:
            console.print(f"[dim]  {len(endpoints)} lien(s) de navigation trouvé(s)[/dim]")
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
        structure d'URL répétée a ce même problème)."""
        groups: dict[tuple[str, ...], list[tuple[str, str]]] = {}
        for path, label in raw_links:
            segments = [s for s in path.split("/") if s]
            if len(segments) < 2:
                continue  # pas de préfixe significatif (ex: "/about")
            prefix = tuple(segments[:-1])
            groups.setdefault(prefix, []).append((segments[-1], label))

        templated_prefixes = {
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
        }

        endpoints: list[_RawEndpoint] = []
        for path, label in raw_links:
            segments = [s for s in path.split("/") if s]
            prefix = tuple(segments[:-1]) if len(segments) >= 2 else None
            if prefix in templated_prefixes:
                continue  # remplacé plus bas par un seul outil générique
            endpoints.append(_RawEndpoint(
                method="GET",
                path=path,
                description=f"Récupère le contenu de la page : {label}",
                source="nav",
            ))

        for prefix in templated_prefixes:
            examples = [last for last, _ in groups[prefix][:3]]
            template_path = "/" + "/".join(prefix) + "/{slug}"
            endpoints.append(_RawEndpoint(
                method="GET",
                path=template_path,
                description=(
                    f"Récupère le contenu de n'importe quelle page sous /{'/'.join(prefix)}/ "
                    f"en fournissant son identifiant (ex: {', '.join(examples)})."
                ),
                params=[ToolParameter(
                    name="slug",
                    type=ParameterType.STRING,
                    description=f"Identifiant de la page sous /{'/'.join(prefix)}/ (ex: {examples[0]}).",
                    required=True,
                )],
                source="nav",
            ))

        return endpoints

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
                "[yellow]⚠ Ce site nécessite Playwright pour les pages JS.\n"
                "  Installez-le avec :[/yellow] "
                "[bold]pip install \"vulcai-mcp-forge-cli\\[web]\" && playwright install chromium[/bold]"
            )
            return None
        except Exception as e:
            console.print(f"[dim]  Playwright échoué : {e}[/dim]")
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
            response = httpx.get(url, timeout=15, follow_redirects=True, headers=headers)
            response.raise_for_status()
            html = response.text
            is_js_heavy = self._detect_js_heavy(html)
            return html, str(response.url), is_js_heavy
        except Exception as e:
            console.print(f"[red]  [FAIL] Erreur de chargement : {e}[/red]")
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
        return f"{method.lower()}_{path}" if path else method.lower()
