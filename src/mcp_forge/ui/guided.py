"""
Mode GUIDED : étape par étape, entièrement interactif.

Étapes :
  1. Confirmation de la source et du type détecté
  2. Discovery avec résumé adapté à la source
  3. Sélection individuelle des tools (contexte selon source)
  4. Édition nom/description + métadonnées spécifiques (flags CLI, etc.)
  5. Enrichissement LLM optionnel
  6. Paramètres du serveur (nom, description, dossier)
  7. Génération
  8. Review des fichiers générés
  9. Validation
"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from mcp_forge.models import DiscoveredTool, DiscoveryResult, ForgeConfig, GeneratedServer, SourceType

console = Console()


def run_guided(config: ForgeConfig) -> GeneratedServer | None:
    from mcp_forge.discovery import discover
    from mcp_forge.enrichment.llm import LLMEnricher
    from mcp_forge.pipeline.selector import run_pipeline
    from mcp_forge.validation import MCPValidator

    console.print(Panel.fit(
        "[bold]Mode guidé[/bold] — Chaque étape est validée avec vous.",
        border_style="blue",
    ))

    # --- Étape 1 : Confirmation source ---
    console.print(f"\n[bold]Étape 1/9[/bold] — Source : [cyan]{config.source}[/cyan]")
    console.print(f"  Type détecté : [cyan]{config.source_type.value}[/cyan]")
    _print_source_hint(config.source_type)
    typer.confirm("Continuer avec cette source ?", default=True, abort=True)

    # --- Étape 2 : Discovery ---
    console.print("\n[bold]Étape 2/9[/bold] — Découverte des capacités")
    result = discover(config)
    _print_discovery_summary(result)

    if not result.tools:
        console.print("[yellow]⚠ Aucun tool découvert.[/yellow]")
        return None

    # --- Étape 3 : Sélection des tools ---
    console.print(f"\n[bold]Étape 3/9[/bold] — Sélection des tools ({len(result.tools)} trouvé(s))")
    result = _select_tools_guided(result)
    enabled = [t for t in result.tools if t.enabled]
    if not enabled:
        console.print("[yellow]⚠ Aucun tool sélectionné.[/yellow]")
        return None

    # --- Étape 4 : Édition ---
    console.print(f"\n[bold]Étape 4/9[/bold] — Édition des tools ({len(enabled)} retenu(s))")
    enabled = _edit_tools_guided(enabled, result.source_type)

    # --- Étape 5 : Enrichissement LLM ---
    console.print("\n[bold]Étape 5/9[/bold] — Enrichissement LLM")
    if config.use_llm_enrichment:
        do_enrich = typer.confirm("Lancer l'enrichissement automatique via Claude ?", default=True)
        if do_enrich:
            try:
                enricher = LLMEnricher(config)
                result = enricher.enrich(result, config)
            except Exception as e:
                console.print(f"[yellow]⚠ Enrichissement ignoré : {e}[/yellow]")
    else:
        console.print("[dim]  (désactivé — pas de clé API)[/dim]")

    # --- Étape 6 : Paramètres du serveur ---
    console.print("\n[bold]Étape 6/9[/bold] — Paramètres du serveur")
    _prompt_server_params(config, result)

    # --- Étape 7 : Génération (local ou Azure selon l'environnement) ---
    console.print("\n[bold]Étape 7/9[/bold] — Génération du serveur")
    typer.confirm("Lancer la génération ?", default=True, abort=True)
    generated = run_pipeline(result, config)

    # --- Étape 8 : Review du code ---
    console.print("\n[bold]Étape 8/9[/bold] — Review du code généré")
    _review_code_guided(generated, result.source_type)

    # --- Étape 9 : Validation ---
    console.print("\n[bold]Étape 9/9[/bold] — Validation")
    typer.confirm("Lancer la validation ?", default=True, abort=True)
    ok = MCPValidator().validate(generated)

    if ok:
        out = str(generated.output_dir).replace("\\", "/")
        console.print(Panel.fit(
            f"[bold green][OK] Serveur prêt ![/bold green]\n\n"
            f"  cd {out}\n"
            f"  python server.py\n\n"
            f"  mcp-forge test {out}/server.py",
            border_style="green",
        ))

    if generated.eval_report:
        _write_eval_report(generated)
        from mcp_forge.evaluate import render_report
        render_report(generated.eval_report, str(generated.output_dir) + "/server.py")

    return generated


def _write_eval_report(generated) -> None:
    import json
    from pathlib import Path
    report_path = Path(generated.output_dir) / "eval_report.json"
    report_path.write_text(
        json.dumps(generated.eval_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ------------------------------------------------------------------
# Étape 1 : hints par source
# ------------------------------------------------------------------

def _print_source_hint(source_type: SourceType) -> None:
    hints = {
        SourceType.OPENAPI:  "  Spec OpenAPI/Swagger — extraction précise des endpoints et types.",
        SourceType.WEBSITE:  "  Site web — scraping HTML + détection OpenAPI + appels JS.",
        SourceType.GRAPHQL:  "  API GraphQL — introspection des queries et mutations.",
        SourceType.CLI_APP:  "  Application CLI — parsing des sous-commandes via --help.",
        SourceType.CODEBASE: "  Code source Python — extraction des fonctions/méthodes publiques.",
    }
    hint = hints.get(source_type, "")
    if hint:
        console.print(f"[dim]{hint}[/dim]")


# ------------------------------------------------------------------
# Étape 2 : résumé discovery
# ------------------------------------------------------------------

def _print_discovery_summary(result: DiscoveryResult) -> None:
    console.print(f"  [green]{len(result.tools)} tool(s) trouvé(s)[/green]")
    if result.title:
        console.print(f"  Titre      : {result.title}")
    if result.description:
        console.print(f"  Description: {result.description[:100]}")

    if result.source_type in (SourceType.OPENAPI, SourceType.WEBSITE, SourceType.GRAPHQL):
        if result.base_url:
            console.print(f"  Base URL   : {result.base_url}")
    elif result.source_type == SourceType.CLI_APP:
        if result.source_path:
            console.print(f"  Commande   : {result.source_path}")
    elif result.source_type == SourceType.CODEBASE and result.source_path:
        console.print(f"  Dossier    : {result.source_path}")

    # Répartition par tag
    tags: dict[str, int] = {}
    for t in result.tools:
        tag = t.tags[0] if t.tags else "autre"
        tags[tag] = tags.get(tag, 0) + 1
    if tags:
        detail = " · ".join(f"{v} {k}" for k, v in tags.items())
        console.print(f"  [dim]{detail}[/dim]")


# ------------------------------------------------------------------
# Étape 3 : sélection des tools
# ------------------------------------------------------------------

def _select_tools_guided(result: DiscoveryResult) -> DiscoveryResult:
    console.print("[dim]  Entrée = garder, n = exclure.[/dim]")
    for tool in result.tools:
        _print_tool_preview(tool, result.source_type)
        keep = typer.confirm("  Inclure ce tool ?", default=True)
        tool.enabled = keep

    return result


def _print_tool_preview(tool: DiscoveredTool, source_type: SourceType) -> None:
    """Affiche un aperçu d'un tool adapté à la source."""
    console.print(f"\n  [cyan]{tool.name}[/cyan]")
    console.print(f"  [dim]{tool.description[:100]}[/dim]")

    _PREVIEW_PRINTERS = {
        SourceType.OPENAPI:   _preview_api,
        SourceType.WEBSITE:   _preview_api,
        SourceType.GRAPHQL:   _preview_graphql,
        SourceType.CLI_APP:   _preview_cli,
        SourceType.CODEBASE:  _preview_codebase,
    }
    printer = _PREVIEW_PRINTERS.get(source_type)
    if printer:
        printer(tool)

    if tool.parameters:
        params = ", ".join(p.name for p in tool.parameters[:4])
        suffix = " ..." if len(tool.parameters) > 4 else ""
        console.print(f"  [dim]params: {params}{suffix}[/dim]")


