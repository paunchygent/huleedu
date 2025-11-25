"""OpenAI model version checker implementation.

This module implements the ModelCheckerProtocol for OpenAI's GPT models.
It queries the OpenAI API /v1/models endpoint to discover available models
and compares them with the model manifest.

Usage:
    from openai import AsyncOpenAI
    from services.llm_provider_service.model_checker import OpenAIModelChecker

    client = AsyncOpenAI(api_key="...")
    checker = OpenAIModelChecker(client, logger)

    # Discover latest models from OpenAI API
    models = await checker.check_latest_models()

    # Compare with manifest
    result = await checker.compare_with_manifest()
"""

from __future__ import annotations

import logging
from datetime import date

from openai import AsyncOpenAI
from openai.types import Model

from services.llm_provider_service.config import Settings
from services.llm_provider_service.model_checker.base import (
    DiscoveredModel,
    ModelComparisonResult,
)
from services.llm_provider_service.model_checker.family_utils import extract_openai_family
from services.llm_provider_service.model_manifest import (
    ProviderName,
    list_models,
)


class OpenAIModelChecker:
    """OpenAI model version checker.

    Queries OpenAI's /v1/models API endpoint to discover available models
    and compares them with the manifest.

    Attributes:
        client: Async OpenAI SDK client
        logger: Structured logger for observability
        settings: Service configuration (provides ACTIVE_MODEL_FAMILIES)
        provider: Always ProviderName.OPENAI
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        logger: logging.Logger,
        settings: Settings,
    ):
        """Initialize OpenAI model checker.

        Args:
            client: Configured AsyncOpenAI client
            logger: Logger for structured logging
            settings: Service configuration (provides ACTIVE_MODEL_FAMILIES)
        """
        self.client = client
        self.logger = logger
        self.settings = settings
        self.provider = ProviderName.OPENAI

    async def check_latest_models(self) -> list[DiscoveredModel]:
        """Query OpenAI API and discover available models.

        Queries the /v1/models endpoint and parses the response into
        DiscoveredModel instances. Filters out legacy models that are
        no longer relevant.

        Returns:
            List of models discovered from OpenAI API

        Raises:
            openai.APIError: If API request fails
        """
        self.logger.info(
            "Checking latest models from OpenAI API",
            extra={"provider": self.provider.value},
        )

        try:
            # Query OpenAI models API
            response = await self.client.models.list()

            discovered: list[DiscoveredModel] = []
            async for model in response:
                # Parse Model into DiscoveredModel
                discovered_model = self._parse_model(model)

                # Filter out legacy/deprecated models we don't care about
                if self._should_include_model(discovered_model):
                    discovered.append(discovered_model)

            self.logger.info(
                "Successfully discovered models from OpenAI",
                extra={
                    "provider": self.provider.value,
                    "filtered_models": len(discovered),
                },
            )

            return discovered

        except Exception as e:
            self.logger.error(
                "Failed to check latest models from OpenAI",
                extra={
                    "provider": self.provider.value,
                    "error": str(e),
                },
            )
            raise

    def _extract_family(self, model_id: str) -> str:
        """Extract model family using centralized utility.

        Examples:
            gpt-5-mini-2025-08-07 → gpt-5
            gpt-4.1-2025-04-14 → gpt-4.1
            dall-e-3 → dall-e

        Args:
            model_id: Full model identifier from OpenAI API

        Returns:
            Family identifier (e.g., "gpt-5", "dall-e")
        """
        return extract_openai_family(model_id)

    def _get_active_families(self) -> set[str]:
        """Get configured active families for OpenAI from settings.

        Returns:
            Set of family identifiers being tracked (e.g., {"gpt-5", "gpt-4o"})
        """
        return set(self.settings.ACTIVE_MODEL_FAMILIES.get(ProviderName.OPENAI, []))

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

        # Get manifest models for OpenAI
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

        # Identify deprecated models (in manifest but not in API anymore)
        deprecated_models = [
            model_id for model_id in manifest_by_id.keys() if model_id not in discovered_by_id
        ]

        # Check for breaking changes (rare for OpenAI as they use 'v1' consistently)
        breaking_changes: list[str] = []

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

    def _parse_model(self, model: Model) -> DiscoveredModel:
        """Parse OpenAI Model into DiscoveredModel.

        Args:
            model: Model from OpenAI API

        Returns:
            DiscoveredModel instance
        """
        # OpenAI Model has: id, object, created, owned_by
        # Limited metadata compared to Anthropic

        # Infer capabilities from model ID
        capabilities: list[str] = []
        model_id_lower = model.id.lower()

        # GPT-4 and newer support function calling
        if any(x in model_id_lower for x in ["gpt-4", "gpt-5"]):
            capabilities = ["function_calling", "json_mode"]

        # Extract metadata
        return DiscoveredModel(
            model_id=model.id,
            display_name=model.id.upper().replace("-", " "),
            api_version="v1",  # OpenAI uses v1 consistently
            capabilities=capabilities,
            max_tokens=None,  # Not exposed in Model object
            context_window=None,  # Not exposed in Model object
            supports_tool_use="function_calling" in capabilities,
            supports_streaming=True,  # All OpenAI models support streaming
            release_date=date.fromtimestamp(model.created) if model.created else None,
            is_deprecated=False,  # OpenAI doesn't expose deprecation in API
            deprecation_date=None,
            notes=f"Owned by: {model.owned_by}" if model.owned_by else "",
        )

    def _should_include_model(self, model: DiscoveredModel) -> bool:
        """Determine if a discovered model should be included in results.

        Filters out models that are not in the currently supported GPT families
        (gpt-5, gpt-4.1, gpt-4o).

        Args:
            model: Discovered model to evaluate

        Returns:
            True if model should be included
        """
        # Restrict GPT families to gpt-5, gpt-4.1, and gpt-4o
        family = self._extract_family(model.model_id)
        allowed_families = {"gpt-5", "gpt-4.1", "gpt-4o"}
        return family in allowed_families
