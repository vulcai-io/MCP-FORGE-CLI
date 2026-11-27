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
            "[red][FAIL] --local is not available in this version of the CLI.[/red]\n"
            "  → Cloud mode     : set FORGE_LICENSE_KEY in your .env\n"
            "  → On-premise mode: deploy the engine with deployment/onpremise/"
        )
        raise SystemExit(1) from None

    # Noms des opérations de la source, avant l'enrichissement (noms MCP vérifiés)
    source_names = [t.name for t in result.tools]
    # Faits de la spec et instructions de l'utilisateur : garde d'origine des
    # défauts (mcp_forge/eval_origin.py), pris avant l'enrichissement
    from mcp_forge.eval_origin import source_facts, user_texts
    facts = source_facts(result.tools, result.source_type)
    texts = user_texts(config.server_instructions, config.tool_instructions)
    if config.use_llm_enrichment:
        from mcp_forge.enrichment.llm import LLMEnricher
        try:
            result = LLMEnricher(config).enrich(result, config)
        except ValueError as e:
            from rich.console import Console
            Console().print(f"[yellow]LLM enrichment skipped: {e}[/yellow]")

    from mcp_forge.generation.generator import MCPGenerator
    generated = MCPGenerator(config).generate(result)

    if generated.success:
        server_code = generated.files.get("server.py", "")
        if server_code and config.no_llm:
            # --no-llm : aucun appel LLM, contrôles mécaniques seulement
            from mcp_forge.evaluate import mechanical_report
            generated = generated.model_copy(
                update={"eval_report": mechanical_report(server_code, source_names=source_names,
                                                         source_facts=facts, user_texts=texts)})
        elif server_code:
            try:
                from mcp_forge.evaluate import coverage_context, evaluate_code
                eval_report = evaluate_code(
                    server_code, context=coverage_context(result.metadata.get("coverage"), server_code),
                    source_names=source_names, source_facts=facts, user_texts=texts,
                )
                generated = generated.model_copy(update={"eval_report": eval_report})
            except Exception:
                pass  # évaluation optionnelle, ne bloque pas la génération

    return generated
