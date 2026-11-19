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
from typing import Annotated

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
from rich.markup import escape
from rich.panel import Panel

from mcp_forge.config_loader import load_yaml_config
from mcp_forge.discovery.limits import parse_list
from mcp_forge.instructions import (
    MAX_SERVER_INSTRUCTIONS,
    clean_instructions,
    clean_tool_instructions,
    parse_tool_instruction_options,
)
from mcp_forge.models import ForgeConfig, ForgeMode, NameStyle, SourceType


def _version_callback(value: bool) -> None:
    if value:
        from mcp_forge import __version__
        typer.echo(f"mcp-forge {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="mcp-forge",
    help="Generates an MCP server from an API, a website, a CLI application or a codebase.",
    add_completion=False,
    rich_markup_mode="rich",
    # Jamais les variables locales dans la trace d'une exception : elles portent les clés
    # (--api-key, FORGE_LICENSE_KEY, set-license) et les en-têtes (--header). Typer < 0.23 les
    # affichait par défaut (constat du 2026-11-17, tests/test_cli_secrets_in_tracebacks.py)
    pretty_exceptions_show_locals=False,
)
console = Console()


@app.callback()
def _main(
    version: Annotated[bool | None, typer.Option(
        "--version", "-V", callback=_version_callback, is_eager=True, help="Show the version and exit"
    )] = None,
) -> None:
    # Typer callback — gestion de --version uniquement, aucune logique supplémentaire.
    pass


def _detect_source_type(source: str) -> SourceType:
    """Détecte automatiquement le type de source."""
    s = source.lower()
    if s.endswith((".json", ".yaml", ".yml")):
        return SourceType.OPENAPI
    if "graphql" in s or s.endswith("/graphql") or s.endswith((".gql", ".graphqls", ".sdl")):
        return SourceType.GRAPHQL
    if s.startswith("http://") or s.startswith("https://"):
        return SourceType.WEBSITE
    if Path(source).is_dir():
        return SourceType.CODEBASE
    return SourceType.CLI_APP


