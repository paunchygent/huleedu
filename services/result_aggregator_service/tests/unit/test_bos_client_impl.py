"""Unit tests for BatchOrchestratorClientImpl."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, Mock

import aiohttp
import pytest

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.implementations.bos_client_impl import (
    BatchOrchestratorClientImpl,
)


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        SERVICE_NAME="test_aggregator",
        BOS_URL="http://test-bos:8000",
        BOS_TIMEOUT_SECONDS=5,
    )


@pytest.fixture
def mock_http_session() -> AsyncMock:
    """Create mock HTTP session for BOS client."""
    return AsyncMock(spec=aiohttp.ClientSession)


@pytest.fixture
def bos_client(mock_http_session: AsyncMock, settings: Settings) -> BatchOrchestratorClientImpl:
    """Create BOS client with mocked session."""
    return BatchOrchestratorClientImpl(settings, mock_http_session)


def create_mock_bos_response(
    status: int = 200,
    data: Optional[Dict[str, Any]] = None,
    raise_error: Optional[Exception] = None,
) -> AsyncMock:
    """Factory for BOS HTTP response mocks."""
    if raise_error:
        mock_context = AsyncMock()
        mock_context.__aenter__.side_effect = raise_error
        return mock_context

    response = AsyncMock()
    response.status = status
    response.json.return_value = data or {}
    
    # Configure raise_for_status behavior (it's a sync method in aiohttp)
    response.raise_for_status = Mock()
    if status >= 400 and status != 404:  # 404 is handled before raise_for_status is called
        response.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=status
        )
    else:
        response.raise_for_status.return_value = None

    mock_context = AsyncMock()
    mock_context.__aenter__.return_value = response
    mock_context.__aexit__.return_value = None
    return mock_context


def create_mock_bos_pipeline_state(
    batch_id: str = "test-batch",
    user_id: str = "test-user",
    override_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Create realistic BOS ProcessingPipelineState data."""
    return {
        "batch_id": batch_id,
        "user_id": user_id,
        "requested_pipelines": ["spellcheck", "cj_assessment"],
        "spellcheck": {
            "status": override_status or "COMPLETED_SUCCESSFULLY",
            "essay_counts": {"total": 3, "successful": 3, "failed": 0},
            "started_at": "2024-01-01T10:00:00Z",
            "completed_at": "2024-01-01T10:05:00Z",
        },
        "cj_assessment": {
            "status": override_status or "IN_PROGRESS",
            "essay_counts": {"total": 3, "successful": 2, "failed": 0},
            "started_at": "2024-01-01T10:05:00Z",
            "completed_at": None,
        },
        "last_updated": "2024-01-01T10:06:00Z",
    }


