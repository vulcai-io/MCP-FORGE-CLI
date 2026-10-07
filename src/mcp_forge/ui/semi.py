"""
Mode SEMI : pipeline avec deux pauses de review interactives.

  SOURCE >> DISCOVERY >> [REVIEW TOOLS] >> ENRICHMENT >> GENERATION >> [REVIEW CODE] >> VALIDATION
"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from mcp_forge.models import DiscoveredTool, DiscoveryResult, ForgeConfig, GeneratedServer, SourceType

console = Console()

# Au-delà de ce seuil, on affiche un résumé au lieu d'un tableau ligne par ligne
_TABLE_MAX_ROWS = 300


def run_semi(config: ForgeConfig) -> GeneratedServer | None:
    from mcp_forge.discovery import discover
    from mcp_forge.pipeline.selector import run_pipeline
    from mcp_forge.validation import MCPValidator

    # 1. Discovery
    result = discover(config)

    if not result.tools:
        console.print("[yellow]⚠ Aucun tool découvert.[/yellow]")
        return None

    # 2. Review des tools — tableau adapté à la source
    result = _review_tools(result)
    enabled = [t for t in result.tools if t.enabled]
    if not enabled:
        console.print("[yellow]⚠ Aucun tool sélectionné.[/yellow]")
        return None

    # 3. Enrichissement + Génération (local ou Azure selon l'environnement)
    generated = run_pipeline(result, config)

    # 4. Review du code généré
    _review_generated(generated, result.source_type)

    # 5. Validation
    MCPValidator().validate(generated)

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
# Review des tools
# ------------------------------------------------------------------

def _review_tools(result: DiscoveryResult) -> DiscoveryResult:
    console.print()
    console.rule("[bold blue]Review des tools découverts[/bold blue]")

    n = len(result.tools)
    large = n > _TABLE_MAX_ROWS

    if large:
        _print_summary_review(result)
    else:
        table = _build_review_table(result)
        console.print(table)

    console.print()
    console.print(f"[dim]{n} tool(s) trouvé(s). Laissez vide pour tout garder.[/dim]")

    if large:
        console.print(
            "[dim]Conseil : excluez par numéro ou par préfixe de fichier "
            "(ex: [bold]file:script/goat[/bold] pour exclure tout un dossier).[/dim]"
        )

    raw = typer.prompt(
        "Numéros à EXCLURE (ex: 2,5,8), préfixe fichier (file:dossier/) ou Entrée pour tout garder",
        default="",
    )

    if raw.strip():
        _apply_exclusions(result.tools, raw)

    enabled_count = sum(1 for t in result.tools if t.enabled)
    console.print(f"[green]{enabled_count} tool(s) conservé(s)[/green]")
    return result


def _apply_exclusions(tools: list[DiscoveredTool], raw: str) -> None:
    """Applique les exclusions par numéro ou par préfixe de fichier."""
    excluded_nums: set[int] = set()
    file_prefixes: list[str] = []

    for token in raw.split(","):
        token = token.strip()
        if token.startswith("file:"):
            file_prefixes.append(token[5:].strip().replace("\\", "/"))
        elif token.isdigit():
            excluded_nums.add(int(token))

    disabled = 0
    for i, tool in enumerate(tools, 1):
        file_path = (tool.metadata or {}).get("file", "").replace("\\", "/")
        if i in excluded_nums or any(file_path.startswith(p) for p in file_prefixes):
            tool.enabled = False
            disabled += 1

    if disabled:
        console.print(f"[dim]  {disabled} tool(s) désactivé(s)[/dim]")


def _print_summary_review(result: DiscoveryResult) -> None:
    """Affiche un résumé par fichier/dossier au lieu d'un tableau ligne par ligne."""
    from collections import Counter
    from rich.table import Table as RichTable

    console.print(f"[yellow]⚠ {len(result.tools)} tools — affichage résumé par fichier.[/yellow]")

    # Compte les tools par fichier (ou dossier de niveau 1)
    file_counts: Counter[str] = Counter()
    for tool in result.tools:
        f = (tool.metadata or {}).get("file", "–").replace("\\", "/")
        # Regroupe par dossier de premier niveau pour les gros projets
        parts = f.split("/")
        key = "/".join(parts[:2]) if len(parts) > 2 else f
        file_counts[key] += 1

    # Tableau résumé : top 30 fichiers/dossiers
    table = RichTable(show_header=True, header_style="bold", expand=False)
    table.add_column("Fichier / Dossier", style="cyan")
    table.add_column("Nb tools", justify="right")

    console.print("[dim]  Construction du résumé...[/dim]")
    for path, count in file_counts.most_common(30):
        table.add_row(path, str(count))
    if len(file_counts) > 30:
        table.add_row(f"[dim]... et {len(file_counts) - 30} autre(s)[/dim]", "")

    console.print(table)

    # Aperçu : 10 premiers tools
    console.print()
    console.print("[dim]Aperçu des 10 premiers tools :[/dim]")
    preview = RichTable(show_header=True, header_style="bold dim", expand=False)
    preview.add_column("#", style="dim", width=6)
    preview.add_column("Nom", style="cyan")
    preview.add_column("Fichier")
    for i, tool in enumerate(result.tools[:10], 1):
        f = (tool.metadata or {}).get("file", "–")
        preview.add_row(str(i), tool.name, f)
    console.print(preview)