@app.command()
def run(
    source: Annotated[str | None, typer.Argument(help="URL, OpenAPI file, CLI command or code folder")] = None,
    mode: Annotated[ForgeMode | None, typer.Option("--mode", "-m", help="Generation mode")] = None,
    output: Annotated[str | None, typer.Option("--output", "-o", help="Output folder")] = None,
    source_type: Annotated[SourceType | None, typer.Option("--type", "-t", help="Force the source type")] = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Name of the generated MCP server")] = None,
    no_llm: Annotated[bool | None, typer.Option("--no-llm", help="No LLM call: neither enrichment nor evaluation (mechanical checks only), locally and through the API")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="Anthropic API key (or ANTHROPIC_API_KEY)")] = None,
    name_style: Annotated[NameStyle | None, typer.Option("--name-style", "-ns", help="Naming style: short or exhaustive")] = None,
    config_file: Annotated[str | None, typer.Option("--config", "-c", help="YAML configuration file (default: mcp-forge.yaml if present)")] = None,
    smoke_test: Annotated[bool, typer.Option("--smoke-test", help="Run the smoke test after generation")] = False,
    functional_test: Annotated[bool, typer.Option("--functional-test", help="Run the MCP functional test after generation (starts the server)")] = False,
    local: Annotated[bool, typer.Option("--local", help="Force the local pipeline (no call to the Vulcai API)")] = False,
    lang: Annotated[str, typer.Option("--lang", help="Language of the generated comments: en (default) or fr")] = "en",
    bundle_source: Annotated[bool, typer.Option("--bundle-source", help="Copy the source code (codebase) into the generated server; off by default, your code does not leave the machine")] = False,
    eval_provider: Annotated[str | None, typer.Option("--eval-provider", help="Evaluation provider to use (e.g. a different one from generation): anthropic, groq, openai, mistral, local")] = None,
    eval_model: Annotated[str | None, typer.Option("--eval-model", help="Evaluation model to use")] = None,
    no_wait: Annotated[bool, typer.Option("--no-wait", help="Remote pipeline: write the provisional version without waiting for the evaluation (get the final one with \"mcp-forge status\")")] = False,
    instructions: Annotated[str | None, typer.Option("--instructions", help="Instructions for the client LLM, for the whole server (sent at MCP initialization)")] = None,
    tool_instruction: Annotated[list[str] | None, typer.Option("--tool-instruction", help="Instruction for one tool: NAME=TEXT (MCP tool name, repeatable)")] = None,
    include_tags: Annotated[list[str] | None, typer.Option("--include-tags", help="OpenAPI: generate only the operations with these tags (comma-separated list)")] = None,
    exclude_tags: Annotated[list[str] | None, typer.Option("--exclude-tags", help="OpenAPI: skip the operations with these tags")] = None,
    include_paths: Annotated[list[str] | None, typer.Option("--include-paths", help="OpenAPI: generate only the paths that start with these prefixes (e.g. /repos)")] = None,
    exclude_paths: Annotated[list[str] | None, typer.Option("--exclude-paths", help="OpenAPI: skip the paths that start with these prefixes")] = None,
    no_output_schema: Annotated[bool, typer.Option("--no-output-schema", help="No outputSchema in the generated tools: a shorter tool list for the client LLM")] = False,
    header: Annotated[list[str] | None, typer.Option("--header", "-H", help="GraphQL: HTTP header for introspection, \"Name: value\" (repeatable). Its value is never written to the generated server nor sent to the API; the server reads it from an environment variable")] = None,
):
    """
    Generates an MCP server from a [bold]source[/bold].

    Examples:
      mcp-forge run https://api.example.com/openapi.json
      mcp-forge run https://example.com --mode semi
      mcp-forge run my-cli-app --mode guided
    """
    # Mode auto (0.4.1) : stdout ne porte que la ligne JSON du résultat,
    # tout l'affichage part sur stderr (mcp_forge/ui/json_stdout.py).
    from mcp_forge.ui.json_stdout import json_only_stdout
    with json_only_stdout(_is_auto(mode, config_file)):
        console.print(Panel.fit(
            "[bold blue]mcp-forge[/bold blue] — MCP server generator",
            border_style="blue",
        ))

        yaml_cfg = _load_yaml(config_file)
        source, mode, output, source_type, name, no_llm, name_style, smoke_test, functional_test = \
            _merge_options(yaml_cfg, source, mode, output, source_type, name, no_llm,
                           name_style, smoke_test, functional_test)

        explicit_no_llm = no_llm  # avant _build_config, qui le force aussi faute de clé locale
        bundle_source = bundle_source or yaml_cfg.get("bundle_source", False)
        # Évaluateur imposé : transmis au pipeline (local.py → evaluate_code)
        # par les variables d'environnement lues dans mcp_forge/evaluate.py.
        if eval_provider:
            os.environ["MCP_FORGE_EVAL_PROVIDER"] = eval_provider
        if eval_model:
            os.environ["MCP_FORGE_EVAL_MODEL"] = eval_model
        config, no_llm = _build_config(yaml_cfg, source, mode, output, source_type, name,
                                       no_llm, name_style, api_key, force_local=local, lang=lang,
                                       bundle_source=bundle_source)
        config.wait_for_eval = not no_wait
        config.no_llm = bool(explicit_no_llm)
        _apply_instructions(config, yaml_cfg, instructions, tool_instruction)
        _apply_selection(config, yaml_cfg, include_tags, exclude_tags, include_paths, exclude_paths, no_output_schema)
        _apply_headers(config, header)

        _print_summary(source, config.source_type, mode, output, no_llm, name_style, force_local=local,
                       explicit_no_llm=config.no_llm)

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


def _is_auto(mode: ForgeMode | None, config_file: str | None) -> bool:
    """Mode effectif avant toute autre lecture : l'option, sinon la clé
    `mode` du YAML, sinon auto (un YAML illisible garde le défaut, auto ;
    l'erreur est signalée ensuite par _load_yaml)."""
    if mode is not None:
        return mode == ForgeMode.AUTO
    try:
        return load_yaml_config(config_file).get("mode", ForgeMode.AUTO.value) == ForgeMode.AUTO.value
    except Exception:  # noqa: BLE001 — l'erreur réelle est affichée par _load_yaml
        return True