def _preview_api(tool: DiscoveredTool) -> None:
    if tool.http_method and tool.endpoint:
        console.print(f"  [dim]{tool.http_method} {tool.endpoint}[/dim]")
    elif tool.tags:
        console.print(f"  [dim]source: {tool.tags[0]}[/dim]")


def _preview_graphql(tool: DiscoveredTool) -> None:
    op = tool.tags[0] if tool.tags else "query"
    console.print(f"  [dim]GraphQL {op}[/dim]")


def _preview_cli(tool: DiscoveredTool) -> None:
    cmd = (tool.metadata or {}).get("cmd", [])
    if cmd:
        console.print(f"  [dim]cmd: {' '.join(cmd)}[/dim]")


def _preview_codebase(tool: DiscoveredTool) -> None:
    meta = tool.metadata or {}
    fichier = meta.get("file", "")
    classe = meta.get("class") or ""
    func = meta.get("function", tool.name)
    qualified = f"{classe}.{func}" if classe else func
    console.print(f"  [dim]{fichier} >> {qualified}[/dim]")


# ------------------------------------------------------------------
# Étape 4 : édition des tools
# ------------------------------------------------------------------

def _edit_tools_guided(
    tools: list[DiscoveredTool], source_type: SourceType
) -> list[DiscoveredTool]:
    console.print("[dim]  Entrée = conserver la valeur actuelle.[/dim]")
    for tool in tools:
        console.print(f"\n  [bold cyan]{tool.name}[/bold cyan]")
        tool.name = typer.prompt("  Nom", default=tool.name)
        tool.description = typer.prompt("  Description", default=tool.description)

        # Édition spécifique par source
        if source_type == SourceType.CLI_APP:
            _edit_cli_tool(tool)
        elif source_type == SourceType.CODEBASE:
            _edit_codebase_tool(tool)
        elif source_type == SourceType.GRAPHQL:
            _edit_graphql_tool(tool)

        tool.reviewed = True

    return tools


