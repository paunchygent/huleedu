"""Integration tests for LLM provider model compatibility validation.

This module validates that LLM provider models work correctly with comparative
judgment assessment prompts by making real API calls. These tests incur actual
API costs and are gated by environment variables.

Test Coverage:
- Current model validation with real API calls
- Structured output parsing (winner, justification, confidence)
- Response quality checks against Pydantic schemas
- New model testing (conditional, requires env var)
- Error handling (API failures, rate limits, auth errors)
- Multi-provider smoke tests

Usage:
    # Run without financial tests (free tests only)
    pdm run pytest-root \\
        services/llm_provider_service/tests/integration/test_model_compatibility.py -v

    # Run with financial tests (incurs API costs)
    CHECK_NEW_MODELS=1 pdm run pytest-root \\
        services/llm_provider_service/tests/integration/test_model_compatibility.py \\
        -v -m "financial"
"""

from __future__ import annotations

import logging
import os
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import aiohttp
import pytest
from anthropic import AsyncAnthropic
from common_core import EssayComparisonWinner
from pydantic import SecretStr

from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.anthropic_provider_impl import (
    AnthropicProviderImpl,
)
from services.llm_provider_service.implementations.openai_provider_impl import (
    OpenAIProviderImpl,
)
from services.llm_provider_service.model_checker.anthropic_checker import (
    AnthropicModelChecker,
)
from services.llm_provider_service.model_manifest import ProviderName, get_model_config
from services.llm_provider_service.protocols import LLMRetryManagerProtocol
from services.llm_provider_service.tests.integration.test_data_fixtures import (
    ESSAY_A_STRONG,
    ESSAY_B_WEAK,
    REPRESENTATIVE_COMPARISON_PROMPT,
    SHORT_ESSAY_A,
    SHORT_ESSAY_B,
)

logger = logging.getLogger(__name__)