def _load_yaml(config_file: str | None) -> dict:
    try:
        return load_yaml_config(config_file)
    except FileNotFoundError as e:
        console.print(f"[red][FAIL] {e}[/red]")
        raise typer.Exit(1) from None


def _merge_options(
    yaml_cfg: dict,
    source: str | None,
    mode: ForgeMode | None,
    output: str | None,
    source_type: SourceType | None,
    name: str | None,
    no_llm: bool | None,
    name_style: NameStyle | None,
    smoke_test: bool,
    functional_test: bool,
) -> tuple:
    source = source or yaml_cfg.get("source")
    if not source:
        console.print("[red][FAIL] Source required (argument or 'source' field in mcp-forge.yaml)[/red]")
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
    source_type: SourceType | None,
    name: str | None,
    no_llm: bool,
    name_style: NameStyle,
    api_key: str | None,
    force_local: bool = False,
    lang: str = "en",
    bundle_source: bool = False,
) -> tuple:
    resolved_type = source_type or _detect_source_type(source)
    resolved_key = api_key or yaml_cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")

    if not no_llm and not resolved_key and not os.environ.get("GROQ_API_KEY"):
        # Avertissement réservé au pipeline local : en mode distant, c'est
        # l'API qui enrichit, avec ses propres clés (message affiché à tort
        # à tous les utilisateurs distants jusqu'à la 0.4.0).
        if _is_local_mode(force_local):
            console.print(
                "[yellow]⚠ No API key found.[/yellow] "
                "LLM enrichment is turned off. "
                "Set ANTHROPIC_API_KEY or GROQ_API_KEY in your .env."
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


def _apply_instructions(
    config: ForgeConfig,
    yaml_cfg: dict,
    instructions: str | None,
    tool_instruction: list[str] | None,
) -> None:
    """Instructions personnalisées (lot D, D4) : options de la CLI, sinon
    clés `instructions` et `tool_instructions` de mcp-forge.yaml. Les
    options --tool-instruction complètent celles du YAML (même nom :
    l'option l'emporte)."""
    try:
        server = instructions if instructions is not None else yaml_cfg.get("instructions")
        if server:
            config.server_instructions = clean_instructions(server, MAX_SERVER_INSTRUCTIONS, "instructions") or None
        per_tool = dict(yaml_cfg.get("tool_instructions") or {})
        per_tool.update(parse_tool_instruction_options(tool_instruction))
        config.tool_instructions = clean_tool_instructions(per_tool)
    except ValueError as e:
        console.print(f"[red][FAIL] {e}[/red]")
        raise typer.Exit(1) from None


def parse_header_options(values: list[str] | None) -> dict[str, str]:
    """--header "Name: value" (lot B des parseurs, 2026-11-17) → {Name: value}."""
    headers: dict[str, str] = {}
    for raw in values or []:
        name, sep, value = raw.partition(":")
        name = name.strip()
        if not sep or not name or any(c.isspace() for c in name) or any(c in value for c in "\r\n"):
            raise ValueError(f'Invalid --header "{name or raw[:40]}": expected "Name: value"')
        headers[name] = value.strip()
    return headers


def _apply_headers(config: ForgeConfig, header: list[str] | None) -> None:
    try:
        config.extra_headers.update(parse_header_options(header))
    except ValueError as e:
        console.print(f"[red][FAIL] {e}[/red]")
        raise typer.Exit(1) from None


def _apply_selection(
    config: ForgeConfig,
    yaml_cfg: dict,
    include_tags: list[str] | None,
    exclude_tags: list[str] | None,
    include_paths: list[str] | None,
    exclude_paths: list[str] | None,
    no_output_schema: bool,
) -> None:
    """Filtre des opérations OpenAPI et --no-output-schema : options de la
    CLI, sinon mêmes clés dans mcp-forge.yaml (voir
    mcp_forge/discovery/limits.py)."""
    for name, value in (("include_tags", include_tags), ("exclude_tags", exclude_tags),
                        ("include_paths", include_paths), ("exclude_paths", exclude_paths)):
        setattr(config, name, parse_list(value if value else yaml_cfg.get(name)))
    config.no_output_schema = bool(no_output_schema or yaml_cfg.get("no_output_schema", False))


def _is_local_mode(force_local: bool) -> bool:
    """Même règle que mcp_forge.pipeline.selector : --local ou FORGE_MODE=local."""
    return force_local or os.environ.get("FORGE_MODE", "").lower() == "local"


def _print_summary(
    source: str, resolved_type: SourceType, mode: ForgeMode,
    output: str, no_llm: bool, name_style: NameStyle, force_local: bool = False,
    explicit_no_llm: bool = False,
) -> None:
    console.print(f"[dim]Source     :[/dim] {source}")
    console.print(f"[dim]Type       :[/dim] {resolved_type.value}")
    console.print(f"[dim]Mode       :[/dim] {mode.value}")
    console.print(f"[dim]Output     :[/dim] {output}")
    if explicit_no_llm:
        console.print("[dim]LLM        :[/dim] off (--no-llm): no LLM enrichment or evaluation")
    elif not _is_local_mode(force_local):
        console.print("[dim]Enrichment :[/dim] LLM, by the mcp-forge API")
    else:
        console.print(f"[dim]Enrichment :[/dim] {'LLM (Claude)' if not no_llm else 'off'}")
    if not no_llm:
        console.print(f"[dim]Naming     :[/dim] {name_style.value}")
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
    server: Annotated[str, typer.Argument(help="Path to server.py (backslashes accepted)")],
):
    """
    Opens MCP Inspector on a generated server.

    Accepts Windows paths (backslashes) pasted from File Explorer.

    Examples:
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
        console.print(f"[red][FAIL] File not found:[/red] {normalized}")
        raise typer.Exit(1)
    server_dir = server_path.resolve().parent
    console.print(f"[dim]Starting MCP Inspector on:[/dim] {server_dir / 'server.py'}")
    # Les dépendances du serveur sont installées par uv dans un environnement
    # éphémère (--with-requirements), plus dans celui de la CLI.
    command = _inspector_command(server_dir)
    if command is None:
        console.print("[red][FAIL] npx not found:[/red] install Node.js (https://nodejs.org) to run MCP Inspector.")
        raise typer.Exit(1)
    result = subprocess.run(command, cwd=str(server_dir), env=_inspector_env())
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


def _inspector_env() -> dict[str, str]:
    """Environnement d'Inspector, donc du serveur qu'il lance via uv.

    Sans PYTHONHOME : sous Windows, le Python géré par uv de la CLI le définit
    pour lui-même ; hérité par le Python de l'environnement éphémère du
    serveur, il lui masquait ses paquets et le serveur se fermait aussitôt
    (Inspector : « Connection closed »)."""
    return {k: v for k, v in os.environ.items() if k.upper() != "PYTHONHOME"}


# Version de MCP Inspector fixée : celle validée sur Windows, Linux et macOS
# (workflow « CLI · test multi-plateforme »). Sans version, npx prendrait la
# dernière publiée (2.12.0 le 2026-10-27), non testée avec mcp-forge.
INSPECTOR_VERSION = "1.0.3"


def _inspector_command(server_dir: Path | None = None) -> list[str] | None:
    """Commande MCP Inspector (npx + uv), ou None si npx est introuvable.

    Transport stdio via `mcp run server.py`, qui démarre l'objet FastMCP du
    serveur. `python server.py` démarre le serveur HTTP (uvicorn) des
    serveurs générés : Inspector, en stdio, n'obtenait aucune réponse.

    Le serveur tourne avec SES dépendances : `--with-requirements
    requirements.txt` quand le fichier existe (tout serveur généré fixe
    `mcp~=1.x`). Un simple `--with mcp` prenait la dernière version publiée,
    mcp 2.x depuis 2026-10, où `mcp.server.fastmcp` n'existe plus. `mcp[cli]`
    ajoute la commande `mcp run` ; uv l'aligne sur la version fixée.

    npx est résolu en chemin complet et lancé sans shell. Sous Windows, on
    cherche explicitement `npx.cmd` : Node.js installe aussi un script `npx`
    sans extension (pour les shells POSIX) que `shutil.which("npx")` peut
    renvoyer et que Windows ne sait pas exécuter (WinError 193). Auparavant
    `shell=True` avec une liste : sous Linux et macOS, le shell ne recevait
    que « npx », sans aucun argument, et Inspector ne démarrait pas."""
    import shutil
    npx = shutil.which("npx.cmd" if sys.platform == "win32" else "npx")
    if npx is None:
        return None
    deps = ["--with", "mcp[cli]"]
    if server_dir is not None and (server_dir / "requirements.txt").is_file():
        deps = ["--with-requirements", "requirements.txt", *deps]
    return [npx, "-y", f"@modelcontextprotocol/inspector@{INSPECTOR_VERSION}",
            "uv", "run", "--no-project", *deps, "mcp", "run", "server.py"]


@app.command(name="smoke-test")
def smoke_test_cmd(
    server_dir: Annotated[str, typer.Argument(help="Folder of the generated MCP server (contains server.py)")],
):
    """
    Checks that a generated MCP server is valid, without starting it.

    Checks:
      • server.py present
      • valid Python syntax
      • imports without error (isolated subprocess)
      • mcp object present
      • at least 1 @mcp.tool registered
      • consistent with the VERSION file

    Examples:
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
        console.print(f"[red][FAIL] Folder not found:[/red] {normalized}")
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
        console.print("\n[red bold]Smoke test FAILED[/red bold]")
        raise typer.Exit(1)


