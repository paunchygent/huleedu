"""CLI tool for checking LLM provider model versions against the manifest.

This module provides a command-line interface for discovering available models
from LLM provider APIs and comparing them with the centralized model manifest.

Usage:
    # Check all providers
    pdm run llm-check-models --provider all

    # Check specific provider
    pdm run llm-check-models --provider anthropic --verbose

    # Check with detailed output
    pdm run llm-check-models --provider openai --verbose

Exit Codes:
    0: All up-to-date (no changes needed)
    1: New models available (non-breaking)
    2: API error or authentication failure
    3: Breaking changes detected (requires manifest update)
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

import aiohttp
import typer
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from services.llm_provider_service.cli_output_formatter import (
    console,
    format_breaking_changes,
    format_comparison_table,
    format_summary,
)
from services.llm_provider_service.config import Settings
from services.llm_provider_service.model_checker.anthropic_checker import (
    AnthropicModelChecker,
)
from services.llm_provider_service.model_checker.base import (
    ModelCheckerProtocol,
    ModelComparisonResult,
)
from services.llm_provider_service.model_checker.google_checker import GoogleModelChecker
from services.llm_provider_service.model_checker.openai_checker import OpenAIModelChecker
from services.llm_provider_service.model_checker.openrouter_checker import (
    OpenRouterModelChecker,
)
from services.llm_provider_service.model_manifest import ProviderName

APP = typer.Typer(help="Check LLM provider model versions against manifest")
logger = logging.getLogger(__name__)


class ProviderChoice(str, Enum):
    """Available provider options for CLI."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    ALL = "all"


class ExitCode(int, Enum):
    """CLI exit codes."""

    UP_TO_DATE = 0
    NEW_MODELS_AVAILABLE = 1
    API_ERROR = 2
    BREAKING_CHANGES = 3


class CheckerFactory:
    """Factory for creating provider-specific model checkers."""

    def __init__(self, settings: Settings, logger: logging.Logger):
        """Initialize the factory with settings and logger.

        Args:
            settings: Service configuration settings
            logger: Structured logger instance
        """
        self.settings = settings
        self.logger = logger

    async def create_checker(self, provider: ProviderName) -> ModelCheckerProtocol | None:
        """Create a checker for the specified provider.

        Args:
            provider: Provider to create checker for

        Returns:
            ModelCheckerProtocol implementation or None if provider disabled

        Raises:
            ValueError: If API key is missing for the provider
        """
        if provider == ProviderName.ANTHROPIC:
            return await self._create_anthropic_checker()
        elif provider == ProviderName.OPENAI:
            return await self._create_openai_checker()
        elif provider == ProviderName.GOOGLE:
            return await self._create_google_checker()
        elif provider == ProviderName.OPENROUTER:
            return await self._create_openrouter_checker()
        else:
            self.logger.warning(
                f"Unsupported provider: {provider}",
                extra={"provider": provider.value},
            )
            return None

    async def _create_anthropic_checker(self) -> AnthropicModelChecker | None:
        """Create Anthropic model checker."""
        api_key = self.settings.ANTHROPIC_API_KEY.get_secret_value()
        if not api_key:
            console.print(
                "[yellow]⚠️  Anthropic API key not found. "
                "Set ANTHROPIC_API_KEY environment variable.[/yellow]"
            )
            return None

        client = AsyncAnthropic(api_key=api_key)
        return AnthropicModelChecker(client=client, logger=self.logger)

    async def _create_openai_checker(self) -> OpenAIModelChecker | None:
        """Create OpenAI model checker."""
        api_key = self.settings.OPENAI_API_KEY.get_secret_value()
        if not api_key:
            console.print(
                "[yellow]⚠️  OpenAI API key not found. "
                "Set OPENAI_API_KEY environment variable.[/yellow]"
            )
            return None

        client = AsyncOpenAI(api_key=api_key)
        return OpenAIModelChecker(client=client, logger=self.logger)

    async def _create_google_checker(self) -> GoogleModelChecker | None:
        """Create Google model checker."""
        api_key = self.settings.GOOGLE_API_KEY.get_secret_value()
        if not api_key:
            console.print(
                "[yellow]⚠️  Google API key not found. "
                "Set GOOGLE_API_KEY environment variable.[/yellow]"
            )
            return None

        # Import at runtime to avoid type-checking issues
        from google import genai  # type: ignore[import-untyped,attr-defined]

        client = genai.Client(api_key=api_key)  # type: ignore[attr-defined]
        return GoogleModelChecker(client=client, logger=self.logger)

    async def _create_openrouter_checker(self) -> OpenRouterModelChecker | None:
        """Create OpenRouter model checker."""
        api_key = self.settings.OPENROUTER_API_KEY.get_secret_value()
        if not api_key:
            console.print(
                "[yellow]⚠️  OpenRouter API key not found. "
                "Set OPENROUTER_API_KEY environment variable.[/yellow]"
            )
            return None

        session = aiohttp.ClientSession()
        return OpenRouterModelChecker(session=session, api_key=api_key, logger=self.logger)


