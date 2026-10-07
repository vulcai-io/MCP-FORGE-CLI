"""
mcp-forge — Point d'entrée CLI principal.

Usage:
    mcp-forge run <source> [options]
    mcp-forge --help
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated, Optional

# Force stdout/stderr en UTF-8 avec remplacement des caractères non
# encodables, au lieu de laisser planter sur le codepage par défaut de la
# console (cp1252 sur beaucoup de terminaux Windows). Sans ça, le moindre
# `console.print` contenant un symbole Rich courant (⚠, ℹ, →...) lève une
# UnicodeEncodeError — qui, étant une sous-classe de ValueError, se fait
# ensuite happer par les `except ValueError` disséminés dans le pipeline
# d'enrichissement LLM (mcp_forge/pipeline/local.py) et masque la VRAIE
# erreur (ex: un 401 Unauthorized de l'API) derrière un message de codec
# incompréhensible. Trouvé en testant sur Windows contre une vraie
# codebase COBOL (aws-mainframe-modernization-carddemo).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

# Dossier output par défaut : dans le répertoire courant de l'utilisateur
# (Path(__file__) pointe vers site-packages après pip install — on utilise cwd)
_DEFAULT_OUTPUT = str(Path.cwd() / "mcp-forge-output")

from dotenv import load_dotenv
load_dotenv(Path.cwd() / ".env")  # Charge .env depuis le dossier de travail de l'utilisateur

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel

from mcp_forge.config_loader import load_yaml_config
from mcp_forge.models import ForgeConfig, ForgeMode, NameStyle, SourceType

def _version_callback(value: bool) -> None:
    if value:
        from mcp_forge import __version__
        typer.echo(f"mcp-forge {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="mcp-forge",
    help="Génère automatiquement un serveur MCP à partir d'une application ou d'un site web.",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


@app.callback()
def _main(
    version: Annotated[Optional[bool], typer.Option(
        "--version", "-V", callback=_version_callback, is_eager=True, help="Afficher la version et quitter"
    )] = None,
) -> None:
    # Typer callback — gestion de --version uniquement, aucune logique supplémentaire.
    pass


def _detect_source_type(source: str) -> SourceType:
    """Détecte automatiquement le type de source."""
    s = source.lower()
    if s.endswith((".json", ".yaml", ".yml")):
        return SourceType.OPENAPI
    if "graphql" in s or s.endswith("/graphql"):
        return SourceType.GRAPHQL
    if s.startswith("http://") or s.startswith("https://"):
        return SourceType.WEBSITE
    if Path(source).is_dir():
        return SourceType.CODEBASE
    return SourceType.CLI_APP


@app.command()
def run(
    source: Annotated[Optional[str], typer.Argument(help="URL, fichier OpenAPI, commande CLI ou dossier de code")] = None,
    mode: Annotated[Optional[ForgeMode], typer.Option("--mode", "-m", help="Mode de génération")] = None,
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="Dossier de sortie")] = None,
    source_type: Annotated[Optional[SourceType], typer.Option("--type", "-t", help="Forcer le type de source")] = None,
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="Nom du serveur MCP généré")] = None,
    no_llm: Annotated[Optional[bool], typer.Option("--no-llm", help="Désactiver l'enrichissement par LLM")] = None,
    api_key: Annotated[Optional[str], typer.Option("--api-key", help="Clé API Anthropic (ou via ANTHROPIC_API_KEY)")] = None,
    name_style: Annotated[Optional[NameStyle], typer.Option("--name-style", "-ns", help="Style de nommage : short ou exhaustive")] = None,
    config_file: Annotated[Optional[str], typer.Option("--config", "-c", help="Fichier de configuration YAML (défaut : mcp-forge.yaml si présent)")] = None,
    smoke_test: Annotated[bool, typer.Option("--smoke-test", help="Lancer le smoke test après génération")] = False,
    functional_test: Annotated[bool, typer.Option("--functional-test", help="Lancer le test fonctionnel MCP après génération (démarre le serveur)")] = False,
    local: Annotated[bool, typer.Option("--local", help="Forcer le pipeline local (pas d'appel à l'API Vulcai)")] = False,
    lang: Annotated[str, typer.Option("--lang", help="Langue des commentaires générés : en (défaut) ou fr")] = "en",
    bundle_source: Annotated[bool, typer.Option("--bundle-source", help="Copier le code source (codebase) dans le serveur généré — désactivé par défaut, votre code ne quitte pas la machine")] = False,
):
    """
    Lance la génération d'un serveur MCP depuis une [bold]source[/bold].

    Exemples :
      mcp-forge run https://api.example.com/openapi.json
      mcp-forge run https://example.com --mode semi
      mcp-forge run my-cli-app --mode guided
    """
    console.print(Panel.fit(
        "[bold blue]mcp-forge[/bold blue] — Générateur de serveurs MCP",
        border_style="blue",
    ))

    yaml_cfg = _load_yaml(config_file)
    source, mode, output, source_type, name, no_llm, name_style, smoke_test, functional_test = \
        _merge_options(yaml_cfg, source, mode, output, source_type, name, no_llm,
                       name_style, smoke_test, functional_test)

    bundle_source = bundle_source or yaml_cfg.get("bundle_source", False)
    config, no_llm = _build_config(yaml_cfg, source, mode, output, source_type, name,
                                   no_llm, name_style, api_key, force_local=local, lang=lang,
                                   bundle_source=bundle_source)

    _print_summary(source, config.source_type, mode, output, no_llm, name_style)

    generated = _dispatch(config, mode)

    if generated is None or not generated.success:
        raise typer.Exit(1)

    if smoke_test:
        _run_smoke_test_cmd(generated.output_dir)
    if functional_test:
        _run_functional_test_cmd(generated.output_dir)


# ---------------------------------------------------------------------------
# Helpers internes — run()
# ---------------------------------------------------------------------------

def _load_yaml(config_file: Optional[str]) -> dict:
    try:
        return load_yaml_config(config_file)
    except FileNotFoundError as e:
        console.print(f"[red][FAIL] {e}[/red]")
        raise typer.Exit(1)


def _merge_options(
    yaml_cfg: dict,
    source: Optional[str],
    mode: Optional[ForgeMode],
    output: Optional[str],
    source_type: Optional[SourceType],
    name: Optional[str],
    no_llm: Optional[bool],
    name_style: Optional[NameStyle],
    smoke_test: bool,
    functional_test: bool,
) -> tuple:
    source = source or yaml_cfg.get("source")
    if not source:
        console.print("[red][FAIL] Source requise (argument ou champ 'source' dans mcp-forge.yaml)[/red]")
        raise typer.Exit(1)

    if not source.startswith("http://") and not source.startswith("https://"):
        source = source.replace("\\", "/")

    mode = mode or (ForgeMode(yaml_cfg["mode"]) if "mode" in yaml_cfg else ForgeMode.AUTO)
    output = output or yaml_cfg.get("output", _DEFAULT_OUTPUT)
    name = name or yaml_cfg.get("name")
    no_llm = no_llm if no_llm is not None else yaml_cfg.get("no_llm", False)
    smoke_test = smoke_test or yaml_cfg.get("smoke_test", False)
    functional_test = functional_test or yaml_cfg.get("functional_test", False)
    name_style = name_style or (NameStyle(yaml_cfg["name_style"]) if "name_style" in yaml_cfg else NameStyle.SHORT)
    if source_type is None and "type" in yaml_cfg:
        source_type = SourceType(yaml_cfg["type"])

    return source, mode, output, source_type, name, no_llm, name_style, smoke_test, functional_test


def _build_config(
    yaml_cfg: dict,
    source: str,
    mode: ForgeMode,
    output: str,
    source_type: Optional[SourceType],
    name: Optional[str],
    no_llm: bool,
    name_style: NameStyle,
    api_key: Optional[str],
    force_local: bool = False,
    lang: str = "en",
    bundle_source: bool = False,
) -> tuple:
    resolved_type = source_type or _detect_source_type(source)
    resolved_key = api_key or yaml_cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")

    if not no_llm and not resolved_key and not os.environ.get("GROQ_API_KEY"):
        console.print(
            "[yellow]⚠ Aucune clé API trouvée.[/yellow] "
            "L'enrichissement LLM sera désactivé. "
            "Définissez ANTHROPIC_API_KEY ou GROQ_API_KEY dans votre .env."
        )
        no_llm = True

    config = ForgeConfig(
        mode=mode,
        source=source,
        source_type=resolved_type,
        output_dir=output,
        server_name=name or "",
        use_llm_enrichment=not no_llm,
        anthropic_api_key=resolved_key,
        name_style=name_style,
        force_local=force_local,
        lang=lang,
        bundle_source=bundle_source,
    )
    return config, no_llm


def _print_summary(
    source: str, resolved_type: SourceType, mode: ForgeMode,
    output: str, no_llm: bool, name_style: NameStyle,
) -> None:
    console.print(f"[dim]Source     :[/dim] {source}")
    console.print(f"[dim]Type       :[/dim] {resolved_type.value}")
    console.print(f"[dim]Mode       :[/dim] {mode.value}")
    console.print(f"[dim]Sortie     :[/dim] {output}")
    console.print(f"[dim]Enrichiss. :[/dim] {'LLM (Claude)' if not no_llm else 'désactivé'}")
    if not no_llm:
        console.print(f"[dim]Nommage    :[/dim] {name_style.value}")
    console.print()


def _dispatch(config: ForgeConfig, mode: ForgeMode):
    if mode == ForgeMode.AUTO:
        from mcp_forge.ui.auto import run_auto
        return run_auto(config)
    if mode == ForgeMode.SEMI:
        from mcp_forge.ui.semi import run_semi
        return run_semi(config)
    if mode == ForgeMode.GUIDED:
        from mcp_forge.ui.guided import run_guided
        return run_guided(config)
    return None


@app.command()
def test(
    server: Annotated[str, typer.Argument(help="Chemin vers server.py (backslashes acceptés)")],
):
    """
    Lance MCP Inspector sur un serveur généré.

    Accepte les chemins Windows (backslashes) collés depuis l'Explorateur.

    Exemples :
      mcp-forge test output\\py_requests\\server.py
      mcp-forge test output/py_requests/server.py
    """
    import subprocess
    normalized = server.replace("\\", "/")
    server_path = Path(normalized)
    if not server_path.exists():
        # Essaie relatif au dossier mcp-forge
        server_path = Path(__file__).parent / normalized
    if not server_path.exists():
        console.print(f"[red][FAIL] Fichier introuvable :[/red] {normalized}")
        raise typer.Exit(1)
    server_dir = server_path.resolve().parent
    console.print(f"[dim]Lancement de MCP Inspector sur :[/dim] {server_dir / 'server.py'}")
    # Installe les dépendances si requirements.txt présent (met en cache pour uv)
    req_file = server_dir / "requirements.txt"
    if req_file.exists():
        import sys
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)],
            cwd=str(server_dir),
        )
    # Lance le MCP Inspector via npx + uv python (évite le prérequis mcp[cli])
    # shell=True requis sur Windows car npx est un .cmd et non un exécutable natif
    result = subprocess.run(
        ["npx", "-y", "@modelcontextprotocol/inspector",
         "uv", "run", "--with", "mcp", "python", "server.py"],
        cwd=str(server_dir),
        shell=True,
    )
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


@app.command(name="smoke-test")
def smoke_test_cmd(
    server_dir: Annotated[str, typer.Argument(help="Dossier du serveur MCP généré (contient server.py)")],
):
    """
    Vérifie qu'un serveur MCP généré est valide sans le démarrer.

    Contrôles effectués :
      • server.py présent
      • Syntaxe Python valide
      • Import sans erreur (subprocess isolé)
      • Objet mcp présent
      • Au moins 1 @mcp.tool enregistré
      • Cohérence avec le fichier VERSION

    Exemples :
      mcp-forge smoke-test output/my_server
      mcp-forge smoke-test output\\my_server
    """
    normalized = server_dir.replace("\\", "/")
    _run_smoke_test_cmd(normalized)


def _run_smoke_test_cmd(server_dir: str) -> None:
    """Exécute le smoke test et affiche les résultats. Exit 1 si échec."""
    from mcp_forge.validation.smoke_test import run_smoke_test

    normalized = server_dir.replace("\\", "/")
    path = Path(normalized)
    if not path.exists():
        path = Path(__file__).parent / normalized
    if not path.exists():
        console.print(f"[red][FAIL] Dossier introuvable :[/red] {normalized}")
        raise typer.Exit(1)

    console.print(f"\n[bold]>> Smoke test :[/bold] {path}")
    result = run_smoke_test(path)

    for label, ok, detail in result.checks:
        color = "green" if ok else "red"
        mark = "OK  " if ok else "FAIL"
        suffix = f" -- {detail}" if detail else ""
        console.print(f"  [{color}]{mark}[/{color}] {label}{suffix}")

    if result.success:
        console.print(f"\n[green bold]Smoke test OK[/green bold] ({result.tools_found} tool(s))")
    else:
        console.print("\n[red bold]Smoke test ECHEC[/red bold]")
        raise typer.Exit(1)


@app.command(name="functional-test")
def functional_test_cmd(
    server_dir: Annotated[str, typer.Argument(help="Dossier du serveur MCP (contient server.py)")],
    timeout: Annotated[float, typer.Option("--timeout", "-t", help="Délai max en secondes par étape")] = 15.0,
):
    """
    Test fonctionnel : démarre le serveur MCP et vérifie ses tools via le protocole MCP.

    Contrairement au smoke-test (import Python), ce test démarre réellement le serveur
    et communique avec lui via JSON-RPC / stdio — comme un vrai client MCP.

    Vérifications :
      • Serveur démarre sans erreur
      • Handshake MCP (initialize) réussi
      • tools/list retourne au moins 1 tool
      • Nombre de tools correspond au fichier VERSION
      • Cohérence avec les @mcp.tool du source

    Exemples :
      mcp-forge functional-test output/my_server
      mcp-forge functional-test output\\my_server --timeout 30
    """
    normalized = server_dir.replace("\\", "/")
    _run_functional_test_cmd(normalized, timeout=timeout)


_FT_STATUS_COLOR = {"ok": "green", "warn": "yellow", "fail": "red", "skip": "dim"}
_FT_STATUS_MARK  = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL", "skip": "SKIP"}


def _print_ft_phase1(result) -> None:
    for label, ok, detail in result.checks:
        color  = "green" if ok else "red"
        mark   = "OK  " if ok else "FAIL"
        suffix = f" -- {detail}" if detail else ""
        console.print(f"  [{color}]{mark}[/{color}] {label}{suffix}")


def _print_ft_phase2(result) -> None:
    if not result.tool_calls:
        return
    console.print("\n[bold]Phase 2 -- Appel des tools :[/bold]")
    for tc in result.tool_calls:
        color    = _FT_STATUS_COLOR.get(tc.status, "white")
        mark     = _FT_STATUS_MARK.get(tc.status, "?   ")
        args_str = f"  args={tc.args_used}" if tc.args_used else ""
        suffix   = f" -- {tc.detail}" if tc.detail else ""
        console.print(f"  [{color}]{mark}[/{color}] {tc.name}{args_str}{suffix}")


def _run_functional_test_cmd(server_dir: str, timeout: float = 15.0) -> None:
    """Exécute le test fonctionnel MCP et affiche les résultats. Exit 1 si échec."""
    from mcp_forge.validation.functional_test import run_functional_test

    normalized = server_dir.replace("\\", "/")
    path = Path(normalized)
    if not path.exists():
        path = Path(__file__).parent / normalized
    if not path.exists():
        console.print(f"[red]Dossier introuvable :[/red] {normalized}")
        raise typer.Exit(1)

    console.print(f"\n[bold]>> Test fonctionnel MCP :[/bold] {path}")
    console.print("[dim]  Démarrage du serveur...[/dim]")
    result = run_functional_test(path, timeout=timeout)

    _print_ft_phase1(result)
    _print_ft_phase2(result)

    if result.success:
        console.print(f"\n[green bold]Test fonctionnel OK[/green bold] ({len(result.tools_listed)} tool(s))")
    else:
        console.print("\n[red bold]Test fonctionnel ECHEC[/red bold]")
        raise typer.Exit(1)


@app.command(name="list")
def list_servers(
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="Dossier de sortie à inspecter")] = None,
):
    """
    Liste les serveurs MCP générés dans le dossier de sortie.

    Pour chaque serveur, affiche : nom, date de génération, source, nombre de tools.
    """
    from rich.table import Table

    output_dir = Path(output or _DEFAULT_OUTPUT)
    if not output_dir.exists():
        console.print(f"[yellow]Dossier introuvable :[/yellow] {output_dir}")
        raise typer.Exit(0)

    servers = sorted(
        [d for d in output_dir.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )

    if not servers:
        console.print(f"[dim]Aucun serveur dans {output_dir}[/dim]")
        raise typer.Exit(0)

    table = Table(title=f"Serveurs MCP dans {output_dir}", show_lines=False)
    table.add_column("Nom", style="bold cyan", no_wrap=True)
    table.add_column("Tools", justify="right")
    table.add_column("Genere le", style="dim")
    table.add_column("Source", style="dim", overflow="fold")

    for d in servers:
        version_path = d / "VERSION"
        if version_path.exists():
            data = {}
            for line in version_path.read_text(encoding="utf-8").splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    data[k.strip()] = v.strip()
            tools = data.get("tools_count", "?")
            generated_at = data.get("generated_at", "?")
            source = data.get("source", "?")
        else:
            tools = "?"
            generated_at = "?"
            source = "[dim](no VERSION file)[/dim]"

        table.add_row(d.name, str(tools), generated_at, source)

    console.print(table)


@app.command(name="set-license")
def set_license(
    key: Annotated[str, typer.Argument(help="Clé de licence (format : mfg_live_... ou mfg_test_...)")],
):
    """
    Enregistre la clé de licence dans le fichier .env du dossier courant.

    Exemple :
      mcp-forge set-license mfg_live_abc123...
    """
    env_path = Path.cwd() / ".env"
    lines: list[str] = []

    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        lines = [l for l in lines if not l.startswith("FORGE_LICENSE_KEY=")]

    lines.append(f"FORGE_LICENSE_KEY={key}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"[green][OK] Clé de licence enregistrée dans {env_path}[/green]")
    console.print("[dim]Elle sera utilisée automatiquement à chaque appel de mcp-forge run.[/dim]")


@app.command()
def info():
    """Affiche des informations sur mcp-forge et les types de sources supportés."""
    rprint(Panel(
        """[bold]Sources supportées :[/bold]

  [green]openapi[/green]   Fichier ou URL OpenAPI/Swagger (.json, .yaml)
  [green]website[/green]   Site web ou API REST (URL http/https)
  [green]graphql[/green]   API GraphQL (URL avec /graphql)
  [green]cli_app[/green]   Application CLI locale
  [green]codebase[/green]  Dossier de code source