@app.command(name="functional-test")
def functional_test_cmd(
    server_dir: Annotated[str, typer.Argument(help="Folder of the MCP server (contains server.py)")],
    timeout: Annotated[float, typer.Option("--timeout", "-t", help="Maximum time per step, in seconds")] = 15.0,
):
    """
    Functional test: starts the MCP server and checks its tools over the MCP protocol.

    Unlike smoke-test (a Python import), this test really starts the server and talks
    to it over JSON-RPC / stdio, like a real MCP client.

    Checks:
      • the server starts without error
      • MCP handshake (initialize) succeeds
      • tools/list returns at least 1 tool
      • the number of tools matches the VERSION file
      • consistent with the @mcp.tool functions of the source

    Examples:
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
    console.print("\n[bold]Phase 2 -- Tool calls:[/bold]")
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
        console.print(f"[red]Folder not found:[/red] {normalized}")
        raise typer.Exit(1)

    console.print(f"\n[bold]>> MCP functional test:[/bold] {path}")
    console.print("[dim]  Starting the server...[/dim]")
    result = run_functional_test(path, timeout=timeout)

    _print_ft_phase1(result)
    _print_ft_phase2(result)

    if result.success:
        console.print(f"\n[green bold]Functional test OK[/green bold] ({len(result.tools_listed)} tool(s))")
    else:
        console.print("\n[red bold]Functional test FAILED[/red bold]")
        raise typer.Exit(1)


@app.command(name="list")
def list_servers(
    output: Annotated[str | None, typer.Option("--output", "-o", help="Output folder to inspect")] = None,
):
    """
    Lists the MCP servers generated in the output folder.

    For each server: name, generation date, source, number of tools.
    """
    from rich.table import Table

    output_dir = Path(output or _DEFAULT_OUTPUT)
    if not output_dir.exists():
        console.print(f"[yellow]Folder not found:[/yellow] {output_dir}")
        raise typer.Exit(0)

    servers = sorted(
        [d for d in output_dir.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )

    if not servers:
        console.print(f"[dim]No server in {output_dir}[/dim]")
        raise typer.Exit(0)

    table = Table(title=f"MCP servers in {output_dir}", show_lines=False)
    table.add_column("Name", style="bold cyan", no_wrap=True)
    table.add_column("Tools", justify="right")
    table.add_column("Generated", style="dim")
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


@app.command()
def status(
    generation_id: Annotated[str, typer.Argument(help="Generation ID (shown by \"run --no-wait\")")],
    output: Annotated[str | None, typer.Option("--output", "-o", help="Folder where the final version is written")] = None,
    no_wait: Annotated[bool, typer.Option("--no-wait", help="Show the status without waiting for the evaluation to finish")] = False,
):
    """
    Status of the evaluation of a remote generation. Waits for the final
    version and, with --output, writes it to that folder.
    """
    from mcp_forge.pipeline.remote import (
        _DEFAULT_API_URL,
        RemoteError,
        _download_bundle,
        _print_evaluation,
        get_evaluation,
        wait_for_evaluation,
    )
    license_key = os.environ.get("FORGE_LICENSE_KEY", "")
    if not license_key:
        console.print("[red][FAIL] FORGE_LICENSE_KEY missing (mcp-forge set-license mfg_live_...)[/red]")
        raise typer.Exit(1)
    api_url = os.environ.get("FORGE_API_URL", _DEFAULT_API_URL).rstrip("/")
    url = f"{api_url}/v1/generations/{generation_id}/evaluation"
    try:
        view = get_evaluation(url, license_key) if no_wait else wait_for_evaluation(url, license_key)
        if view.get("status") in ("queued", "running"):
            console.print(f"Evaluation {view['status']}: provisional version.")
            return
        _print_evaluation(view)
        if output:
            _download_bundle(view["bundle_url"], license_key, Path(output))
            console.print(f"[green][OK] Final version written to: {output}[/green]")
    except RemoteError as exc:
        console.print(f"[red][FAIL] {escape(str(exc))}[/red]")
        raise typer.Exit(1) from None


@app.command(name="set-license")
def set_license(
    key: Annotated[str, typer.Argument(help="License key (format: mfg_live_... or mfg_test_...)")],
):
    """
    Saves the license key to the .env file of the current folder.

    Example:
      mcp-forge set-license mfg_live_abc123...
    """
    env_path = Path.cwd() / ".env"
    lines: list[str] = []

    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        lines = [line for line in lines if not line.startswith("FORGE_LICENSE_KEY=")]

    lines.append(f"FORGE_LICENSE_KEY={key}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"[green][OK] License key saved to {env_path}[/green]")
    console.print("[dim]It is used automatically by every mcp-forge run.[/dim]")


@app.command()
def info():
    """Shows information about mcp-forge and the supported source types."""
    rprint(Panel(
        """[bold]Supported sources:[/bold]

  [green]openapi[/green]   OpenAPI/Swagger file or URL (.json, .yaml)
  [green]website[/green]   Website or REST API (http/https URL)
  [green]graphql[/green]   GraphQL API (URL with /graphql, or .graphql schema file)
  [green]cli_app[/green]   Local CLI application
  [green]codebase[/green]  Source code folder

