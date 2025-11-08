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

from services.llm_provider_service.model_checker.base import (
    DiscoveredModel,
    ModelComparisonResult,
)
from services.llm_provider_service.model_manifest import (
    ModelConfig,
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
        provider: Always ProviderName.OPENAI
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        logger: logging.Logger,
    ):
        """Initialize OpenAI model checker.

        Args:
            client: Configured AsyncOpenAI client
            logger: Logger for structured logging
        """
        self.client = client
        self.logger = logger
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

        # Get manifest models for OpenAI
        manifest_models = list_models(self.provider)

        # Build lookup maps
        discovered_by_id = {m.model_id: m for m in discovered}
        manifest_by_id = {m.model_id: m for m in manifest_models}

        # Identify new models (in API but not in manifest)
        new_models = [
            model for model_id, model in discovered_by_id.items() if model_id not in manifest_by_id
        ]

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

                # Check for API version changes (breaking for OpenAI is rare)
                # OpenAI uses 'v1' consistently, so breaking changes are unlikely
                # but we check for capability changes

                # Check for capability changes (non-breaking but notable)
                if self._has_capability_changes(manifest_model, discovered_model):
                    updated_models.append((model_id, discovered_model))

        # Determine if manifest is up-to-date
        is_up_to_date = (
            len(new_models) == 0
            and len(deprecated_models) == 0
            and len(updated_models) == 0
            and len(breaking_changes) == 0
        )

        result = ModelComparisonResult(
            provider=self.provider,
            new_models=new_models,
            deprecated_models=deprecated_models,
            updated_models=updated_models,
            breaking_changes=breaking_changes,
            is_up_to_date=is_up_to_date,
        )

        self.logger.info(
            "Comparison complete",
            extra={
                "provider": self.provider.value,
                "new_models_count": len(new_models),
                "deprecated_models_count": len(deprecated_models),
                "updated_models_count": len(updated_models),
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

        Filters out legacy models that are no longer relevant for comparison.

        Args:
            model: Discovered model to evaluate

        Returns:
            True if model should be included
        """
        # Include GPT-4, GPT-5 and newer models
        # Filter out GPT-3.5 and earlier (legacy)
        model_id_lower = model.model_id.lower()

        # Include if it's a GPT-4+ model
        if any(x in model_id_lower for x in ["gpt-4", "gpt-5", "o1", "o3"]):
            return True

        # Exclude GPT-3.5 and earlier
        if "gpt-3" in model_id_lower:
            return False

        # Include everything else (future models)
        return True

    def _has_capability_changes(
        self,
        manifest_model: ModelConfig,
        discovered_model: DiscoveredModel,
    ) -> bool:
        """Check if capabilities have changed between manifest and discovered model.

        Args:
            manifest_model: Model from manifest
            discovered_model: Model from API

        Returns:
            True if capabilities differ
        """
        # Convert manifest capabilities dict to set of strings
        manifest_caps = set(key for key, value in manifest_model.capabilities.items() if value)

        # Convert discovered capabilities list to set
        discovered_caps = set(discovered_model.capabilities)

        # Check if sets differ
        return manifest_caps != discovered_caps
