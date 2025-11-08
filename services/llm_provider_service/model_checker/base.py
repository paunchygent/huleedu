"""Base protocol and models for LLM model version checking.

This module defines the interface for checking model versions from LLM providers
and comparing them against the model manifest. It provides:

- DiscoveredModel: Pydantic model for models discovered from provider APIs
- ModelComparisonResult: Results from comparing discovered vs manifest models
- ModelCheckerProtocol: Protocol interface for provider-specific checkers

Architecture:
    Each provider (Anthropic, OpenAI, Google, OpenRouter) implements
    ModelCheckerProtocol to query their API and discover available models.
    The comparison logic identifies new models, deprecated models, and
    breaking changes.

Usage:
    from services.llm_provider_service.model_checker import ModelCheckerProtocol

    class MyProviderChecker:
        async def check_latest_models(self) -> list[DiscoveredModel]:
            # Query provider API
            ...

        async def compare_with_manifest(self) -> ModelComparisonResult:
            # Compare discovered vs manifest
            ...
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from services.llm_provider_service.model_manifest import ProviderName


class DiscoveredModel(BaseModel):
    """Model discovered from a provider's API.

    This represents a model found by querying the provider's API endpoint.
    It contains metadata returned by the provider, which may differ from
    our manifest's structure.

    Attributes:
        model_id: Provider-specific model identifier
        display_name: Human-readable model name
        api_version: API version required by provider (if applicable)
        capabilities: List of capability strings (e.g., ['tool_use', 'vision'])
        max_tokens: Maximum output tokens supported
        context_window: Total context window size (if known)
        supports_tool_use: Whether model supports function/tool calling
        supports_streaming: Whether model supports streaming responses
        release_date: Model release date (if known)
        is_deprecated: Whether provider marks this model as deprecated
        deprecation_date: When model will be/was deprecated (if known)
        notes: Additional information from provider
    """

    model_config = ConfigDict(frozen=True)

    # Identity
    model_id: str = Field(
        ...,
        description="Provider-specific model identifier",
    )
    display_name: str = Field(
        ...,
        description="Human-readable model name",
    )

    # API Configuration
    api_version: str | None = Field(
        default=None,
        description="API version string required by provider",
    )

    # Capabilities (as strings since providers may use different schemas)
    capabilities: list[str] = Field(
        default_factory=list,
        description="List of capability strings (e.g., ['tool_use', 'vision'])",
    )

    # Performance Characteristics
    max_tokens: int | None = Field(
        default=None,
        description="Maximum output tokens supported",
    )
    context_window: int | None = Field(
        default=None,
        description="Total context window size",
    )
    supports_tool_use: bool = Field(
        default=False,
        description="Supports function/tool calling",
    )
    supports_streaming: bool = Field(
        default=True,
        description="Supports streaming responses",
    )

    # Metadata
    release_date: date | None = Field(
        default=None,
        description="Model release date",
    )
    is_deprecated: bool = Field(
        default=False,
        description="Model is deprecated by provider",
    )
    deprecation_date: date | None = Field(
        default=None,
        description="Date model will be/was deprecated",
    )

    # Additional Info
    notes: str = Field(
        default="",
        description="Additional information from provider",
    )


class ModelComparisonResult(BaseModel):
    """Result of comparing discovered models with manifest.

    This captures the delta between what the provider API reports and
    what our manifest contains. Used by the CLI to display changes.

    Attributes:
        provider: Which provider was checked
        new_models: Models discovered but not in manifest
        deprecated_models: Model IDs in manifest but marked deprecated by provider
        updated_models: Models where metadata changed (model_id, discovered_model)
        breaking_changes: List of breaking change descriptions
        is_up_to_date: True if manifest matches provider API exactly
        checked_at: When this comparison was performed
    """

    model_config = ConfigDict(frozen=True)

    provider: ProviderName = Field(
        ...,
        description="Provider that was checked",
    )
    new_models: list[DiscoveredModel] = Field(
        default_factory=list,
        description="Models discovered but not in manifest",
    )
    deprecated_models: list[str] = Field(
        default_factory=list,
        description="Model IDs in manifest but deprecated by provider",
    )
    updated_models: list[tuple[str, DiscoveredModel]] = Field(
        default_factory=list,
        description="Models where metadata changed (model_id, discovered_model)",
    )
    breaking_changes: list[str] = Field(
        default_factory=list,
        description="Breaking change descriptions (e.g., API version changes)",
    )
    is_up_to_date: bool = Field(
        ...,
        description="True if manifest matches provider API exactly",
    )
    checked_at: date = Field(
        default_factory=date.today,
        description="When this comparison was performed",
    )


class ModelCheckerProtocol(Protocol):
    """Protocol for checking model versions from LLM providers.

    Each provider (Anthropic, OpenAI, Google, OpenRouter) implements this
    protocol to query their API and compare discovered models with the manifest.

    Implementations should:
    1. Query the provider's model listing API
    2. Parse responses into DiscoveredModel instances
    3. Filter out legacy/deprecated models that aren't relevant
    4. Compare discovered models with manifest entries
    5. Identify breaking changes (e.g., API version changes)

    Example:
        class AnthropicModelChecker:
            async def check_latest_models(self) -> list[DiscoveredModel]:
                # Query Anthropic /v1/models endpoint
                # Parse and return discovered models
                ...

            async def compare_with_manifest(self) -> ModelComparisonResult:
                # Get manifest models for Anthropic
                # Compare with discovered models
                # Identify new, deprecated, updated models
                ...
    """

    async def check_latest_models(self) -> list[DiscoveredModel]:
        """Query provider API and discover available models.

        This method should:
        1. Authenticate with the provider's API
        2. Query the models endpoint (e.g., /v1/models)
        3. Parse the response into DiscoveredModel instances
        4. Filter out legacy/irrelevant models

        Returns:
            List of models discovered from provider API

        Raises:
            aiohttp.ClientError: If API request fails
            ValueError: If response parsing fails
        """
        ...

    async def compare_with_manifest(self) -> ModelComparisonResult:
        """Compare discovered models with manifest and identify changes.

        This method should:
        1. Call check_latest_models() to get current provider models
        2. Load manifest models for this provider
        3. Identify:
           - New models: in API but not in manifest
           - Deprecated models: in manifest but deprecated by provider
           - Updated models: metadata changes (API version, capabilities)
           - Breaking changes: incompatible changes requiring manifest update

        Returns:
            ModelComparisonResult with delta information

        Raises:
            ValueError: If manifest lookup fails
        """
        ...