[bold]Modes:[/bold]

  [blue]auto[/blue]     Fully automatic generation
  [blue]semi[/blue]     Pauses to review the tools and the generated code
  [blue]guided[/blue]   Step by step, with interactive choices

[bold]Environment variables:[/bold]

  FORGE_LICENSE_KEY   License key (mcp-forge set-license)
  ANTHROPIC_API_KEY   API key for LLM enrichment (local pipeline)
""",
        title="[bold blue]mcp-forge[/bold blue] — Information",
        border_style="blue",
    ))


@app.command()
def evaluate(
    server: Annotated[str, typer.Argument(help="Path to the server.py to evaluate")],
    context: Annotated[str | None, typer.Option("--context", "-C", help="Additional context (source spec, use cases...)")] = None,
    output_json: Annotated[bool, typer.Option("--json", help="Raw JSON output (for CI/CD)")] = False,
    save: Annotated[str | None, typer.Option("--save", "-s", metavar="FILE", help="Save the JSON report")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="Anthropic API key")] = None,
    eval_provider: Annotated[str | None, typer.Option("--eval-provider", help="Evaluation provider to use: anthropic, groq, openai, mistral, local")] = None,
    eval_model: Annotated[str | None, typer.Option("--eval-model", help="Evaluation model to use")] = None,
):
    """Evaluates the quality of an MCP server generated by mcp-forge."""
    from mcp_forge.evaluate import evaluate as _evaluate
    from mcp_forge.ui.json_stdout import json_only_stdout
    with json_only_stdout(output_json):  # --json : la ligne JSON seule sur stdout (0.4.1)
        _evaluate(
            server_path=server,
            context=context,
            output_json=output_json,
            api_key=api_key,
            save=save,
            provider=eval_provider,
            model=eval_model,
        )


if __name__ == "__main__":
    app()
