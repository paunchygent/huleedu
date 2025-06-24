"""Tests for Batch Conductor Service pipeline resolution endpoint."""

from __future__ import annotations

from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.batch_conductor_service.api_models import (
    BCSPipelineDefinitionRequestV1,
    BCSPipelineDefinitionResponseV1,
)
from services.batch_conductor_service.app import app
from services.batch_conductor_service.protocols import (
    DlqProducerProtocol,
    PipelineResolutionServiceProtocol,
)


@pytest.fixture
def mock_pipeline_resolution_service() -> AsyncMock:
    """
    Create a mock of the PipelineResolutionServiceProtocol.
    This is the primary external boundary we want to control for these API tests.
    """
    return AsyncMock(spec=PipelineResolutionServiceProtocol)


@pytest.fixture
def mock_dlq_producer() -> AsyncMock:
    """
    Create a mock of the DlqProducerProtocol.
    The endpoint injects this, so we must provide a mock for it in our test container.
    """
    return AsyncMock(spec=DlqProducerProtocol)


@pytest.fixture
async def app_client(
    mock_pipeline_resolution_service: AsyncMock, mock_dlq_producer: AsyncMock
) -> AsyncGenerator[QuartTestClient, None]:
    """
    Return a Quart test client configured with mocked dependencies using Dishka.

    This fixture correctly overrides the production providers with test providers
    that supply our mocks. This is the standard way to test DI-based applications.
    """

    # 1. Define a test-specific provider that provides our mocks
    class TestProvider(Provider):
        @provide(scope=Scope.APP)
        def provide_mock_pipeline_service(self) -> PipelineResolutionServiceProtocol:
            return mock_pipeline_resolution_service

        @provide(scope=Scope.APP)
        def provide_mock_dlq_producer(self) -> DlqProducerProtocol:
            return mock_dlq_producer

    # 2. Create a new container with our test provider
    container = make_async_container(TestProvider())

    # 3. Apply the container to the app instance for the test
    app.config.update({"TESTING": True})
    QuartDishka(app=app, container=container)

    async with app.test_client() as client:
        yield client

    # 4. Clean up the container after the test
    await container.close()


class TestPipelineResolutionAPI:
    """Validate /internal/v1/pipelines/define endpoint."""

    async def test_pipeline_resolution_success(
        self, app_client: QuartTestClient, mock_pipeline_resolution_service: AsyncMock
    ) -> None:
        """Test successful pipeline resolution with valid input (Happy Path)."""
        # Arrange
        payload = {"batch_id": "batch_001", "requested_pipeline": "ai_feedback"}
        expected_pipeline = ["spellcheck", "nlp", "ai_feedback"]
        mock_response = BCSPipelineDefinitionResponseV1(
            batch_id=payload["batch_id"],
            final_pipeline=expected_pipeline,
            analysis_summary="Test analysis summary",
        )
        mock_pipeline_resolution_service.resolve_pipeline_request.return_value = mock_response

        # Act
        response = await app_client.post("/internal/v1/pipelines/define", json=payload)
        data = await response.get_json()

        # Assert
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "application/json"
        assert data == {
            "batch_id": payload["batch_id"],
            "final_pipeline": expected_pipeline,
            "analysis_summary": mock_response.analysis_summary,
        }

        # Verify service call
        mock_pipeline_resolution_service.resolve_pipeline_request.assert_called_once()
        call_args = mock_pipeline_resolution_service.resolve_pipeline_request.call_args[0]
        assert isinstance(call_args[0], BCSPipelineDefinitionRequestV1)
        assert call_args[0].batch_id == payload["batch_id"]
        assert call_args[0].requested_pipeline == payload["requested_pipeline"]

    @pytest.mark.parametrize(
        "payload, expected_error_part",
        [
            ({"batch_id": "batch_002"}, "Field required"),  # Missing requested_pipeline
            ({"requested_pipeline": "ai_feedback"}, "Field required"),  # Missing batch_id
            (
                {"batch_id": "", "requested_pipeline": "ai_feedback"},
                "String should have at least 1 character",
            ),  # Empty batch_id
            (
                {"batch_id": "batch_001", "requested_pipeline": 123},
                "Input should be a valid string",
            ),  # Invalid type
        ],
    )
    async def test_pipeline_resolution_validation_errors(
        self, app_client: QuartTestClient, payload: dict[str, Any], expected_error_part: str
    ) -> None:
        """Test validation errors for various invalid payloads."""
        # Act
        response = await app_client.post("/internal/v1/pipelines/define", json=payload)
        data = await response.get_json()

        # Assert
        assert response.status_code == 400
        assert response.headers["Content-Type"] == "application/json"
        assert "detail" in data
        assert any(expected_error_part in error["msg"] for error in data["detail"])

    async def test_pipeline_not_found(
        self, app_client: QuartTestClient, mock_pipeline_resolution_service: AsyncMock
    ) -> None:
        """Test handling of a pipeline resolution that fails because the pipeline is unknown."""
        # Arrange
        payload = {"batch_id": "batch_003", "requested_pipeline": "nonexistent"}
        mock_response = BCSPipelineDefinitionResponseV1(
            batch_id="batch_003",
            final_pipeline=[],
            analysis_summary="Pipeline resolution failed: Unknown pipeline: 'nonexistent'",
        )
        mock_pipeline_resolution_service.resolve_pipeline_request.return_value = mock_response

        # Act
        response = await app_client.post("/internal/v1/pipelines/define", json=payload)
        data = await response.get_json()

        # Assert
        assert response.status_code == 400
        assert response.headers["Content-Type"] == "application/json"
        assert "error" in data
        assert data["detail"] == "Pipeline resolution failed: Unknown pipeline: 'nonexistent'"

    async def test_dlq_producer_on_service_exception(
        self,
        app_client: QuartTestClient,
        mock_pipeline_resolution_service: AsyncMock,
        mock_dlq_producer: AsyncMock,
    ) -> None:
        """Test that a generic exception from the service layer returns a 500 and calls the DLQ."""
        # Arrange
        payload = {"batch_id": "batch_004", "requested_pipeline": "ai_feedback"}
        error_message = "Internal service error"
        mock_pipeline_resolution_service.resolve_pipeline_request.side_effect = Exception(
            error_message
        )

        # Act
        response = await app_client.post("/internal/v1/pipelines/define", json=payload)
        data = await response.get_json()

        # Assert
        assert response.status_code == 500
        assert data == {"error": "Internal server error"}
        

    async def test_pipeline_resolution_invalid_method(self, app_client: QuartTestClient) -> None:
        """Test that only POST method is allowed."""
        # Act
        response = await app_client.get("/internal/v1/pipelines/define")

        # Assert
        assert response.status_code == 405
        assert "Allow" in response.headers
        assert "POST" in response.headers["Allow"]
