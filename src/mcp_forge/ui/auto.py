"""
Mode AUTO : pipeline complet sans aucune intervention de l'utilisateur.

  SOURCE >> DISCOVERY >> ENRICHMENT >> GENERATION >> VALIDATION

Sortie :
  - Logs / progression >> stderr (Rich)
  - Résultat JSON      >> stdout, seul (0.4.1, voir mcp_forge/ui/json_stdout.py)
"""
from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.progress import Progress, SpinnerColumn, TextColumn

from mcp_forge.models import ForgeConfig, GeneratedServer

# Rich sur stderr — stdout réservé au JSON machine-readable
console = Console(stderr=True)


def run_auto(config: ForgeConfig) -> GeneratedServer | None:
    from mcp_forge.discovery import discover
    from mcp_forge.pipeline.selector import run_pipeline
    from mcp_forge.validation import MCPValidator

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:

        # 1. Discovery
        task = progress.add_task("Discovering capabilities...", total=None)
        result = discover(config)
        progress.update(task, description=f"[green][OK] {len(result.tools)} tools discovered[/green]")
        progress.stop_task(task)

        if not result.tools:
            console.print("[yellow]⚠ No tool discovered. Check the source.[/yellow]")
            _print_json(None, errors=["No tool discovered"])
            return None

        # 2. Enrichissement + Génération (local ou Azure selon l'environnement)
        task = progress.add_task("Enrichment and generation...", total=None)
        try:
            generated = run_pipeline(result, config)
        except Exception as _exc:
            progress.stop_task(task)
            progress.stop()
            from mcp_forge.pipeline.remote import RemoteError
            if isinstance(_exc, RemoteError):
                console.print(f"[red][FAIL] {escape(str(_exc))}[/red]")
            else:
                console.print(f"[red][FAIL] Unexpected error: {_exc}[/red]")
            _print_json(None, errors=[str(_exc)])
            return None
        progress.update(task, description=f"[green][OK] Server generated ({generated.tools_count} tools)[/green]")
        progress.stop_task(task)

        # 3. Validation
        task = progress.add_task("Validation...", total=None)
        validator = MCPValidator()
        validator.validate(generated)
        progress.stop_task(task)

    _print_json(generated)
    _print_hints(generated)

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
    console.print(f"[dim]Evaluation report: {report_path}[/dim]")


def _print_json(generated: GeneratedServer | None, errors: list[str] | None = None) -> None:
    """Écrit le résultat JSON sur stdout — lisible par les pipelines CI/CD."""
    if generated is None:
        payload = {"success": False, "errors": errors or []}
    else:
        out = str(generated.output_dir).replace("\\", "/")
        payload = {
            "success": generated.success,
            "server_name": generated.server_name,
            "output_dir": out,
            "tools_count": generated.tools_count,
            "files": list(generated.files.keys()),
            "errors": generated.errors,
        }
    from mcp_forge.ui.json_stdout import emit_result
    emit_result(payload)


def _print_hints(generated: GeneratedServer) -> None:
    """Affiche des conseils post-génération sur stderr."""
    from mcp_forge.models import SourceType

    if not generated.success:
        console.print(f"[red][FAIL] Generation failed:[/red] {', '.join(generated.errors)}")
        return

    out = str(generated.output_dir).replace("\\", "/")
    console.print(f"\n[bold]To run:[/bold]  cd {out} && python server.py")
    console.print(f"[bold]To test:[/bold]  mcp-forge test {out}/server.py")

    source_type_str = ""
    server = generated.files.get("server.py", "")
    if "ctypes.CDLL" in server:
        source_type_str = "cpp"
    elif "subprocess" in server:
        source_type_str = SourceType.CLI_APP.value
    elif "importlib" in server:
        source_type_str = SourceType.CODEBASE.value
    elif "graphql" in server.lower():
        source_type_str = SourceType.GRAPHQL.value

    hints = {
        "cpp": "[dim]  ℹ Build your shared library (.dll/.so) and set CPP_LIB_PATH.[/dim]",
        SourceType.CLI_APP.value: "[dim]  ℹ Check that the CLI commands are on the PATH.[/dim]",
        SourceType.CODEBASE.value: "[dim]  ℹ Install the dependencies of the source codebase.[/dim]",
        SourceType.WEBSITE.value: "[dim]  ℹ Read the target site's robots.txt before deploying.[/dim]",
    }
    hint = hints.get(source_type_str)
    if hint:
        console.print(hint)
