"""Admin CLI for LLM Provider Service model management.

This CLI provides operational tools for:
- Listing available models
- Inspecting model capabilities
- Dry-running API payloads (preview without network calls)
- Testing models with real API calls

Usage:
    pdm run llm-admin list-models --provider openai
    pdm run llm-admin show-capabilities --provider openai \\
        --model gpt-5-mini-2025-08-07
    pdm run llm-admin dry-run-payload --provider openai \\
        --model gpt-5-mini-2025-08-07
    pdm run llm-admin call --provider openai \\
        --model gpt-4o-mini-2024-07-18 --essay-a "A" --essay-b "B"
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import aiohttp
import typer
from rich.console import Console
from rich.table import Table

from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.openai_provider_impl import (
    OpenAIProviderImpl,
)
from services.llm_provider_service.implementations.retry_manager_impl import (
    RetryManagerImpl,
)
from services.llm_provider_service.model_manifest import (
    ProviderName,
    get_model_config,
    list_models,
)

app = typer.Typer(help="LLM Provider Service admin CLI")
console = Console()


@app.command("list-models")
def list_models_cmd(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all available models for a provider."""
    try:
        provider_enum = ProviderName(provider.lower())
    except ValueError:
        console.print(
            f"[red]Invalid provider: {provider}. Valid: {[p.value for p in ProviderName]}[/red]"
        )
        raise typer.Exit(code=1)

    models = list_models(provider_enum)

    if json_output:
        # JSON output
        output = [
            {
                "model_id": m.model_id,
                "display_name": m.display_name,
                "context_window": m.context_window,
                "max_tokens": m.max_tokens,
                "cost_per_1k_input": m.cost_per_1k_input_tokens,
                "cost_per_1k_output": m.cost_per_1k_output_tokens,
                "supports_temperature": m.supports_temperature,
                "supports_top_p": m.supports_top_p,
            }
            for m in models
        ]
        typer.echo(json.dumps(output, indent=2))
    else:
        # Rich table output
        table = Table(title=f"{provider.upper()} Models")
        table.add_column("Model ID", style="cyan")
        table.add_column("Display Name", style="green")
        table.add_column("Context", justify="right")
        table.add_column("Max Out", justify="right")
        table.add_column("Temp", justify="center")
        table.add_column("TopP", justify="center")

        for m in models:
            table.add_row(
                m.model_id,
                m.display_name,
                f"{m.context_window:,}",
                f"{m.max_tokens:,}",
                "✓" if m.supports_temperature else "✗",
                "✓" if m.supports_top_p else "✗",
            )

        console.print(table)
        console.print(f"\n[dim]Total: {len(models)} models[/dim]")


@app.command("show-capabilities")
def show_capabilities_cmd(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name"),
    model: str = typer.Option(..., "--model", "-m", help="Model ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show detailed capabilities for a specific model."""
    try:
        provider_enum = ProviderName(provider.lower())
    except ValueError:
        console.print(
            f"[red]Invalid provider: {provider}. Valid: {[p.value for p in ProviderName]}[/red]"
        )
        raise typer.Exit(code=1)

    try:
        config = get_model_config(provider_enum, model)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)

    if json_output:
        # JSON output
        output = {
            "model_id": config.model_id,
            "display_name": config.display_name,
            "provider": config.provider.value,
            "api_version": config.api_version,
            "structured_output_method": config.structured_output_method.value,
            "parameter_compatibility": {
                "supports_temperature": config.supports_temperature,
                "supports_top_p": config.supports_top_p,
                "supports_frequency_penalty": config.supports_frequency_penalty,
                "supports_presence_penalty": config.supports_presence_penalty,
                "uses_max_completion_tokens": config.uses_max_completion_tokens,
            },
            "capabilities": config.capabilities,
            "performance": {
                "max_tokens": config.max_tokens,
                "context_window": config.context_window,
                "supports_streaming": config.supports_streaming,
            },
            "pricing": {
                "cost_per_1k_input_tokens": config.cost_per_1k_input_tokens,
                "cost_per_1k_output_tokens": config.cost_per_1k_output_tokens,
            },
            "metadata": {
                "release_date": config.release_date.isoformat() if config.release_date else None,
                "is_deprecated": config.is_deprecated,
                "recommended_for": config.recommended_for,
                "notes": config.notes,
            },
        }
        typer.echo(json.dumps(output, indent=2))
    else:
        # Rich formatted output
        console.print(f"\n[bold cyan]{config.display_name}[/bold cyan]")
        console.print(f"[dim]Model ID:[/dim] {config.model_id}")
        console.print(f"[dim]Provider:[/dim] {config.provider.value}")

        console.print("\n[bold]Parameter Compatibility:[/bold]")
        temp_status = "✓" if config.supports_temperature else "✗"
        console.print(f"  Temperature:       {temp_status}")
        top_p_status = "✓" if config.supports_top_p else "✗"
        console.print(f"  Top-P:             {top_p_status}")
        freq_status = "✓" if config.supports_frequency_penalty else "✗"
        console.print(f"  Frequency Penalty: {freq_status}")
        pres_status = "✓" if config.supports_presence_penalty else "✗"
        console.print(f"  Presence Penalty:  {pres_status}")
        token_param = "max_completion_tokens" if config.uses_max_completion_tokens else "max_tokens"
        console.print(f"  Token Parameter:   {token_param}")

        console.print("\n[bold]Capabilities:[/bold]")
        for cap, supported in config.capabilities.items():
            console.print(f"  {cap}: {'✓' if supported else '✗'}")

        console.print("\n[bold]Performance:[/bold]")
        console.print(f"  Context Window: {config.context_window:,} tokens")
        console.print(f"  Max Output:     {config.max_tokens:,} tokens")
        console.print(f"  Streaming:      {'✓' if config.supports_streaming else '✗'}")

        if config.cost_per_1k_input_tokens is not None:
            console.print("\n[bold]Pricing:[/bold]")
            console.print(f"  Input:  ${config.cost_per_1k_input_tokens:.5f} per 1K tokens")
            console.print(f"  Output: ${config.cost_per_1k_output_tokens:.5f} per 1K tokens")

        if config.notes:
            console.print(f"\n[bold]Notes:[/bold]\n  {config.notes}")


@app.command("dry-run-payload")
def dry_run_payload_cmd(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name"),
    model: str = typer.Option(..., "--model", "-m", help="Model ID"),
    temperature: float = typer.Option(0.7, "--temperature", "-t", help="Temperature parameter"),
    max_tokens: int = typer.Option(512, "--max-tokens", help="Max tokens"),
) -> None:
    """Dry-run: Preview API payload without making network call."""
    try:
        provider_enum = ProviderName(provider.lower())
    except ValueError:
        console.print(
            f"[red]Invalid provider: {provider}. Valid: {[p.value for p in ProviderName]}[/red]"
        )
        raise typer.Exit(code=1)

    try:
        config = get_model_config(provider_enum, model)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)

    # Build payload as provider would
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "[SYSTEM_PROMPT]"},
            {"role": "user", "content": "[USER_PROMPT]"},
        ],
    }

    # Add parameters conditionally based on model capabilities
    omitted_params = []

    if config.uses_max_completion_tokens:
        payload["max_completion_tokens"] = max_tokens
    else:
        payload["max_tokens"] = max_tokens

    if config.supports_temperature:
        payload["temperature"] = temperature
    else:
        omitted_params.append(f"temperature ({temperature})")

    if not config.supports_top_p:
        omitted_params.append("top_p (if specified)")

    # Display payload
    console.print("\n[bold cyan]API Payload Preview:[/bold cyan]")
    console.print(json.dumps(payload, indent=2))

    if omitted_params:
        console.print("\n[bold yellow]⚠ Parameters Omitted (model does not support):[/bold yellow]")
        for param in omitted_params:
            console.print(f"  • {param}")

    # Show recommendations
    console.print("\n[bold green]✓ Payload Recommendations:[/bold green]")
    if not config.supports_temperature:
        console.print("  • Model does NOT support temperature - using default value (1.0)")
    if config.uses_max_completion_tokens:
        console.print("  • Model uses 'max_completion_tokens' instead of 'max_tokens'")
    console.print(f"  • Structured output method: {config.structured_output_method.value}")