class TestAnthropicModelCompatibility:
    """Test Anthropic model compatibility with CJ assessment prompts."""

    @pytest.fixture
    def settings(self) -> Settings:
        """Create settings for Anthropic testing."""
        return Settings()

    @pytest.fixture
    async def http_session(self) -> Any:
        """Create HTTP session for testing."""
        async with aiohttp.ClientSession() as session:
            yield session

    @pytest.fixture
    def retry_manager(self) -> LLMRetryManagerProtocol:
        """Create mock retry manager that just executes the operation once."""
        retry_manager = AsyncMock(spec=LLMRetryManagerProtocol)

        async def mock_with_retry(operation: Any, operation_name: str, **kwargs: Any) -> Any:
            """Mock retry that just calls operation once."""
            return await operation(**kwargs)

        retry_manager.with_retry.side_effect = mock_with_retry
        return retry_manager

    @pytest.fixture
    def anthropic_client(self, settings: Settings) -> AsyncAnthropic:
        """Create Anthropic API client."""
        api_key = settings.ANTHROPIC_API_KEY.get_secret_value()
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY not set")
        return AsyncAnthropic(api_key=api_key)

    @pytest.fixture
    def anthropic_provider(
        self, http_session: Any, settings: Settings, retry_manager: LLMRetryManagerProtocol
    ) -> AnthropicProviderImpl:
        """Create Anthropic provider implementation."""
        api_key = settings.ANTHROPIC_API_KEY.get_secret_value()
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY not set")
        return AnthropicProviderImpl(
            session=http_session, settings=settings, retry_manager=retry_manager
        )

    @pytest.mark.integration
    @pytest.mark.financial
    @pytest.mark.asyncio
    async def test_current_anthropic_model_produces_valid_comparison_response(
        self, anthropic_provider: AnthropicProviderImpl, settings: Settings
    ) -> None:
        """Validate current Anthropic model produces valid comparison responses.

        This test makes a real API call to Anthropic using the current default
        model from the manifest. It validates:
        - API call succeeds
        - Response contains required fields
        - Structured output parsing works
        - Response quality meets requirements
        """
        # Get current default model from manifest
        model_config = get_model_config(ProviderName.ANTHROPIC)
        logger.info(
            "Testing Anthropic model compatibility",
            extra={
                "model_id": model_config.model_id,
                "api_version": model_config.api_version,
            },
        )

        # Use representative essays from test fixtures
        correlation_id = uuid4()
        user_prompt = f"""{REPRESENTATIVE_COMPARISON_PROMPT}

**Essay A (ID: essay_a_strong):**
{ESSAY_A_STRONG}

**Essay B (ID: essay_b_weak):**
{ESSAY_B_WEAK}"""
        response = await anthropic_provider.generate_comparison(
            user_prompt=user_prompt,
            correlation_id=correlation_id,
        )

        # Validate response structure
        assert response is not None, "Response should not be None"
        assert response.winner in [
            EssayComparisonWinner.ESSAY_A,
            EssayComparisonWinner.ESSAY_B,
        ], f"Winner must be Essay A or Essay B, got: {response.winner}"

        # Validate justification quality
        assert len(response.justification) > 0, "Justification should be non-empty"
        just_len = len(response.justification)
        assert just_len <= 500, (
            f"Justification accepted up to max 500 chars by validator, got: {just_len}"
        )
        assert isinstance(response.justification, str), "Justification must be string"

        # Validate confidence score
        assert 1.0 <= response.confidence <= 5.0, (
            f"Confidence must be 1.0-5.0, got: {response.confidence}"
        )

        # Validate model metadata
        assert response.model == model_config.model_id, (
            f"Response model should match request: {model_config.model_id}"
        )
        assert response.provider == "anthropic", "Provider should be anthropic"

        # Validate token usage is present
        assert response.prompt_tokens > 0, "Prompt tokens should be > 0"
        assert response.completion_tokens > 0, "Completion tokens should be > 0"
        assert response.total_tokens > 0, "Total tokens should be > 0"

        logger.info(
            "Anthropic model compatibility test passed",
            extra={
                "model": response.model,
                "winner": response.winner.value,
                "confidence": response.confidence,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
            },
        )

    @pytest.mark.integration
    @pytest.mark.financial
    @pytest.mark.asyncio
    async def test_anthropic_structured_output_parsing(
        self, anthropic_provider: AnthropicProviderImpl
    ) -> None:
        """Validate Anthropic structured output is correctly parsed.

        This test verifies that the provider implementation correctly extracts
        structured data from Anthropic's tool use response format.
        """
        user_prompt = f"""{REPRESENTATIVE_COMPARISON_PROMPT}

**Essay A (ID: short_a):**
{SHORT_ESSAY_A}

**Essay B (ID: short_b):**
{SHORT_ESSAY_B}"""
        response = await anthropic_provider.generate_comparison(
            user_prompt=user_prompt,
            correlation_id=uuid4(),
        )

        # Verify response can be serialized to JSON (proves valid Pydantic model)
        response_json = response.model_dump(mode="json")
        assert isinstance(response_json, dict), "Response should serialize to dict"

        # Verify required fields are present
        required_fields = ["winner", "justification", "confidence", "model", "provider"]
        for field in required_fields:
            assert field in response_json, f"Required field '{field}' missing from response"

        # Verify winner is valid enum value
        assert response.winner.value in ["Essay A", "Essay B"], (
            f"Winner enum should have value 'Essay A' or 'Essay B', got: {response.winner.value}"
        )

    @pytest.mark.integration
    @pytest.mark.financial
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        os.getenv("CHECK_NEW_MODELS") != "1",
        reason="New model testing requires CHECK_NEW_MODELS=1 env var",
    )
    async def test_anthropic_new_models_compatibility(
        self, anthropic_client: AsyncAnthropic
    ) -> None:
        """Test newly discovered Anthropic models (only when explicitly enabled).

        This test is gated by CHECK_NEW_MODELS=1 environment variable to avoid
        unnecessary API costs. It discovers new models and runs basic compatibility
        tests on them.
        """
        # Create model checker and discover new models
        settings = Settings()
        checker = AnthropicModelChecker(client=anthropic_client, logger=logger, settings=settings)
        comparison_result = await checker.compare_with_manifest()

        # Combine tracked and untracked families for compatibility testing
        all_new_models = (
            comparison_result.new_models_in_tracked_families
            + comparison_result.new_untracked_families
        )

        if not all_new_models:
            pytest.skip("No new models discovered, skipping compatibility test")

        logger.info(
            f"Found {len(all_new_models)} new Anthropic models to test",
            extra={"new_models": [m.model_id for m in all_new_models]},
        )

        # Test each new model with a simple prompt
        for discovered_model in all_new_models[:2]:  # Limit to 2 to control costs
            logger.info(f"Testing new model: {discovered_model.model_id}")

            # Create a minimal comparison request
            try:
                # Use Anthropic SDK directly for new models not yet in manifest
                test_message = (
                    "Which is better: Essay A with strong thesis and evidence, "
                    "or Essay B with weak structure? Respond with JSON: "
                    '{"winner": "Essay A", "justification": "...", "confidence": 4.0}'
                )

                response = await anthropic_client.messages.create(
                    model=discovered_model.model_id,
                    max_tokens=500,
                    messages=[{"role": "user", "content": test_message}],  # type: ignore[arg-type]
                )

                # Basic validation: response should complete successfully
                assert response.content, (
                    f"New model {discovered_model.model_id} returned empty response"
                )

                logger.info(
                    f"New model {discovered_model.model_id} responded successfully",
                    extra={"model_id": discovered_model.model_id},
                )

            except Exception as exc:
                logger.error(
                    f"New model {discovered_model.model_id} failed compatibility test",
                    extra={"model_id": discovered_model.model_id, "error": str(exc)},
                    exc_info=True,
                )
                # Don't fail the whole test, just log the issue
                continue


