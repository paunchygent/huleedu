"""Anthropic model version checker implementation.

This module implements the ModelCheckerProtocol for Anthropic's Claude models.
It queries the Anthropic API /v1/models endpoint to discover available models
and compares them with the model manifest.

Usage:
    from anthropic import AsyncAnthropic
    from services.llm_provider_service.model_checker import AnthropicModelChecker

    client = AsyncAnthropic(api_key="...")
    checker = AnthropicModelChecker(client, logger)

    # Discover latest models from Anthropic API
    models = await checker.check_latest_models()

    # Compare with manifest
    result = await checker.compare_with_manifest()
"""

from __future__ import annotations

import logging

from anthropic import AsyncAnthropic
from anthropic.types import ModelInfo

from services.llm_provider_service.config import Settings
from services.llm_provider_service.model_checker.base import (
    DiscoveredModel,
    ModelComparisonResult,
)
from services.llm_provider_service.model_checker.family_utils import extract_anthropic_family
from services.llm_provider_service.model_manifest import (
    ModelConfig,
    ProviderName,
    list_models,
)


class AnthropicModelChecker:
    """Anthropic model version checker.

    Queries Anthropic's /v1/models API endpoint to discover available models
    and compares them with the manifest.

    Attributes:
        client: Async Anthropic SDK client
        logger: Structured logger for observability
        settings: Service configuration (provides ACTIVE_MODEL_FAMILIES)
        provider: Always ProviderName.ANTHROPIC
    """

    def __init__(
        self,
        client: AsyncAnthropic,
        logger: logging.Logger,
        settings: Settings,
    ):
        """Initialize Anthropic model checker.

        Args:
            client: Configured AsyncAnthropic client
            logger: Logger for structured logging
            settings: Service configuration (provides ACTIVE_MODEL_FAMILIES)
        """
        self.client = client
        self.logger = logger
        self.settings = settings
        self.provider = ProviderName.ANTHROPIC

    async def check_latest_models(self) -> list[DiscoveredModel]:
        """Query Anthropic API and discover available models.

        Queries the /v1/models endpoint and parses the response into
        DiscoveredModel instances. Filters out legacy models that are
        no longer relevant.

        Returns:
            List of models discovered from Anthropic API

        Raises:
            anthropic.APIError: If API request fails
        """
        self.logger.info(
            "Checking latest models from Anthropic API",
            extra={"provider": self.provider.value},
        )

        try:
            # Query Anthropic models API
            response = await self.client.models.list()

            discovered: list[DiscoveredModel] = []
            for model_info in response.data:
                # Parse ModelInfo into DiscoveredModel
                discovered_model = self._parse_model_info(model_info)

                # Filter out legacy/deprecated models we don't care about
                if self._should_include_model(discovered_model):
                    discovered.append(discovered_model)

            self.logger.info(
                "Successfully discovered models from Anthropic",
                extra={
                    "provider": self.provider.value,
                    "total_models": len(response.data),
                    "filtered_models": len(discovered),
                },
            )

            return discovered

        except Exception as e:
            self.logger.error(
                "Failed to check latest models from Anthropic",
                extra={
                    "provider": self.provider.value,
                    "error": str(e),
                },
            )
            raise

    def _extract_family(self, model_id: str) -> str:
        """Extract model family using centralized utility.

        Examples:
            claude-haiku-4-5-20251001 → claude-haiku
            claude-sonnet-4-5-20250929 → claude-sonnet

        Args:
            model_id: Full model identifier from Anthropic API

        Returns:
            Family identifier (e.g., "claude-haiku")
        """
        return extract_anthropic_family(model_id)

    def _get_active_families(self) -> set[str]:
        """Get configured active families for Anthropic from settings.

        Returns:
            Set of family identifiers being tracked
        """
        return set(self.settings.ACTIVE_MODEL_FAMILIES.get(ProviderName.ANTHROPIC, []))

    async def compare_with_manifest(self) -> ModelComparisonResult:
        """Compare discovered models with manifest and identify changes.

        Identifies:
        - New models: in API but not in manifest
        - Deprecated models: in manifest but deprecated by provider
        - Breaking changes: incompatible changes requiring manifest update

        Returns:
            ModelComparisonResult with delta information

        Raises:
            ValueError: If manifest lookup fails
        """
        self.logger.info(
            "Comparing discovered models with manifest",
            extra={"provider": self.provider.value},
        )

        # Get discovered models from API
        discovered = await self.check_latest_models()

        # Get manifest models for Anthropic
        manifest_models = list_models(self.provider)

        # Build lookup maps
        discovered_by_id = {m.model_id: m for m in discovered}
        manifest_by_id = {m.model_id: m for m in manifest_models}
        active_families = self._get_active_families()

        # Categorize new models by family
        new_in_tracked = []
        new_untracked = []

        for model_id, discovered_model in discovered_by_id.items():
            if model_id not in manifest_by_id:
                family = self._extract_family(model_id)

                if family in active_families:
                    new_in_tracked.append(discovered_model)
                else:
                    new_untracked.append(discovered_model)

        # Identify deprecated models (in manifest but deprecated by provider)
        deprecated_models = [
            model_id
            for model_id, manifest_model in manifest_by_id.items()
            if discovered_by_id.get(
                model_id, DiscoveredModel(model_id="", display_name="")
            ).is_deprecated
        ]

        # Identify breaking changes (e.g., API version changes)
        breaking_changes: list[str] = []

        for model_id, manifest_model in manifest_by_id.items():
            if model_id in discovered_by_id:
                discovered_model = discovered_by_id[model_id]

                # Check for API version changes (breaking)
                if (
                    discovered_model.api_version
                    and manifest_model.api_version != discovered_model.api_version
                ):
                    breaking_changes.append(
                        f"{model_id}: API version changed from "
                        f"{manifest_model.api_version} to {discovered_model.api_version}"
                    )

        # Determine if manifest is up-to-date
        is_up_to_date = (
            len(new_in_tracked) == 0
            and len(new_untracked) == 0
            and len(deprecated_models) == 0
            and len(breaking_changes) == 0
        )

        result = ModelComparisonResult(
            provider=self.provider,
            new_models_in_tracked_families=new_in_tracked,
            new_untracked_families=new_untracked,
            deprecated_models=deprecated_models,
            breaking_changes=breaking_changes,
            is_up_to_date=is_up_to_date,
        )

        self.logger.info(
            "Comparison complete",
            extra={
                "provider": self.provider.value,
                "new_in_tracked_count": len(new_in_tracked),
                "new_untracked_count": len(new_untracked),
                "deprecated_models_count": len(deprecated_models),
                "breaking_changes_count": len(breaking_changes),
                "is_up_to_date": is_up_to_date,
            },
        )

        return result

    def _parse_model_info(self, model_info: ModelInfo) -> DiscoveredModel:
        """Parse Anthropic ModelInfo into DiscoveredModel.

        Args:
            model_info: ModelInfo from Anthropic API

        Returns:
            DiscoveredModel instance
        """
        # Parse capabilities from ModelInfo
        capabilities: list[str] = []
        if hasattr(model_info, "supported_features"):
            capabilities = model_info.supported_features or []

        # Extract metadata
        return DiscoveredModel(
            model_id=model_info.id,
            display_name=model_info.display_name or model_info.id,
            api_version=None,  # Anthropic doesn't expose this in ModelInfo
            capabilities=capabilities,
            max_tokens=getattr(model_info, "max_tokens", None),
            context_window=getattr(model_info, "context_window", None),
            supports_tool_use="tool_use" in capabilities,
            supports_streaming=True,  # All Anthropic models support streaming
            release_date=getattr(model_info, "created_at", None),
            is_deprecated=False,  # Anthropic doesn't expose deprecation in API
            deprecation_date=None,
            notes="",
        )

    def _should_include_model(self, model: DiscoveredModel) -> bool:
        """Determine if a discovered model should be included in results.

        Filters out legacy models that are no longer relevant for comparison.

        Args:
            model: Discovered model to evaluate

        Returns:
            True if model should be included
        """
        # Include Claude 3.x and newer models
        # Filter out Claude 2.x and earlier (legacy)
        model_id_lower = model.model_id.lower()

        # Include if it's a Claude 3+ model
        if "claude-3" in model_id_lower or "claude-4" in model_id_lower:
            return True

        # Exclude Claude 2 and earlier
        if "claude-2" in model_id_lower or "claude-instant" in model_id_lower:
            return False

        # Include everything else (future models)
        return True