def determine_exit_code(results: list[ModelComparisonResult]) -> ExitCode:
    """Determine appropriate exit code based on results.

    Args:
        results: List of comparison results

    Returns:
        Exit code enum value
    """
    has_breaking = any(len(r.breaking_changes) > 0 for r in results)
    if has_breaking:
        return ExitCode.BREAKING_CHANGES

    has_new = any(len(r.new_models) > 0 for r in results)
    has_updates = any(len(r.updated_models) > 0 for r in results)

    if has_new or has_updates:
        return ExitCode.NEW_MODELS_AVAILABLE

    return ExitCode.UP_TO_DATE


async def _async_check_models(
    provider: ProviderChoice, verbose: bool
) -> list[ModelComparisonResult]:
    """Async implementation of model checking.

    Args:
        provider: Provider(s) to check
        verbose: Include detailed output

    Returns:
        List of comparison results

    Raises:
        Exception: If API calls fail
    """
    settings = Settings()
    factory = CheckerFactory(settings=settings, logger=logger)

    # Determine which providers to check
    providers_to_check: list[ProviderName] = []
    if provider == ProviderChoice.ALL:
        providers_to_check = [
            ProviderName.ANTHROPIC,
            ProviderName.OPENAI,
            ProviderName.GOOGLE,
            ProviderName.OPENROUTER,
        ]
    else:
        # Map ProviderChoice to ProviderName
        provider_map = {
            ProviderChoice.ANTHROPIC: ProviderName.ANTHROPIC,
            ProviderChoice.OPENAI: ProviderName.OPENAI,
            ProviderChoice.GOOGLE: ProviderName.GOOGLE,
            ProviderChoice.OPENROUTER: ProviderName.OPENROUTER,
        }
        providers_to_check = [provider_map[provider]]

    # Run comparisons
    results: list[ModelComparisonResult] = []

    for provider_name in providers_to_check:
        console.print(f"\n[bold]Checking {provider_name.value.upper()} models...[/bold]")

        try:
            checker = await factory.create_checker(provider_name)
            if checker is None:
                console.print(f"[yellow]Skipping {provider_name.value} (no API key)[/yellow]")
                continue

            result = await checker.compare_with_manifest()
            results.append(result)

            # Display table for this provider
            table = format_comparison_table(result, verbose=verbose)
            console.print(table)

            if result.is_up_to_date:
                console.print(f"[green]✓ {provider_name.value.upper()} is up-to-date[/green]")

        except Exception as exc:
            logger.error(
                f"Failed to check {provider_name.value}",
                extra={"provider": provider_name.value, "error": str(exc)},
                exc_info=True,
            )
            console.print(f"[red]✗ Error checking {provider_name.value}: {exc}[/red]")
            raise

    return results


@APP.command()
def check_models(
    provider: ProviderChoice = typer.Option(
        ProviderChoice.ALL,
        "--provider",
        "-p",
        case_sensitive=False,
        help="Provider to check (or 'all' for all providers)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed model metadata",
    ),
) -> None:
    """Check LLM provider model versions against the manifest.

    This command queries LLM provider APIs to discover available models
    and compares them with the centralized model manifest. It identifies:

    - New models (available but not in manifest)
    - Deprecated models (in manifest but deprecated by provider)
    - Updated models (metadata changes)
    - Breaking changes (API version changes)

    Examples:

        # Check all providers
        pdm run llm-check-models

        # Check specific provider
        pdm run llm-check-models --provider anthropic

        # Show detailed information
        pdm run llm-check-models --provider openai --verbose
    """
    try:
        results = asyncio.run(_async_check_models(provider, verbose))

        if not results:
            console.print("[yellow]No providers were checked[/yellow]")
            raise typer.Exit(code=ExitCode.API_ERROR.value)

        # Display summary
        format_summary(results)

        # Display breaking changes if any
        format_breaking_changes(results)

        # Determine exit code
        exit_code = determine_exit_code(results)

        if exit_code == ExitCode.BREAKING_CHANGES:
            console.print(
                "\n[red]⛔ Breaking changes detected! Update the manifest before proceeding.[/red]"
            )
        elif exit_code == ExitCode.NEW_MODELS_AVAILABLE:
            console.print(
                "\n[yellow]⚠️  New models or updates available. "
                "Consider updating the manifest.[/yellow]"
            )
        else:
            console.print("\n[green]✅ All providers are up-to-date![/green]")

        raise typer.Exit(code=exit_code.value)

    except Exception as exc:
        logger.error("Model check failed", exc_info=True)
        console.print(f"\n[red]Error: {exc}[/red]")
        raise typer.Exit(code=ExitCode.API_ERROR.value)


if __name__ == "__main__":
    APP()
