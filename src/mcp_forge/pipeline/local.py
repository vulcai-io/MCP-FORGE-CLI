"""
Pipeline local : enrichissement LLM + génération sur la machine du client.

Disponible uniquement avec le moteur complet (on-premise ou développement).
Dans le CLI distribué, ce module lève une erreur claire si les modules
enrichment/generation ne sont pas installés.
"""
from __future__ import annotations

from mcp_forge.models import DiscoveryResult, ForgeConfig, GeneratedServer


def run_local(result: DiscoveryResult, config: ForgeConfig) -> GeneratedServer:
    """Enrichissement LLM local + génération. Nécessite le moteur complet."""
    try:
        from mcp_forge.generation.generator import MCPGenerator  # noqa: F401
    except ImportError:
        from rich.console import Console
        Console().print(
            "[red][FAIL] Le mode --local n'est pas disponible dans cette version du CLI.[/red]\n"
            "  → Mode cloud     : définissez FORGE_LICENSE_KEY dans votre .env\n"
            "  → Mode on-premise: déployez le moteur via deployment/onpremise/"
        )
        raise SystemExit(1)

    if config.use_llm_enrichment:
        from mcp_forge.enrichment.llm import LLMEnricher
        try:
            result = LLMEnricher(config).enrich(result, config)
        except ValueError as e:
            from rich.console import Console
            Console().print(f"[yellow]Enrichissement LLM ignore : {e}[/yellow]")

    from mcp_forge.generation.generator import MCPGenerator
    generated = MCPGenerator(config).generate(result)

    if generated.success:
        server_code = generated.files.get("server.py", "")
        if server_code:
            try:
                from mcp_forge.evaluate import evaluate_code
                eval_report = evaluate_code(server_code)
                generated = generated.model_copy(update={"eval_report": eval_report})
            except Exception:
                pass  # évaluation optionnelle, ne bloque pas la génération

    return generated