def _build_review_table(result: DiscoveryResult) -> Table:
    """Construit un tableau de review adapté au type de source (≤ _TABLE_MAX_ROWS)."""
    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Nom", style="cyan", no_wrap=True)

    builders = {
        SourceType.OPENAPI:   _fill_api_table,
        SourceType.WEBSITE:   _fill_api_table,
        SourceType.GRAPHQL:   _fill_api_table,
        SourceType.CLI_APP:   _fill_cli_table,
        SourceType.CODEBASE:  _fill_codebase_table,
    }
    builder = builders.get(result.source_type, _fill_api_table)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(), MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("  Préparation du tableau", total=len(result.tools))
        builder(table, result, progress, task)

    return table


def _fill_api_table(table: Table, result: DiscoveryResult, progress: Progress, task: object) -> None:
    table.add_column("Type", width=10)
    table.add_column("Endpoint / Tag")
    table.add_column("Description")
    for i, tool in enumerate(result.tools, 1):
        tag = tool.tags[0].upper() if tool.tags else "–"
        table.add_row(
            str(i), tool.name,
            _format_method_cell(tool, result.source_type),
            tool.endpoint or tag,
            _truncate(tool.description),
        )
        progress.advance(task)


def _fill_cli_table(table: Table, result: DiscoveryResult, progress: Progress, task: object) -> None:
    table.add_column("Commande")
    table.add_column("Options", width=12)
    table.add_column("Description")
    for i, tool in enumerate(result.tools, 1):
        cmd = " ".join((tool.metadata or {}).get("cmd", [tool.name]))
        table.add_row(
            str(i), tool.name,
            cmd,
            f"{len(tool.parameters)} option(s)",
            _truncate(tool.description),
        )
        progress.advance(task)


def _fill_codebase_table(table: Table, result: DiscoveryResult, progress: Progress, task: object) -> None:
    table.add_column("Fichier")
    table.add_column("Classe / Fonction")
    table.add_column("Description")
    for i, tool in enumerate(result.tools, 1):
        meta = tool.metadata or {}
        classe = meta.get("class") or ""
        func = meta.get("function", tool.name)
        table.add_row(
            str(i), tool.name,
            meta.get("file", "–"),
            f"{classe}.{func}" if classe else func,
            _truncate(tool.description),
        )
        progress.advance(task)


def _truncate(text: str, limit: int = 55) -> str:
    return text[:limit] + "..." if len(text) > limit else text


def _format_method_cell(tool: DiscoveredTool, source_type: SourceType) -> str:
    """Formate la colonne 'Type' selon la source."""
    if source_type == SourceType.GRAPHQL:
        tag = tool.tags[0] if tool.tags else "query"
        return f"[magenta]{tag}[/magenta]"
    if source_type == SourceType.WEBSITE:
        tag = tool.tags[0] if tool.tags else ""
        colors = {"nav": "blue", "form": "green", "js": "yellow", "openapi": "cyan"}
        color = colors.get(tag, "white")
        return f"[{color}]{tag or '–'}[/{color}]"
    # OpenAPI : méthode HTTP
    method = tool.http_method or "–"
    colors = {"GET": "green", "POST": "yellow", "PUT": "blue", "PATCH": "cyan", "DELETE": "red"}
    color = colors.get(method, "white")
    return f"[{color}]{method}[/{color}]"


# ------------------------------------------------------------------
# Review du code généré
# ------------------------------------------------------------------

def _review_generated(generated: GeneratedServer, source_type: SourceType) -> None:
    console.print()
    console.rule("[bold blue]Review du code généré[/bold blue]")

    server_code = generated.files.get("server.py", "")
    console.print(f"[dim]server.py ({len(server_code.splitlines())} lignes) — {source_type.value}[/dim]")

    # Aperçu des premiers tools dans le fichier généré
    tool_count = server_code.count("@mcp.tool()")
    console.print(f"[dim]{tool_count} outil(s) MCP dans le fichier[/dim]")
    console.print()

    show = typer.confirm("Afficher server.py dans le terminal ?", default=False)
    if show:
        from rich.syntax import Syntax
        console.print(Syntax(server_code, "python", theme="monokai", line_numbers=True))

    # Pour CLI et Codebase : avertissement spécifique
    if source_type == SourceType.CLI_APP:
        console.print(
            "[yellow]  ℹ Le serveur lance des sous-processus — "
            "vérifiez que les commandes sont disponibles dans le PATH.[/yellow]"
        )
    elif source_type == SourceType.CODEBASE:
        console.print(
            "[yellow]  ℹ Le serveur importe le code source directement — "
            "assurez-vous que les dépendances du codebase sont installées.[/yellow]"
        )

    console.print(f"\n[bold]Fichiers générés dans :[/bold] {generated.output_dir}")
    typer.confirm("Continuer avec la validation ?", default=True, abort=True)