[bold]Modes :[/bold]

  [blue]auto[/blue]     Génération entièrement automatique
  [blue]semi[/blue]     Pause pour review des tools et du code généré
  [blue]guided[/blue]   Étape par étape avec choix interactif

[bold]Variables d'environnement :[/bold]

  ANTHROPIC_API_KEY   Clé API pour l'enrichissement LLM
""",
        title="[bold blue]mcp-forge[/bold blue] — Informations",
        border_style="blue",
    ))


@app.command()
def evaluate(
    server: Annotated[str, typer.Argument(help="Chemin vers le server.py à évaluer")],
    context: Annotated[Optional[str], typer.Option("--context", "-C", help="Contexte additionnel (source spec, cas d'usage...)")] = None,
    output_json: Annotated[bool, typer.Option("--json", help="Sortie JSON brute (pour CI/CD)")] = False,
    save: Annotated[Optional[str], typer.Option("--save", "-s", metavar="FILE", help="Sauvegarder le rapport JSON")] = None,
    api_key: Annotated[Optional[str], typer.Option("--api-key", help="Clé API Anthropic")] = None,
):
    """Évalue la qualité d'un serveur MCP généré par mcp-forge."""
    from mcp_forge.evaluate import evaluate as _evaluate
    _evaluate(
        server_path=server,
        context=context,
        output_json=output_json,
        api_key=api_key,
        save=save,
    )


if __name__ == "__main__":
    app()
