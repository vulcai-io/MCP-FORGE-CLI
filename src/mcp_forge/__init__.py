"""
mcp-forge — Public Python API

Usage::

    from mcp_forge import generate, run_smoke_test, run_functional_test
    from mcp_forge.models import ForgeConfig, ForgeMode, SourceType, NameStyle

    config = ForgeConfig(
        source="https://petstore3.swagger.io/api/v3/openapi.json",
        mode=ForgeMode.AUTO,
        output="mcp-forge-output",
    )

    generated = generate(config)
    print(f"Server written to: {generated.output_dir}")
    print(f"Tools: {generated.tools_count}")

    result = run_functional_test(generated.output_dir)
    print(result.summary())
"""
from __future__ import annotations

from mcp_forge.models import (
    DiscoveredTool,
    DiscoveryResult,
    ForgeConfig,
    ForgeMode,
    GeneratedServer,
    NameStyle,
    ParameterType,
    SourceType,
    ToolParameter,
)
from mcp_forge.validation.smoke_test import SmokeTestResult, run_smoke_test
from mcp_forge.validation.functional_test import (
    FunctionalTestResult,
    ToolCallResult,
    run_functional_test,
)

try:
    from importlib.metadata import version as _v
    __version__ = _v("vulcai-mcp-forge-cli")
except Exception:
    __version__ = "0.1.0"

__all__ = [
    "generate",
    "ForgeConfig",
    "ForgeMode",
    "SourceType",
    "NameStyle",
    "ParameterType",
    "DiscoveredTool",
    "ToolParameter",
    "DiscoveryResult",
    "GeneratedServer",
    "run_smoke_test",
    "SmokeTestResult",
    "run_functional_test",
    "FunctionalTestResult",
    "ToolCallResult",
]


def generate(
    config: ForgeConfig,
    *,
    enrich: bool = True,
) -> GeneratedServer:
    """
    Generate a MCP server from a source.

    Args:
        config:  ForgeConfig describing the source and output options.
        enrich:  Use LLM to improve tool names/descriptions (requires ANTHROPIC_API_KEY).

    Returns:
        GeneratedServer with output_dir, tools_count and generated file contents.

    Example::

        from mcp_forge import generate
        from mcp_forge.models import ForgeConfig, ForgeMode

        config = ForgeConfig(
            source="https://petstore3.swagger.io/api/v3/openapi.json",
            mode=ForgeMode.AUTO,
            output="mcp-forge-output",
        )
        server = generate(config, enrich=False)
        print(server.output_dir)
    """
    from mcp_forge.discovery import discover
    from mcp_forge.generation.generator import MCPGenerator

    result = discover(config)

    if enrich and not getattr(config, "no_llm", False):
        try:
            from mcp_forge.enrichment.llm import LLMEnricher
            result = LLMEnricher(config).enrich(result)
        except Exception:
            pass

    return MCPGenerator(config).generate(result)