def _edit_cli_tool(tool: DiscoveredTool) -> None:
    """Édition enrichie pour les tools CLI : ajuste les flags des paramètres."""
    if not tool.parameters:
        return
    edit_params = typer.confirm(
        f"  Éditer les {len(tool.parameters)} flag(s) CLI ?", default=False
    )
    if not edit_params:
        return
    for param in tool.parameters:
        console.print(f"    [dim]--{param.name.replace('_', '-')}[/dim] ({param.type.value})")
        param.description = typer.prompt(
            f"    Description du flag --{param.name}", default=param.description
        )


def _edit_codebase_tool(tool: DiscoveredTool) -> None:
    """Édition enrichie pour les tools codebase : affiche la signature et ajuste les paramètres."""
    meta = tool.metadata or {}
    fichier = meta.get("file", "")
    classe = meta.get("class") or ""
    func = meta.get("function", tool.name)
    is_async = meta.get("is_async", False)

    prefix = "async " if is_async else ""
    qualified = f"{classe}.{func}" if classe else func
    console.print(f"  [dim]{prefix}def {qualified}() — {fichier}[/dim]")

    if tool.parameters:
        edit_params = typer.confirm(
            f"  Éditer les {len(tool.parameters)} paramètre(s) ?", default=False
        )
        if edit_params:
            for param in tool.parameters:
                console.print(f"    [dim]{param.name}: {param.type.value}[/dim]")
                param.description = typer.prompt(
                    f"    Description de '{param.name}'", default=param.description
                )


def _edit_graphql_tool(tool: DiscoveredTool) -> None:
    """Affiche le type d'opération GraphQL et permet d'affiner les arguments."""
    op = tool.tags[0] if tool.tags else "query"
    console.print(f"  [dim]GraphQL {op}[/dim]")

    if tool.parameters:
        edit_params = typer.confirm(
            f"  Éditer les {len(tool.parameters)} argument(s) GraphQL ?", default=False
        )
        if edit_params:
            for param in tool.parameters:
                console.print(f"    [dim]{param.name}: {param.type.value}{'!' if param.required else ''}[/dim]")
                param.description = typer.prompt(
                    f"    Description de '{param.name}'", default=param.description
                )


# ------------------------------------------------------------------
# Étape 6 : paramètres serveur
# ------------------------------------------------------------------

def _prompt_server_params(config: ForgeConfig, result: DiscoveryResult) -> None:
    default_name = config.server_name or result.title.lower().replace(" ", "_") or "mcp_server"
    config.server_name = typer.prompt("Nom du serveur (snake_case)", default=default_name)
    config.server_description = typer.prompt(
        "Description du serveur",
        default=config.server_description or result.description or "",
    )
    config.output_dir = typer.prompt("Dossier de sortie", default=config.output_dir)

    # Avertissements selon la source
    if result.source_type == SourceType.CODEBASE:
        console.print(
            "[yellow]  ℹ Le serveur généré importera le code source directement "
            f"depuis : {result.source_path}[/yellow]"
        )
    elif result.source_type == SourceType.CLI_APP:
        console.print(
            "[yellow]  ℹ Le serveur exécutera des commandes système — "
            "vérifiez les permissions et la disponibilité des binaires.[/yellow]"
        )


# ------------------------------------------------------------------
# Étape 8 : review du code généré
# ------------------------------------------------------------------

def _review_code_guided(generated: GeneratedServer, source_type: SourceType) -> None:
    console.print(f"  Fichiers générés dans : [bold]{generated.output_dir}[/bold]")

    _print_source_warnings(source_type)

    for filename in generated.files:
        show = typer.confirm(f"  Afficher {filename} ?", default=False)
        if show:
            content = generated.files[filename]
            lang = "python" if filename.endswith(".py") else "markdown"
            console.print(Syntax(content, lang, theme="monokai", line_numbers=True))


def _print_source_warnings(source_type: SourceType) -> None:
    warnings = {
        SourceType.CLI_APP: (
            "[yellow]  ℹ server.py lance des sous-processus — "
            "les commandes doivent être dans le PATH.[/yellow]"
        ),
        SourceType.CODEBASE: (
            "[yellow]  ℹ server.py importe le code source — "
            "ses dépendances doivent être installées.[/yellow]"
        ),
        SourceType.WEBSITE: (
            "[yellow]  ℹ server.py fait des requêtes HTTP — "
            "vérifiez les politiques CORS et robots.txt du site.[/yellow]"
        ),
    }
    warning = warnings.get(source_type)
    if warning:
        console.print(warning)