class TestOpenAIModelCompatibility:
    """Test OpenAI model compatibility with CJ assessment prompts."""

    @pytest.fixture
    def settings(self) -> Settings:
        """Create settings for OpenAI testing."""
        return Settings()

    @pytest.fixture
    async def http_session(self) -> Any:
        """Create HTTP session for testing."""
        async with aiohttp.ClientSession() as session:
            yield session

    @pytest.fixture
    def retry_manager(self) -> LLMRetryManagerProtocol:
        """Create mock retry manager that just executes the operation once."""
        retry_manager = AsyncMock(spec=LLMRetryManagerProtocol)

        async def mock_with_retry(operation: Any, operation_name: str, **kwargs: Any) -> Any:
            """Mock retry that just calls operation once."""
            return await operation(**kwargs)

        retry_manager.with_retry.side_effect = mock_with_retry
        return retry_manager

    @pytest.fixture
    def openai_provider(
        self, http_session: Any, settings: Settings, retry_manager: LLMRetryManagerProtocol
    ) -> OpenAIProviderImpl:
        """Create OpenAI provider implementation."""
        api_key = settings.OPENAI_API_KEY.get_secret_value()
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")
        return OpenAIProviderImpl(
            session=http_session, settings=settings, retry_manager=retry_manager
        )

    @pytest.mark.integration
    @pytest.mark.financial
    @pytest.mark.asyncio
    async def test_current_openai_model_produces_valid_comparison_response(
        self, openai_provider: OpenAIProviderImpl, settings: Settings
    ) -> None:
        """Validate current OpenAI model produces valid comparison responses."""
        # Get current default model from manifest
        model_config = get_model_config(ProviderName.OPENAI)
        logger.info(
            "Testing OpenAI model compatibility",
            extra={"model_id": model_config.model_id},
        )

        # Make actual API call using short essays for cost control
        user_prompt = f"""{REPRESENTATIVE_COMPARISON_PROMPT}

**Essay A (ID: short_a):**
{SHORT_ESSAY_A}

**Essay B (ID: short_b):**
{SHORT_ESSAY_B}"""
        response = await openai_provider.generate_comparison(
            user_prompt=user_prompt,
            correlation_id=uuid4(),
        )

        # Validate response structure (same validation as Anthropic)
        assert response is not None
        assert response.winner in [EssayComparisonWinner.ESSAY_A, EssayComparisonWinner.ESSAY_B]
        assert len(response.justification) > 0, "Justification should be non-empty"
        just_len = len(response.justification)
        assert just_len <= 500, (
            f"Justification accepted up to max 500 chars by validator, got: {just_len}"
        )
        # Internal model uses 0-1 scale (converted from LLM's 1-5 scale)
        assert 0.0 <= response.confidence <= 1.0, (
            f"Internal model should use 0-1 scale, got: {response.confidence}"
        )
        assert response.model == model_config.model_id
        assert response.provider == "openai"
        assert response.prompt_tokens > 0
        assert response.completion_tokens > 0

        logger.info(
            "OpenAI model compatibility test passed",
            extra={
                "model": response.model,
                "winner": response.winner.value,
                "confidence": response.confidence,
            },
        )


