"""OpenRouter model version checker implementation.

This module implements the ModelCheckerProtocol for OpenRouter's aggregated models.
It queries the OpenRouter REST API /api/v1/models endpoint to discover available models
and compares them with the model manifest.

Usage:
    import aiohttp
    from services.llm_provider_service.model_checker import OpenRouterModelChecker

    async with aiohttp.ClientSession() as session:
        checker = OpenRouterModelChecker(
            session=session,
            api_key="...",
            logger=logger
        )

        # Discover latest models from OpenRouter API
        models = await checker.check_latest_models()

        # Compare with manifest
        result = await checker.compare_with_manifest()
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from services.llm_provider_service.config import Settings
from services.llm_provider_service.model_checker.base import (
    DiscoveredModel,
    ModelComparisonResult,
)
from services.llm_provider_service.model_checker.family_utils import extract_openrouter_family
from services.llm_provider_service.model_manifest import (
    ProviderName,
    list_models,
)


class OpenRouterModelChecker:
    """OpenRouter model version checker.

    Queries OpenRouter's REST API /api/v1/models endpoint to discover available models
    and compares them with the manifest.

    Attributes:
        session: aiohttp ClientSession for API requests
        api_key: OpenRouter API key for authentication
        logger: Structured logger for observability
        settings: Service configuration (provides ACTIVE_MODEL_FAMILIES)
        provider: Always ProviderName.OPENROUTER
        api_base: OpenRouter API base URL
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        logger: logging.Logger,
        settings: Settings,
    ):
        """Initialize OpenRouter model checker.

        Args:
            session: Configured aiohttp ClientSession
            api_key: OpenRouter API key
            logger: Logger for structured logging
            settings: Service configuration (provides ACTIVE_MODEL_FAMILIES)
        """
        self.session = session
        self.api_key = api_key
        self.logger = logger
        self.settings = settings
        self.provider = ProviderName.OPENROUTER
        self.api_base = "https://openrouter.ai/api/v1"

    async def check_latest_models(self) -> list[DiscoveredModel]:
        """Query OpenRouter API and discover available models.

        Queries the /api/v1/models endpoint and parses the response into
        DiscoveredModel instances. Filters out legacy models that are
        no longer relevant.

        Returns:
            List of models discovered from OpenRouter API

        Raises:
            aiohttp.ClientError: If API request fails
        """
        self.logger.info(
            "Checking latest models from OpenRouter API",
            extra={"provider": self.provider.value},
        )

        try:
            # Query OpenRouter models API
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            async with self.session.get(
                f"{self.api_base}/models",
                headers=headers,
            ) as response:
                response.raise_for_status()
                data = await response.json()

            # Parse response
            models_data = data.get("data", [])
            discovered: list[DiscoveredModel] = []

            for model_data in models_data:
                # Parse model data into DiscoveredModel
                discovered_model = self._parse_model_data(model_data)

                # Filter out legacy/deprecated models we don't care about
                if self._should_include_model(discovered_model):
                    discovered.append(discovered_model)

            self.logger.info(
                "Successfully discovered models from OpenRouter",
                extra={
                    "provider": self.provider.value,
                    "total_models": len(models_data),
                    "filtered_models": len(discovered),
                },
            )

            return discovered

        except Exception as e:
            self.logger.error(
                "Failed to check latest models from OpenRouter",
                extra={
                    "provider": self.provider.value,
                    "error": str(e),
                },
            )
            raise

    def _extract_family(self, model_id: str) -> str:
        """Extract model family using centralized utility.

        Examples:
            anthropic/claude-haiku-4-5-20251001 → claude-haiku-openrouter

        Args:
            model_id: Full model identifier from OpenRouter API

        Returns:
            Family identifier with -openrouter suffix
        """
        return extract_openrouter_family(model_id)

    def _get_active_families(self) -> set[str]:
        """Get configured active families for OpenRouter from settings.

        Returns:
            Set of family identifiers being tracked
        """
        return set(self.settings.ACTIVE_MODEL_FAMILIES.get(ProviderName.OPENROUTER, []))

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

        # Get manifest models for OpenRouter
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

        # Check for breaking changes (rare for OpenRouter as it's a pass-through)
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

    def _parse_model_data(self, model_data: dict[str, Any]) -> DiscoveredModel:
        """Parse OpenRouter model data into DiscoveredModel.

        Args:
            model_data: Model data dict from OpenRouter API

        Returns:
            DiscoveredModel instance
        """
        # OpenRouter returns: id, name, context_length, pricing, etc.
        model_id = model_data.get("id", "")
        name = model_data.get("name", model_id)
        context_length = model_data.get("context_length")

        # Infer capabilities (OpenRouter is a pass-through)
        capabilities: list[str] = []

        # Check if model supports various features
        if "function" in name.lower() or "tool" in name.lower():
            capabilities.append("function_calling")

        # Most modern models support JSON mode
        capabilities.append("json_mode")

        return DiscoveredModel(
            model_id=model_id,
            display_name=name,
            api_version="v1",  # OpenRouter uses v1
            capabilities=capabilities,
            max_tokens=model_data.get("top_provider", {}).get("max_completion_tokens"),
            context_window=context_length,
            supports_tool_use="function_calling" in capabilities,
            supports_streaming=True,  # OpenRouter supports streaming
            release_date=None,  # Not exposed in API
            is_deprecated=False,  # Not exposed in API
            deprecation_date=None,
            notes=model_data.get("description", ""),
        )

    def _should_include_model(self, model: DiscoveredModel) -> bool:
        """Determine if a discovered model should be included in results.

        Filters out legacy models that are no longer relevant for comparison.
        Only include Anthropic models routed through OpenRouter.

        Args:
            model: Discovered model to evaluate

        Returns:
            True if model should be included
        """
        model_id_lower = model.model_id.lower()

        # Only include Anthropic Claude 4.5-tier models via OpenRouter.
        # Example accepted: anthropic/claude-haiku-4-5-20251001
        if not model_id_lower.startswith("anthropic/claude-"):
            return False

        # Require the 4-5 marker in the Anthropic portion.
        _, anthropic_part = model_id_lower.split("/", 1)
        return "-4-5-" in anthropic_part
