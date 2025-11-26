"""Unit tests for LPS centralized error handling pattern.

Validates the fix for double-jsonify bug (llm_routes.py:137):
- HuleEduError exceptions include provider/model in error details
- Centralized handler returns properly structured response
- Response uses libs factory (no double-jsonify TypeError)

Follows Rule 075 test creation methodology.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from common_core import Environment
from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.error_handling.quart_handlers import create_error_response
from pydantic import SecretStr
from quart import Quart
from quart.typing import TestClientProtocol
from quart_dishka import QuartDishka

from services.llm_provider_service.api.llm_routes import llm_bp
from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.protocols import LLMOrchestratorProtocol

# --- Test Data Builders ---


def create_test_settings() -> Settings:
    """Create Settings instance with minimal valid test values."""
    return Settings(
        SERVICE_NAME="llm_provider_service",
        ENVIRONMENT=Environment.DEVELOPMENT,
        ANTHROPIC_ENABLED=True,
        ANTHROPIC_API_KEY=SecretStr("sk-test"),
        OPENAI_ENABLED=False,
        OPENAI_API_KEY=SecretStr(""),
        GOOGLE_ENABLED=False,
        GOOGLE_API_KEY=SecretStr(""),
        OPENROUTER_ENABLED=False,
        OPENROUTER_API_KEY=SecretStr(""),
        USE_MOCK_LLM=False,
        ALLOW_MOCK_PROVIDER=True,
        REDIS_URL="redis://localhost:6379",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
    )


def create_error_detail_with_provider_model(
    error_code: ErrorCode = ErrorCode.EXTERNAL_SERVICE_ERROR,
    message: str = "Provider error",
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-20250514",
    correlation_id: UUID | None = None,
    extra_details: dict[str, Any] | None = None,
) -> ErrorDetail:
    """Create ErrorDetail with provider/model context in details dict."""
    details: dict[str, Any] = {"provider": provider, "model": model}
    if extra_details:
        details.update(extra_details)

    return ErrorDetail(
        error_code=error_code,
        message=message,
        correlation_id=correlation_id or uuid4(),
        timestamp=datetime.now(timezone.utc),
        service="llm_provider_service",
        operation="generate_comparison",
        details=details,
    )


# --- Fixtures ---


@pytest.fixture
def mock_tracer() -> MagicMock:
    """Create mock TraceContextManagerImpl for tracing."""
    mock = MagicMock(spec=TraceContextManagerImpl)
    mock.start_api_request_span.return_value.__enter__ = MagicMock()
    mock.start_api_request_span.return_value.__exit__ = MagicMock(return_value=False)
    mock.add_span_event = MagicMock()
    mock.set_span_attributes = MagicMock()
    return mock


@pytest.fixture
def mock_orchestrator() -> AsyncMock:
    """Create mock LLMOrchestratorProtocol."""
    return AsyncMock(spec=LLMOrchestratorProtocol)


@pytest.fixture
async def test_app_with_error_handler(
    mock_tracer: MagicMock,
    mock_orchestrator: AsyncMock,
) -> AsyncGenerator[tuple[TestClientProtocol, AsyncContainer, AsyncMock], None]:
    """Create Quart test app with error handler and DI container."""
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

    @test_app.errorhandler(HuleEduError)
    async def _handle_huleedu_error(error: HuleEduError) -> Any:
        return create_error_response(error.error_detail)

    test_app.register_blueprint(llm_bp, url_prefix="/api/v1")

    container = make_async_container(TestProvider())
    QuartDishka(app=test_app, container=container)

    async with test_app.test_client() as client:
        yield client, container, mock_orchestrator

    await container.close()


# --- Test Classes ---


class TestErrorResponseWithProviderModel:
    """Tests that error responses include provider/model from error details."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "provider,model",
        [
            ("anthropic", "claude-sonnet-4-20250514"),
            ("anthropic", "claude-haiku-3-5-20241022"),
            ("openrouter", "anthropic/claude-haiku-4-5-20251001"),
            ("mock", "mock-model-v1"),
        ],
        ids=["anthropic_sonnet", "anthropic_haiku", "openrouter", "mock"],
    )
    async def test_error_response_preserves_provider_and_model(
        self,
        test_app_with_error_handler: tuple[TestClientProtocol, AsyncContainer, AsyncMock],
        provider: str,
        model: str,
    ) -> None:
        """Verify provider/model from error details appear in response."""
        client, _, mock_orchestrator = test_app_with_error_handler

        correlation_id = uuid4()
        error_detail = create_error_detail_with_provider_model(
            provider=provider,
            model=model,
            correlation_id=correlation_id,
        )
        mock_orchestrator.perform_comparison.side_effect = HuleEduError(error_detail=error_detail)

        response = await client.post(
            "/api/v1/comparison",
            json={
                "user_prompt": "Compare essays",
                "callback_topic": "test.topic",
                "llm_config_overrides": {"provider_override": "anthropic"},
                "correlation_id": str(correlation_id),
            },
        )

        assert response.status_code in [400, 500, 502, 503]

        data: dict[str, Any] = await response.get_json()

        assert "error" in data
        error = data["error"]

        assert error["details"]["provider"] == provider
        assert error["details"]["model"] == model
        assert error["correlation_id"] == str(correlation_id)


class TestNoDoubleJsonify:
    """Tests verifying the double-jsonify bug is fixed."""

    @pytest.mark.asyncio
    async def test_error_response_is_valid_json_structure(
        self,
        test_app_with_error_handler: tuple[TestClientProtocol, AsyncContainer, AsyncMock],
    ) -> None:
        """Verify error response has proper JSON structure (not double-serialized)."""
        client, _, mock_orchestrator = test_app_with_error_handler

        correlation_id = uuid4()
        error_detail = create_error_detail_with_provider_model(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message="API rate limit exceeded",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            correlation_id=correlation_id,
            extra_details={"status_code": 429, "retry_after": 60},
        )
        mock_orchestrator.perform_comparison.side_effect = HuleEduError(error_detail=error_detail)

        response = await client.post(
            "/api/v1/comparison",
            json={
                "user_prompt": "Compare essays",
                "callback_topic": "test.topic",
                "llm_config_overrides": {"provider_override": "anthropic"},
                "correlation_id": str(correlation_id),
            },
        )

        assert response.status_code in [400, 500, 502, 503]

        data: dict[str, Any] = await response.get_json()

        assert data is not None
        assert isinstance(data, dict)
        assert "error" in data

        error = data["error"]

        assert "code" in error
        assert error["code"] == ErrorCode.EXTERNAL_SERVICE_ERROR.value
        assert error["message"] == "API rate limit exceeded"
        assert error["correlation_id"] == str(correlation_id)
        assert error["service"] == "llm_provider_service"
        assert "timestamp" in error

        assert "details" in error
        assert error["details"]["provider"] == "anthropic"
        assert error["details"]["model"] == "claude-sonnet-4-20250514"
        assert error["details"]["status_code"] == 429
        assert error["details"]["retry_after"] == 60