@app.command("call")
def call_cmd(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name"),
    model: str = typer.Option(..., "--model", "-m", help="Model ID"),
    essay_a: str = typer.Option("Sample essay A", "--essay-a", help="Essay A text"),
    essay_b: str = typer.Option("Sample essay B", "--essay-b", help="Essay B text"),
    temperature: float = typer.Option(0.7, "--temperature", "-t", help="Temperature"),
    max_tokens: int = typer.Option(512, "--max-tokens", help="Max tokens"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Make a real API call to test the model (requires API keys)."""
    try:
        provider_enum = ProviderName(provider.lower())
    except ValueError:
        console.print(
            f"[red]Invalid provider: {provider}. Valid: {[p.value for p in ProviderName]}[/red]"
        )
        raise typer.Exit(code=1)

    if provider_enum != ProviderName.OPENAI:
        console.print("[red]Currently only OpenAI provider is supported for 'call' command[/red]")
        raise typer.Exit(code=1)

    # Run async call
    import asyncio

    asyncio.run(_call_openai(model, essay_a, essay_b, temperature, max_tokens, json_output))


async def _call_openai(
    model: str,
    essay_a: str,
    essay_b: str,
    temperature: float,
    max_tokens: int,
    json_output: bool,
) -> None:
    """Execute OpenAI API call asynchronously."""
    settings = Settings()

    if not settings.OPENAI_API_KEY:
        console.print("[red]OPENAI_API_KEY environment variable not set[/red]")
        raise typer.Exit(code=1)

    async with aiohttp.ClientSession() as session:
        retry_manager = RetryManagerImpl(settings)
        provider = OpenAIProviderImpl(session, settings, retry_manager)

        system_prompt = "Compare the following two essays and determine which is better."
        user_prompt = f"Essay A: {essay_a}\n\nEssay B: {essay_b}"

        try:
            response = await provider._make_api_request(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                correlation_id=uuid.uuid4(),
                model_override=model,
                temperature_override=temperature,
                max_tokens_override=max_tokens,
            )

            if json_output:
                output = {
                    "model": response.model,
                    "response_text": response.justification,
                    "input_tokens": response.prompt_tokens,
                    "output_tokens": response.completion_tokens,
                    "provider": response.provider.value,
                }
                typer.echo(json.dumps(output, indent=2))
            else:
                console.print("\n[bold green]✓ API Call Successful[/bold green]")
                console.print(f"[dim]Model:[/dim] {response.model}")
                console.print(f"[dim]Provider:[/dim] {response.provider.value}")
                console.print(f"[dim]Input Tokens:[/dim] {response.prompt_tokens}")
                console.print(f"[dim]Output Tokens:[/dim] {response.completion_tokens}")
                console.print(f"\n[bold]Response:[/bold]\n{response.justification}")

        except Exception as e:
            console.print("\n[bold red]✗ API Call Failed[/bold red]")
            console.print(f"[red]Error: {str(e)}[/red]")
            raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