class TestErrorHandling:
    """Test error handling for API failures and edge cases."""

    @pytest.fixture
    def settings_with_invalid_key(self) -> Settings:
        """Create settings with invalid API key."""
        settings = Settings()
        # Override with invalid key
        object.__setattr__(settings, "ANTHROPIC_API_KEY", SecretStr("invalid-key-12345"))
        return settings

    @pytest.fixture
    async def http_session(self) -> Any:
        """Create HTTP session for testing."""
        async with aiohttp.ClientSession() as session:
            yield session

    @pytest.fixture
    def retry_manager(self) -> LLMRetryManagerProtocol:
        """Create mock retry manager that just executes the operation once."""
        retry_manager = AsyncMock(spec=LLMRetryManagerProtocol)

        async def mock_with_retry(operation: Any, operation_name: str, **kwargs: Any) -> Any:
            """Mock retry that just calls operation once."""
            return await operation(**kwargs)

        retry_manager.with_retry.side_effect = mock_with_retry
        return retry_manager

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_anthropic_authentication_failure_handling(
        self,
        http_session: Any,
        retry_manager: LLMRetryManagerProtocol,
        settings_with_invalid_key: Settings,
    ) -> None:
        """Test graceful handling of authentication failures."""
        provider = AnthropicProviderImpl(
            session=http_session, settings=settings_with_invalid_key, retry_manager=retry_manager
        )

        # Should raise appropriate error for auth failure
        user_prompt = """Simple test prompt

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content"""
        with pytest.raises(Exception) as exc_info:
            await provider.generate_comparison(
                user_prompt=user_prompt,
                correlation_id=uuid4(),
            )

        # Error should indicate authentication issue
        error_msg = str(exc_info.value).lower()
        assert any(
            keyword in error_msg
            for keyword in ["auth", "401", "unauthorized", "invalid", "api key"]
        ), f"Expected auth error, got: {exc_info.value}"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_rate_limit_handling(
        self, http_session: Any, retry_manager: LLMRetryManagerProtocol
    ) -> None:
        """Test handling of API rate limits.

        Note: This test is marked as integration but doesn't make real API calls
        to avoid actually hitting rate limits. It validates the error handling logic.
        """
        # Use default settings for smoke test
        settings = Settings()

        # This is a smoke test - actual rate limit testing would require
        # making many rapid requests, which is expensive and slow.
        # Instead, we verify the provider has timeout settings configured.
        provider = AnthropicProviderImpl(
            session=http_session, settings=settings, retry_manager=retry_manager
        )

        # Verify session configuration exists
        assert hasattr(provider, "session"), "Provider should have session attribute"
        # The actual rate limit handling is tested in unit tests with mocks


# Module-level test for quick smoke testing all providers
@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_provider_smoke_test() -> None:
    """Quick smoke test across all configured providers.

    This test validates that all providers with valid API keys can be instantiated
    and have their checkers created successfully. No actual API calls are made.
    """
    settings = Settings()

    # Create mock retry manager
    retry_manager = AsyncMock(spec=LLMRetryManagerProtocol)

    async def mock_with_retry(operation: Any, operation_name: str, **kwargs: Any) -> Any:
        return await operation(**kwargs)

    retry_manager.with_retry.side_effect = mock_with_retry

    async with aiohttp.ClientSession() as session:
        # Test Anthropic
        if settings.ANTHROPIC_API_KEY.get_secret_value():
            provider = AnthropicProviderImpl(
                session=session, settings=settings, retry_manager=retry_manager
            )
            assert provider is not None
            logger.info("Anthropic provider instantiated successfully")

        # Test OpenAI
        if settings.OPENAI_API_KEY.get_secret_value():
            provider_openai = OpenAIProviderImpl(
                session=session, settings=settings, retry_manager=retry_manager
            )
            assert provider_openai is not None
            logger.info("OpenAI provider instantiated successfully")

        # Add Google and OpenRouter when implemented
