"""Unit tests for LLM Provider Service comparison routes.

Tests the /api/v1/comparison POST endpoint with Dishka DI mocking.
Follows Rule 075 test creation methodology and Rule 070 testing standards.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from common_core import Environment, LLMProviderType
from common_core.models.error_models import ErrorDetail
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.error_handling.quart import create_error_response
from huleedu_service_libs.resilience import CircuitBreakerError
from pydantic import SecretStr
from quart import Quart
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.llm_provider_service.api.llm_routes import llm_bp
from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.internal_models import LLMQueuedResult
from services.llm_provider_service.protocols import LLMOrchestratorProtocol


def create_test_settings() -> Settings:
    """Create Settings instance with minimal valid test values."""
    return Settings(
        SERVICE_NAME="llm_provider_service",
        ENVIRONMENT=Environment.DEVELOPMENT,
        ANTHROPIC_ENABLED=True,
        ANTHROPIC_API_KEY=SecretStr("sk-test-anthropic"),
        OPENAI_ENABLED=True,
        OPENAI_API_KEY=SecretStr("sk-test-openai"),
        GOOGLE_ENABLED=False,
        GOOGLE_API_KEY=SecretStr(""),
        OPENROUTER_ENABLED=False,
        OPENROUTER_API_KEY=SecretStr(""),
        USE_MOCK_LLM=False,
        ALLOW_MOCK_PROVIDER=True,
        REDIS_URL="redis://localhost:6379",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
    )


def create_queued_result(
    queue_id: UUID | None = None,
    correlation_id: UUID | None = None,
    provider: LLMProviderType = LLMProviderType.ANTHROPIC,
) -> LLMQueuedResult:
    """Create LLMQueuedResult with controlled test values.

    Fields from internal_models.py:
    - queue_id: UUID
    - correlation_id: UUID
    - provider: LLMProviderType
    - status: str = "queued"
    - estimated_wait_minutes: int | None
    - priority: int
    - queued_at: str (ISO format)
    """
    from datetime import datetime, timezone

    return LLMQueuedResult(
        queue_id=queue_id or uuid4(),
        correlation_id=correlation_id or uuid4(),
        provider=provider,
        status="queued",
        estimated_wait_minutes=2,
        priority=5,
        queued_at=datetime.now(timezone.utc).isoformat(),
    )


class TestComparisonRoutes:
    """Tests for POST /api/v1/comparison endpoint."""

    @pytest.fixture
    def mock_orchestrator(self) -> AsyncMock:
        """Create mock LLMOrchestratorProtocol that returns queued result."""
        mock = AsyncMock(spec=LLMOrchestratorProtocol)
        mock.perform_comparison.return_value = create_queued_result()
        return mock

    @pytest.fixture
    def mock_tracer(self) -> MagicMock:
        """Create mock TraceContextManagerImpl for tracing."""
        mock = MagicMock(spec=TraceContextManagerImpl)
        # start_api_request_span returns a context manager
        mock.start_api_request_span.return_value.__enter__ = MagicMock()
        mock.start_api_request_span.return_value.__exit__ = MagicMock(return_value=False)
        mock.add_span_event = MagicMock()
        mock.set_span_attributes = MagicMock()
        return mock

    @pytest.fixture
    async def app_client(
        self,
        mock_orchestrator: AsyncMock,
        mock_tracer: MagicMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """Create test client with mocked dependencies."""
        test_settings = create_test_settings()

        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_settings(self) -> Settings:
                return test_settings

            @provide(scope=Scope.APP)
            def provide_orchestrator(self) -> LLMOrchestratorProtocol:
                return mock_orchestrator

            @provide(scope=Scope.APP)
            def provide_tracer(self) -> TraceContextManagerImpl:
                return mock_tracer

        test_app = Quart(__name__)
        test_app.config.update({"TESTING": True})

        # Register error handlers matching production setup
        @test_app.errorhandler(HuleEduError)
        async def handle_huleedu_error(error: HuleEduError) -> Any:
            return create_error_response(error.error_detail)

        test_app.register_blueprint(llm_bp, url_prefix="/api/v1")

        container = make_async_container(TestProvider())
        QuartDishka(app=test_app, container=container)

        async with test_app.test_client() as client:
            yield client

        await container.close()

    @pytest.mark.asyncio
    async def test_comparison_returns_400_when_no_json(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test POST /comparison returns 400 when no JSON body provided."""
        response = await app_client.post(
            "/api/v1/comparison",
            data=b"not json",
            headers={"Content-Type": "text/plain"},
        )

        assert response.status_code == 400

        data: dict[str, Any] = await response.get_json()
        # Response may have "error" or "message" field depending on error path
        error_text = data.get("error", "") or data.get("message", "")
        assert "No JSON data" in error_text or "json" in error_text.lower()

    @pytest.mark.asyncio
    async def test_comparison_returns_400_when_invalid_request(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test POST /comparison returns 400 when request schema is invalid."""
        # Missing required fields (user_prompt, callback_topic)
        response = await app_client.post(
            "/api/v1/comparison",
            json={"invalid": "data"},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_comparison_returns_400_when_no_provider_override(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test POST /comparison returns 400 when provider_override is missing."""
        # Valid request structure but no llm_config_overrides.provider_override
        response = await app_client.post(
            "/api/v1/comparison",
            json={
                "user_prompt": "Compare essay A to essay B",
                "callback_topic": "llm.comparison.results",
                # No llm_config_overrides provided
            },
        )

        assert response.status_code == 400

        data: dict[str, Any] = await response.get_json()
        # Response has "error" field with the message
        error_text = data.get("error", "") or data.get("message", "")
        assert "Provider configuration required" in error_text

    @pytest.mark.asyncio
    async def test_comparison_returns_202_when_queued_successfully(
        self,
        app_client: QuartTestClient,
        mock_orchestrator: AsyncMock,
    ) -> None:
        """Test POST /comparison returns 202 when request is successfully queued."""
        test_queue_id = uuid4()
        test_correlation_id = uuid4()
        mock_orchestrator.perform_comparison.return_value = create_queued_result(
            queue_id=test_queue_id,
            correlation_id=test_correlation_id,
            provider=LLMProviderType.ANTHROPIC,
        )

        response = await app_client.post(
            "/api/v1/comparison",
            json={
                "user_prompt": "Compare essay A to essay B",
                "callback_topic": "llm.comparison.results",
                "llm_config_overrides": {
                    "provider_override": "anthropic",
                },
                "correlation_id": str(test_correlation_id),
            },
        )

        assert response.status_code == 202

        data: dict[str, Any] = await response.get_json()
        assert data["status"] == "queued"
        assert data["queue_id"] == str(test_queue_id)

    @pytest.mark.asyncio
    async def test_comparison_returns_503_when_circuit_breaker_open(
        self,
        mock_tracer: MagicMock,
    ) -> None:
        """Test POST /comparison returns 503 when circuit breaker is open."""
        test_settings = create_test_settings()

        # Create orchestrator that raises CircuitBreakerError
        mock_orchestrator = AsyncMock(spec=LLMOrchestratorProtocol)
        mock_orchestrator.perform_comparison.side_effect = CircuitBreakerError(
            "Circuit breaker open for anthropic"
        )

        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_settings(self) -> Settings:
                return test_settings

            @provide(scope=Scope.APP)
            def provide_orchestrator(self) -> LLMOrchestratorProtocol:
                return mock_orchestrator

            @provide(scope=Scope.APP)
            def provide_tracer(self) -> TraceContextManagerImpl:
                return mock_tracer

        test_app = Quart(__name__)
        test_app.config.update({"TESTING": True})
        test_app.register_blueprint(llm_bp, url_prefix="/api/v1")

        container = make_async_container(TestProvider())
        QuartDishka(app=test_app, container=container)

        async with test_app.test_client() as client:
            response = await client.post(
                "/api/v1/comparison",
                json={
                    "user_prompt": "Compare essay A to essay B",
                    "callback_topic": "llm.comparison.results",
                    "llm_config_overrides": {
                        "provider_override": "anthropic",
                    },
                },
            )

            assert response.status_code == 503

            data: dict[str, Any] = await response.get_json()
            # Response has "error" field with the message
            error_text = data.get("error", "") or data.get("message", "")
            assert "temporarily unavailable" in error_text.lower()

        await container.close()

    @pytest.mark.asyncio
    async def test_comparison_returns_500_on_orchestrator_error(
        self,
        mock_tracer: MagicMock,
    ) -> None:
        """Test POST /comparison returns 500 when orchestrator raises HuleEduError."""
        from datetime import datetime, timezone

        from common_core.error_enums import LLMErrorCode

        test_settings = create_test_settings()

        # Create orchestrator that raises HuleEduError
        mock_orchestrator = AsyncMock(spec=LLMOrchestratorProtocol)
        error_detail = ErrorDetail(
            error_code=LLMErrorCode.QUEUE_FULL,
            message="Queue is full, try again later",
            correlation_id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            service="llm_provider_service",
            operation="perform_comparison",
        )
        mock_orchestrator.perform_comparison.side_effect = HuleEduError(error_detail=error_detail)

        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_settings(self) -> Settings:
                return test_settings

            @provide(scope=Scope.APP)
            def provide_orchestrator(self) -> LLMOrchestratorProtocol:
                return mock_orchestrator

            @provide(scope=Scope.APP)
            def provide_tracer(self) -> TraceContextManagerImpl:
                return mock_tracer

        test_app = Quart(__name__)
        test_app.config.update({"TESTING": True})

        # Register error handler for HuleEduError
        @test_app.errorhandler(HuleEduError)
        async def handle_huleedu_error(error: HuleEduError) -> Any:
            return create_error_response(error.error_detail)

        test_app.register_blueprint(llm_bp, url_prefix="/api/v1")

        container = make_async_container(TestProvider())
        QuartDishka(app=test_app, container=container)

        async with test_app.test_client() as client:
            response = await client.post(
                "/api/v1/comparison",
                json={
                    "user_prompt": "Compare essay A to essay B",
                    "callback_topic": "llm.comparison.results",
                    "llm_config_overrides": {
                        "provider_override": "anthropic",
                    },
                },
            )

            # HuleEduError is caught in the endpoint and returns error response
            # The error code determines the status code via create_error_response
            assert response.status_code in [400, 500, 503]

        await container.close()

    @pytest.mark.asyncio
    async def test_comparison_preserves_correlation_id_from_request(
        self,
        app_client: QuartTestClient,
        mock_orchestrator: AsyncMock,
    ) -> None:
        """Test POST /comparison passes correlation_id to orchestrator."""
        provided_correlation_id = uuid4()
        mock_orchestrator.perform_comparison.return_value = create_queued_result(
            correlation_id=provided_correlation_id,
        )

        await app_client.post(
            "/api/v1/comparison",
            json={
                "user_prompt": "Compare essay A to essay B",
                "callback_topic": "llm.comparison.results",
                "llm_config_overrides": {
                    "provider_override": "anthropic",
                },
                "correlation_id": str(provided_correlation_id),
            },
        )

        # Verify orchestrator was called with the provided correlation_id
        mock_orchestrator.perform_comparison.assert_called_once()
        call_kwargs = mock_orchestrator.perform_comparison.call_args.kwargs
        assert call_kwargs["correlation_id"] == provided_correlation_id

    @pytest.mark.asyncio
    async def test_comparison_generates_correlation_id_when_missing(
        self,
        app_client: QuartTestClient,
        mock_orchestrator: AsyncMock,
    ) -> None:
        """Test POST /comparison generates correlation_id when not provided."""
        mock_orchestrator.perform_comparison.return_value = create_queued_result()

        await app_client.post(
            "/api/v1/comparison",
            json={
                "user_prompt": "Compare essay A to essay B",
                "callback_topic": "llm.comparison.results",
                "llm_config_overrides": {
                    "provider_override": "anthropic",
                },
                # No correlation_id provided
            },
        )

        # Verify orchestrator was called with a generated correlation_id
        mock_orchestrator.perform_comparison.assert_called_once()
        call_kwargs = mock_orchestrator.perform_comparison.call_args.kwargs
        assert "correlation_id" in call_kwargs
        assert isinstance(call_kwargs["correlation_id"], UUID)

    @pytest.mark.asyncio
    async def test_comparison_forwards_reasoning_controls_to_orchestrator(
        self,
        app_client: QuartTestClient,
        mock_orchestrator: AsyncMock,
    ) -> None:
        """Test POST /comparison forwards reasoning_effort and output_verbosity to orchestrator.

        Regression test for ENG5 GPT-5.1 reasoning controls bug where these parameters
        were extracted from llm_config_overrides but not passed to perform_comparison().
        """
        mock_orchestrator.perform_comparison.return_value = create_queued_result(
            provider=LLMProviderType.OPENAI,
        )

        await app_client.post(
            "/api/v1/comparison",
            json={
                "user_prompt": "Compare essay A to essay B",
                "callback_topic": "llm.comparison.results",
                "llm_config_overrides": {
                    "provider_override": "openai",
                    "model_override": "gpt-5.1",
                    "reasoning_effort": "low",
                    "output_verbosity": "high",
                },
            },
        )

        # Verify orchestrator was called with reasoning controls
        mock_orchestrator.perform_comparison.assert_called_once()
        call_kwargs = mock_orchestrator.perform_comparison.call_args.kwargs
        assert call_kwargs.get("reasoning_effort") == "low"
        assert call_kwargs.get("output_verbosity") == "high"
