"""Google Generative AI model version checker implementation.

This module implements the ModelCheckerProtocol for Google's Gemini models.
It queries the Google Generative AI API to discover available models
and compares them with the model manifest.

Usage:
    from google import genai
    from services.llm_provider_service.model_checker import GoogleModelChecker

    client = genai.Client(api_key="...")
    checker = GoogleModelChecker(client, logger, settings)

    # Discover latest models from Google API
    models = await checker.check_latest_models()

    # Compare with manifest
    result = await checker.compare_with_manifest()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from google.genai import Client as GenAIClient

from services.llm_provider_service.config import Settings
from services.llm_provider_service.model_checker.base import (
    DiscoveredModel,
    ModelComparisonResult,
)
from services.llm_provider_service.model_checker.family_utils import extract_google_family
from services.llm_provider_service.model_manifest import (
    ModelConfig,
    ProviderName,
    list_models,
)


class GoogleModelChecker:
    """Google Generative AI model version checker.

    Queries Google's models API to discover available models
    and compares them with the manifest.

    Attributes:
        client: Google GenAI client
        logger: Structured logger for observability
        settings: Service configuration (provides ACTIVE_MODEL_FAMILIES)
        provider: Always ProviderName.GOOGLE
    """

    def __init__(
        self,
        client: GenAIClient,
        logger: logging.Logger,
        settings: Settings,
    ):
        """Initialize Google model checker.

        Args:
            client: Configured google.genai.Client instance
            logger: Logger for structured logging
            settings: Service configuration (provides ACTIVE_MODEL_FAMILIES)
        """
        self.client = client
        self.logger = logger
        self.settings = settings
        self.provider = ProviderName.GOOGLE

    async def check_latest_models(self) -> list[DiscoveredModel]:
        """Query Google API and discover available models.

        Queries the models API and parses the response into
        DiscoveredModel instances. Filters out legacy models that are
        no longer relevant.

        Returns:
            List of models discovered from Google API

        Raises:
            google.genai.errors.APIError: If API request fails
        """
        self.logger.info(
            "Checking latest models from Google API",
            extra={"provider": self.provider.value},
        )

        try:
            # Query Google models API using async client
            discovered: list[DiscoveredModel] = []

            # Use async iteration for the pager
            async for model in await self.client.aio.models.list():
                # Parse model into DiscoveredModel
                discovered_model = self._parse_model(model)

                # Filter out legacy/deprecated models we don't care about
                if self._should_include_model(discovered_model):
                    discovered.append(discovered_model)

            self.logger.info(
                "Successfully discovered models from Google",
                extra={
                    "provider": self.provider.value,
                    "filtered_models": len(discovered),
                },
            )

            return discovered

        except Exception as e:
            self.logger.error(
                "Failed to check latest models from Google",
                extra={
                    "provider": self.provider.value,
                    "error": str(e),
                },
            )
            raise

    def _extract_family(self, model_id: str) -> str:
        """Extract model family using centralized utility.

        Examples:
            gemini-2.5-flash-preview-05-20 → gemini-2.5-flash

        Args:
            model_id: Full model identifier from Google API

        Returns:
            Family identifier (e.g., "gemini-2.5-flash")
        """
        return extract_google_family(model_id)

    def _get_active_families(self) -> set[str]:
        """Get configured active families for Google from settings.

        Returns:
            Set of family identifiers being tracked
        """
        return set(self.settings.ACTIVE_MODEL_FAMILIES.get(ProviderName.GOOGLE, []))

    async def compare_with_manifest(self) -> ModelComparisonResult:
        """Compare discovered models with manifest and identify changes.

        Identifies:
        - New models: in API but not in manifest
        - Deprecated models: in manifest but deprecated by provider
        - Updated models: metadata changes (API version, capabilities)
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

        # Get manifest models for Google
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

        # Identify updated models (metadata changes)
        updated_models: list[tuple[str, DiscoveredModel]] = []
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
                    updated_models.append((model_id, discovered_model))

                # Check for capability changes (non-breaking but notable)
                elif self._has_capability_changes(manifest_model, discovered_model):
                    updated_models.append((model_id, discovered_model))

        # Determine if manifest is up-to-date
        is_up_to_date = (
            len(new_in_tracked) == 0
            and len(new_untracked) == 0
            and len(deprecated_models) == 0
            and len(updated_models) == 0
            and len(breaking_changes) == 0
        )

        result = ModelComparisonResult(
            provider=self.provider,
            new_models_in_tracked_families=new_in_tracked,
            new_untracked_families=new_untracked,
            deprecated_models=deprecated_models,
            updated_models=updated_models,
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
                "updated_models_count": len(updated_models),
                "breaking_changes_count": len(breaking_changes),
                "is_up_to_date": is_up_to_date,
            },
        )

        return result

    def _parse_model(self, model: Any) -> DiscoveredModel:
        """Parse Google model object into DiscoveredModel.

        Args:
            model: Model object from Google API

        Returns:
            DiscoveredModel instance
        """
        # Google model has: name, display_name, description, supported_generation_methods
        # Extract model ID from name (format: models/gemini-...)
        model_id = model.name.split("/")[-1] if hasattr(model, "name") else model.name

        # Infer capabilities from supported generation methods
        capabilities: list[str] = []
        if hasattr(model, "supported_generation_methods"):
            methods = model.supported_generation_methods or []
            if "generateContent" in methods:
                capabilities.append("text_generation")
            if "generateMessage" in methods:
                capabilities.append("chat")

        # Google models support function calling
        capabilities.extend(["function_calling", "json_mode", "multimodal"])

        return DiscoveredModel(
            model_id=model_id,
            display_name=model.display_name if hasattr(model, "display_name") else model_id,
            api_version="v1",  # Google uses v1
            capabilities=capabilities,
            max_tokens=getattr(model, "output_token_limit", None),
            context_window=getattr(model, "input_token_limit", None),
            supports_tool_use=True,  # All Gemini models support tools
            supports_streaming=True,  # All Gemini models support streaming
            release_date=None,  # Not exposed in API
            is_deprecated=False,  # Not exposed in API
            deprecation_date=None,
            notes=getattr(model, "description", "") or "",
        )

    def _should_include_model(self, model: DiscoveredModel) -> bool:
        """Determine if a discovered model should be included in results.

        Filters out legacy models that are no longer relevant for comparison.

        Args:
            model: Discovered model to evaluate

        Returns:
            True if model should be included
        """
        # Include Gemini 1.5, 2.0, 2.5 and newer models
        # Filter out Gemini 1.0 and earlier (legacy)
        model_id_lower = model.model_id.lower()

        # Include if it's a Gemini 1.5+ model
        if any(x in model_id_lower for x in ["gemini-1.5", "gemini-2", "gemini-3"]):
            return True

        # Exclude Gemini 1.0 and pro-vision (legacy)
        if "gemini-1.0" in model_id_lower or "pro-vision" in model_id_lower:
            return False

        # Include everything else (future models)
        return True

    def _has_capability_changes(
        self,
        manifest_model: ModelConfig,
        discovered_model: DiscoveredModel,
    ) -> bool:
        """Check if capabilities have changed between manifest and discovered model.

        Google's models API does not expose capability information (tool_use, vision, etc).
        The API returns supported_actions (API endpoints like 'generateContent'), not
        model capabilities. Discovered capabilities are hard-coded assumptions
        (function_calling, json_mode, multimodal), not actual API data.

        Comparing hard-coded capabilities against manifest capabilities produces
        false positives. Since capabilities are static (determined by model architecture),
        we skip this comparison.

        Args:
            manifest_model: Model from manifest
            discovered_model: Model from API (with hard-coded capabilities)

        Returns:
            False (capabilities comparison disabled for Google)
        """
        # Google API doesn't expose capabilities - skip comparison to avoid false positives
        return False