class TestBatchOrchestratorClientImpl:
    """Test cases for BOS client implementation."""

    async def test_get_pipeline_state_success(
        self,
        bos_client: BatchOrchestratorClientImpl,
        mock_http_session: AsyncMock,
    ) -> None:
        """Test successful pipeline state retrieval."""
        # Arrange
        batch_id = "test-batch-123"
        expected_data = create_mock_bos_pipeline_state(batch_id=batch_id)

        mock_response = create_mock_bos_response(status=200, data=expected_data)
        mock_http_session.get.return_value = mock_response

        # Act
        result = await bos_client.get_pipeline_state(batch_id)

        # Assert
        assert result is not None
        assert result["batch_id"] == batch_id
        assert "spellcheck" in result
        assert "cj_assessment" in result
        assert result["user_id"] == "test-user"

        # Verify HTTP call
        mock_http_session.get.assert_called_once()
        call_args = mock_http_session.get.call_args
        expected_url = f"{bos_client.settings.BOS_URL}/internal/v1/batches/{batch_id}/pipeline-state"
        assert call_args[0][0] == expected_url

        # Verify timeout configuration
        timeout_arg = call_args.kwargs.get("timeout")
        assert timeout_arg is not None
        assert timeout_arg.total == bos_client.settings.BOS_TIMEOUT_SECONDS

    async def test_get_pipeline_state_404_not_found(
        self,
        bos_client: BatchOrchestratorClientImpl,
        mock_http_session: AsyncMock,
    ) -> None:
        """Test 404 response handling (batch not found in BOS)."""
        # Arrange
        batch_id = "nonexistent-batch"
        mock_response = create_mock_bos_response(status=404)
        mock_http_session.get.return_value = mock_response

        # Act
        result = await bos_client.get_pipeline_state(batch_id)

        # Assert
        assert result is None
        mock_http_session.get.assert_called_once()

    async def test_get_pipeline_state_http_error_500(
        self,
        bos_client: BatchOrchestratorClientImpl,
        mock_http_session: AsyncMock,
    ) -> None:
        """Test HTTP 500 error handling."""
        # Arrange
        batch_id = "test-batch"
        mock_response = create_mock_bos_response(status=500)
        mock_http_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(aiohttp.ClientResponseError):
            await bos_client.get_pipeline_state(batch_id)

        mock_http_session.get.assert_called_once()

    async def test_get_pipeline_state_timeout_error(
        self,
        bos_client: BatchOrchestratorClientImpl,
        mock_http_session: AsyncMock,
    ) -> None:
        """Test timeout handling."""
        # Arrange
        batch_id = "test-batch"
        mock_response = create_mock_bos_response(raise_error=asyncio.TimeoutError())
        mock_http_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(asyncio.TimeoutError):
            await bos_client.get_pipeline_state(batch_id)

        mock_http_session.get.assert_called_once()

    async def test_get_pipeline_state_network_error(
        self,
        bos_client: BatchOrchestratorClientImpl,
        mock_http_session: AsyncMock,
    ) -> None:
        """Test network error handling."""
        # Arrange
        batch_id = "test-batch"
        network_error = aiohttp.ClientConnectionError("Connection refused")
        mock_response = create_mock_bos_response(raise_error=network_error)
        mock_http_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(aiohttp.ClientConnectionError):
            await bos_client.get_pipeline_state(batch_id)

        mock_http_session.get.assert_called_once()

    async def test_get_pipeline_state_invalid_json_response(
        self,
        bos_client: BatchOrchestratorClientImpl,
        mock_http_session: AsyncMock,
    ) -> None:
        """Test invalid JSON response handling."""
        # Arrange
        batch_id = "test-batch"

        # Create a response that raises when .json() is called
        response = AsyncMock()
        response.status = 200
        response.json.side_effect = ValueError("Invalid JSON")
        response.raise_for_status = AsyncMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = response
        mock_http_session.get.return_value = mock_context

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid JSON"):
            await bos_client.get_pipeline_state(batch_id)

        mock_http_session.get.assert_called_once()

    async def test_get_pipeline_state_http_403_error(
        self,
        bos_client: BatchOrchestratorClientImpl,
        mock_http_session: AsyncMock,
    ) -> None:
        """Test HTTP 403 error handling."""
        # Arrange
        batch_id = "test-batch"
        mock_response = create_mock_bos_response(status=403)
        mock_http_session.get.return_value = mock_response

        # Act & Assert
        with pytest.raises(aiohttp.ClientResponseError):
            await bos_client.get_pipeline_state(batch_id)

        mock_http_session.get.assert_called_once()

    async def test_get_pipeline_state_empty_response_data(
        self,
        bos_client: BatchOrchestratorClientImpl,
        mock_http_session: AsyncMock,
    ) -> None:
        """Test handling of empty but valid JSON response."""
        # Arrange
        batch_id = "test-batch"
        empty_data: Dict[str, Any] = {}
        mock_response = create_mock_bos_response(status=200, data=empty_data)
        mock_http_session.get.return_value = mock_response

        # Act
        result = await bos_client.get_pipeline_state(batch_id)

        # Assert
        assert result == {}
        mock_http_session.get.assert_called_once()

    async def test_get_pipeline_state_url_construction(
        self,
        bos_client: BatchOrchestratorClientImpl,
        mock_http_session: AsyncMock,
    ) -> None:
        """Test correct URL construction for different batch IDs."""
        # Arrange
        batch_id = "complex-batch-id-with-special-chars"
        expected_data = create_mock_bos_pipeline_state(batch_id=batch_id)
        mock_response = create_mock_bos_response(status=200, data=expected_data)
        mock_http_session.get.return_value = mock_response

        # Act
        await bos_client.get_pipeline_state(batch_id)

        # Assert
        call_args = mock_http_session.get.call_args
        expected_url = (
            f"{bos_client.settings.BOS_URL}/internal/v1/batches/"
            f"{batch_id}/pipeline-state"
        )
        assert call_args[0][0] == expected_url

    async def test_get_pipeline_state_partial_pipeline_data(
        self,
        bos_client: BatchOrchestratorClientImpl,
        mock_http_session: AsyncMock,
    ) -> None:
        """Test handling of response with only partial pipeline data."""
        # Arrange
        batch_id = "test-batch"
        partial_data = {
            "batch_id": batch_id,
            "user_id": "test-user",
            "requested_pipelines": ["spellcheck"],
            "spellcheck": {
                "status": "COMPLETED_SUCCESSFULLY",
                "essay_counts": {"total": 2, "successful": 2, "failed": 0},
                "started_at": "2024-01-01T10:00:00Z",
                "completed_at": "2024-01-01T10:05:00Z",
            },
            "last_updated": "2024-01-01T10:06:00Z",
        }

        mock_response = create_mock_bos_response(status=200, data=partial_data)
        mock_http_session.get.return_value = mock_response

        # Act
        result = await bos_client.get_pipeline_state(batch_id)

        # Assert
        assert result is not None
        assert result["batch_id"] == batch_id
        assert "spellcheck" in result
        assert "cj_assessment" not in result  # Only spellcheck pipeline present
        assert len(result["requested_pipelines"]) == 1

        mock_http_session.get.assert_called_once()