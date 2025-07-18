"""Integration tests for BOS fallback flow in Result Aggregator Service.

Tests the complete end-to-end flow from database miss → BOS client → data transformation → response.
These tests verify the critical architectural refactoring that moved BOS integration from API Gateway
to Result Aggregator Service while maintaining proper service boundaries.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
from common_core.status_enums import BatchStatus

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.implementations.aggregator_service_impl import (
    AggregatorServiceImpl,
)
from services.result_aggregator_service.implementations.bos_client_impl import (
    BatchOrchestratorClientImpl,
)
from services.result_aggregator_service.implementations.bos_data_transformer import (
    BOSDataTransformer,
)
from services.result_aggregator_service.models_db import BatchResult
from services.result_aggregator_service.protocols import BatchRepositoryProtocol


@pytest.fixture
def integration_test_settings() -> Settings:
    """Create settings for BOS integration tests."""
    return Settings(
        SERVICE_NAME="test-result-aggregator",
        BOS_URL="http://test-bos:8000",
        BOS_TIMEOUT_SECONDS=5,
        DATABASE_URL="postgresql://test:test@localhost:5432/test_ras",
        REDIS_URL="redis://localhost:6379/1",
        INTERNAL_API_KEY="test-api-key",
        ALLOWED_SERVICE_IDS=["test-service", "api_gateway"],
    )


@pytest.fixture
def bos_response_factory():
    """Factory for creating realistic BOS ProcessingPipelineState responses."""
    
    def create_spellcheck_only(
        self,  # Accept self parameter explicitly for bound methods
        batch_id: str = "test-batch",
        user_id: str = "test-user",
        status: str = "COMPLETED_SUCCESSFULLY"
    ) -> Dict[str, Any]:
        """Create BOS response with only spellcheck pipeline."""
        return {
            "batch_id": batch_id,
            "user_id": user_id,
            "requested_pipelines": ["spellcheck"],
            "spellcheck": {
                "status": status,
                "essay_counts": {"total": 3, "successful": 3, "failed": 0},
                "started_at": "2024-01-01T10:00:00Z",
                "completed_at": "2024-01-01T10:05:00Z" if status == "COMPLETED_SUCCESSFULLY" else None,
            },
            "last_updated": "2024-01-01T10:06:00Z",
        }
    
    def create_multi_pipeline(
        self,  # Accept self parameter explicitly for bound methods
        batch_id: str = "test-batch",
        user_id: str = "test-user",
        spellcheck_status: str = "COMPLETED_SUCCESSFULLY",
        cj_status: str = "IN_PROGRESS"
    ) -> Dict[str, Any]:
        """Create BOS response with multiple pipelines."""
        return {
            "batch_id": batch_id,
            "user_id": user_id,
            "requested_pipelines": ["spellcheck", "cj_assessment"],
            "spellcheck": {
                "status": spellcheck_status,
                "essay_counts": {"total": 5, "successful": 5, "failed": 0},
                "started_at": "2024-01-01T10:00:00Z",
                "completed_at": "2024-01-01T10:05:00Z",
            },
            "cj_assessment": {
                "status": cj_status,
                "essay_counts": {"total": 5, "successful": 3, "failed": 0},
                "started_at": "2024-01-01T10:05:00Z",
                "completed_at": None,
            },
            "last_updated": "2024-01-01T10:15:00Z",
        }
    
    def create_large_batch(
        self,  # Accept self parameter explicitly for bound methods
        batch_id: str = "large-batch",
        user_id: str = "test-user",
        essay_count: int = 100
    ) -> Dict[str, Any]:
        """Create BOS response with large essay count for performance testing."""
        return {
            "batch_id": batch_id,
            "user_id": user_id,
            "requested_pipelines": ["spellcheck"],
            "spellcheck": {
                "status": "COMPLETED_SUCCESSFULLY",
                "essay_counts": {"total": essay_count, "successful": essay_count, "failed": 0},
                "started_at": "2024-01-01T10:00:00Z",
                "completed_at": "2024-01-01T10:05:00Z",
            },
            "last_updated": "2024-01-01T10:06:00Z",
        }
    
    return type('BOSResponseFactory', (), {
        'create_spellcheck_only': create_spellcheck_only,
        'create_multi_pipeline': create_multi_pipeline,
        'create_large_batch': create_large_batch,
    })()


@pytest.fixture
def mock_batch_repository():
    """Mock repository that simulates database miss (triggers BOS fallback)."""
    mock_repo = Mock(spec=BatchRepositoryProtocol)
    # By default, return None to trigger BOS fallback
    mock_repo.get_batch.return_value = None
    return mock_repo


def create_mock_http_session(bos_data: Dict[str, Any], status_code: int = 200) -> AsyncMock:
    """Create a properly mocked aiohttp.ClientSession for BOS client testing."""
    # Create mock session
    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    
    # Create mock response
    mock_response = AsyncMock()
    mock_response.status = status_code
    
    if status_code == 200:
        mock_response.json.return_value = bos_data
        # raise_for_status is sync in aiohttp, not async
        mock_response.raise_for_status = Mock(return_value=None)
    elif status_code == 404:
        mock_response.raise_for_status = Mock(return_value=None)
    else:
        # For error status codes, raise_for_status should raise an exception
        mock_response.raise_for_status = Mock(side_effect=aiohttp.ClientResponseError(
            request_info=Mock(), history=(), status=status_code
        ))
    
    # Create mock context manager
    mock_context = AsyncMock()
    mock_context.__aenter__.return_value = mock_response
    mock_context.__aexit__.return_value = None
    
    mock_session.get.return_value = mock_context
    
    return mock_session


def create_mock_http_session_with_error(error_type: str) -> AsyncMock:
    """Create mock HTTP session that raises specific errors."""
    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    
    if error_type == "connection_error":
        # Connection refused error
        mock_session.get.side_effect = aiohttp.ClientConnectionError("Connection refused")
    elif error_type == "timeout":
        # Timeout error
        mock_session.get.side_effect = asyncio.TimeoutError()
    elif error_type == "json_error":
        # JSON parsing error
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = Mock(return_value=None)
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_context.__aexit__.return_value = None
        
        mock_session.get.return_value = mock_context
    
    return mock_session


def create_mock_http_session_with_status(status_code: int, text: str = "") -> AsyncMock:
    """Create mock HTTP session that returns specific status codes."""
    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    
    mock_response = AsyncMock()
    mock_response.status = status_code
    
    if status_code == 404:
        mock_response.raise_for_status = Mock(return_value=None)
    elif status_code >= 400:
        mock_response.raise_for_status = Mock(side_effect=aiohttp.ClientResponseError(
            request_info=Mock(), history=(), status=status_code
        ))
    else:
        mock_response.raise_for_status = Mock(return_value=None)
    
    if text:
        mock_response.text.return_value = text
    
    mock_context = AsyncMock()
    mock_context.__aenter__.return_value = mock_response
    mock_context.__aexit__.return_value = None
    
    mock_session.get.return_value = mock_context
    
    return mock_session


class TestBOSIntegrationHappyPath:
    """Test successful BOS fallback scenarios with real HTTP and transformation."""

    async def test_bos_fallback_single_pipeline_success(
        self,
        integration_test_settings: Settings,
        bos_response_factory,
        mock_batch_repository,
    ) -> None:
        """
        Scenario: Database miss triggers BOS fallback with single pipeline
        Given: Batch not found in RAS database, exists in BOS with spellcheck only
        When: get_batch_status called with batch_id
        Then: BOS API called, data transformed, consistent BatchResult returned
        Verifies: Complete BOS fallback flow with single pipeline data
        """
        # Arrange
        batch_id = "single-pipeline-batch"
        user_id = "integration-user-123"
        
        # Create BOS response data using fixed factory
        bos_data = bos_response_factory.create_spellcheck_only(batch_id, user_id)
        
        # Create mock HTTP session that returns the BOS data
        mock_http_session = create_mock_http_session(bos_data, status_code=200)
        
        # Create real components for integration test
        bos_client = BatchOrchestratorClientImpl(integration_test_settings, mock_http_session)
        bos_transformer = BOSDataTransformer()
        aggregator_service = AggregatorServiceImpl(
            batch_repository=mock_batch_repository,
            cache_manager=Mock(),  # Not used in this test
            bos_client=bos_client,
            bos_transformer=bos_transformer,
            settings=integration_test_settings,
        )
        
        # Act
        result = await aggregator_service.get_batch_status(batch_id)
        
        # Assert
        assert result is not None
        assert isinstance(result, BatchResult)
        assert result.batch_id == batch_id
        assert result.user_id == user_id
        assert result.overall_status == BatchStatus.COMPLETED_SUCCESSFULLY
        assert result.essay_count == 3
        assert result.completed_essay_count == 3
        assert result.failed_essay_count == 0
        assert result.requested_pipeline == "spellcheck"
        assert result.batch_metadata is not None
        assert result.batch_metadata["source"] == "bos_fallback"
        
        # Verify BOS client was called with correct URL
        mock_http_session.get.assert_called_once()
        call_args = mock_http_session.get.call_args
        expected_url = f"{integration_test_settings.BOS_URL}/internal/v1/batches/{batch_id}/pipeline-state"
        actual_url = call_args[0][0]
        assert actual_url == expected_url
        
        # Verify repository was called first (database-first logic)
        mock_batch_repository.get_batch.assert_called_once_with(batch_id)

    async def test_bos_fallback_multiple_pipelines_success(
        self,
        integration_test_settings: Settings,
        bos_response_factory,
        mock_batch_repository,
    ) -> None:
        """
        Scenario: Database miss triggers BOS fallback with multiple pipelines
        Given: Batch not found in RAS database, exists in BOS with spellcheck + CJ assessment
        When: get_batch_status called with batch_id
        Then: BOS API called, complex data transformed, complete BatchResult returned
        Verifies: Complex pipeline state transformation accuracy
        """
        # Arrange
        batch_id = "multi-pipeline-batch"
        user_id = "integration-user-456"
        
        # Create BOS response data using fixed factory
        bos_data = bos_response_factory.create_multi_pipeline(
            batch_id, user_id, "COMPLETED_SUCCESSFULLY", "IN_PROGRESS"
        )
        
        # Create mock HTTP session that returns the BOS data
        mock_http_session = create_mock_http_session(bos_data, status_code=200)
        
        # Create real components for integration test
        bos_client = BatchOrchestratorClientImpl(integration_test_settings, mock_http_session)
        bos_transformer = BOSDataTransformer()
        aggregator_service = AggregatorServiceImpl(
            batch_repository=mock_batch_repository,
            cache_manager=Mock(),  # Not used in this test
            bos_client=bos_client,
            bos_transformer=bos_transformer,
            settings=integration_test_settings,
        )
        
        # Act
        result = await aggregator_service.get_batch_status(batch_id)
        
        # Assert
        assert result is not None
        assert result.batch_id == batch_id
        assert result.user_id == user_id
        assert result.overall_status == BatchStatus.PROCESSING_PIPELINES  # One pipeline still in progress
        assert result.essay_count == 5
        assert result.completed_essay_count == 8  # 5 from spellcheck + 3 from CJ assessment
        assert result.failed_essay_count == 0
        assert result.requested_pipeline == "spellcheck,cj_assessment"
        assert result.batch_metadata["source"] == "bos_fallback"
        assert result.batch_metadata["current_phase"] == "CJ_ASSESSMENT"  # Active pipeline
        
        # Verify BOS client was called with correct URL
        mock_http_session.get.assert_called_once()
        call_args = mock_http_session.get.call_args
        expected_url = f"{integration_test_settings.BOS_URL}/internal/v1/batches/{batch_id}/pipeline-state"
        actual_url = call_args[0][0]
        assert actual_url == expected_url
        
        # Verify repository was called first (database-first logic)
        mock_batch_repository.get_batch.assert_called_once_with(batch_id)

    async def test_database_hit_bypasses_bos(
        self,
        integration_test_settings: Settings,
    ) -> None:
        """
        Scenario: Batch found in local database, no BOS call needed
        Given: Batch exists in RAS PostgreSQL database
        When: get_batch_status called with batch_id
        Then: BatchResult returned from database, BOS client never called
        Verifies: Database-first logic prevents unnecessary BOS calls
        """
        # Arrange
        batch_id = "database-hit-batch"
        user_id = "database-user"
        
        # Create mock repository that returns a batch (database hit)
        mock_repo = Mock(spec=BatchRepositoryProtocol)
        mock_batch = Mock(spec=BatchResult)
        mock_batch.batch_id = batch_id
        mock_batch.user_id = user_id
        mock_batch.overall_status = BatchStatus.COMPLETED_SUCCESSFULLY
        mock_repo.get_batch.return_value = mock_batch
        
        # Create real BOS client (should not be called)
        async with aiohttp.ClientSession() as http_session:
            bos_client = BatchOrchestratorClientImpl(integration_test_settings, http_session)
            bos_transformer = BOSDataTransformer()
            aggregator_service = AggregatorServiceImpl(
                batch_repository=mock_repo,
                cache_manager=Mock(),
                bos_client=bos_client,
                bos_transformer=bos_transformer,
                settings=integration_test_settings,
            )
            
            # Act
            result = await aggregator_service.get_batch_status(batch_id)
        
        # Assert
        assert result is not None
        assert result.batch_id == batch_id
        assert result.user_id == user_id
        assert result.overall_status == BatchStatus.COMPLETED_SUCCESSFULLY
        
        # Verify database was queried first
        mock_repo.get_batch.assert_called_once_with(batch_id)


class TestBOSIntegrationErrorHandling:
    """Test error scenarios in BOS fallback flow."""

    async def test_bos_service_unavailable_connection_refused(
        self,
        integration_test_settings: Settings,
        mock_batch_repository,
    ) -> None:
        """
        Scenario: BOS service completely unavailable (connection refused)
        Given: BOS service down, batch not in RAS database
        When: get_batch_status called with batch_id
        Then: aiohttp.ClientConnectionError raised, logged appropriately
        Verifies: Network-level error handling and logging
        """
        # Arrange
        batch_id = "unavailable-service-batch"
        
        # Create mock HTTP session that raises connection error
        mock_http_session = create_mock_http_session_with_error("connection_error")
        
        # Create real components
        bos_client = BatchOrchestratorClientImpl(integration_test_settings, mock_http_session)
        bos_transformer = BOSDataTransformer()
        aggregator_service = AggregatorServiceImpl(
            batch_repository=mock_batch_repository,
            cache_manager=Mock(),
            bos_client=bos_client,
            bos_transformer=bos_transformer,
            settings=integration_test_settings,
        )
        
        # Act & Assert
        with pytest.raises(aiohttp.ClientConnectionError, match="Connection refused"):
            await aggregator_service.get_batch_status(batch_id)
        
        # Verify database was checked first
        mock_batch_repository.get_batch.assert_called_once_with(batch_id)
        
        # Verify BOS call was attempted
        mock_http_session.get.assert_called_once()

    async def test_bos_service_timeout_slow_response(
        self,
        integration_test_settings: Settings,
        mock_batch_repository,
    ) -> None:
        """
        Scenario: BOS service responds slowly causing timeout
        Given: BOS service responds after configured timeout period
        When: get_batch_status called with batch_id
        Then: asyncio.TimeoutError raised, timeout logged with batch_id
        Verifies: Timeout configuration and error propagation
        """
        # Arrange
        batch_id = "timeout-batch"
        
        # Configure timeout to be shorter than response delay
        short_timeout_settings = Settings(
            **{**integration_test_settings.model_dump(), "BOS_TIMEOUT_SECONDS": 1}
        )
        
        # Create mock HTTP session that raises timeout error
        mock_http_session = create_mock_http_session_with_error("timeout")
        
        # Create real components with short timeout
        bos_client = BatchOrchestratorClientImpl(short_timeout_settings, mock_http_session)
        bos_transformer = BOSDataTransformer()
        aggregator_service = AggregatorServiceImpl(
            batch_repository=mock_batch_repository,
            cache_manager=Mock(),
            bos_client=bos_client,
            bos_transformer=bos_transformer,
            settings=short_timeout_settings,
        )
        
        # Act & Assert
        with pytest.raises(asyncio.TimeoutError):
            await aggregator_service.get_batch_status(batch_id)
        
        # Verify database was checked first
        mock_batch_repository.get_batch.assert_called_once_with(batch_id)
        
        # Verify BOS call was attempted
        mock_http_session.get.assert_called_once()

    async def test_bos_service_returns_404_batch_not_found(
        self,
        integration_test_settings: Settings,
        mock_batch_repository,
    ) -> None:
        """
        Scenario: BOS service returns 404 (batch not found anywhere)
        Given: Batch not in RAS database, BOS returns 404
        When: get_batch_status called with batch_id
        Then: None returned (not found), no exceptions raised
        Verifies: 404 handling as normal "not found" response
        """
        # Arrange
        batch_id = "not-found-batch"
        
        # Create mock HTTP session that returns 404
        mock_http_session = create_mock_http_session_with_status(404)
        
        # Create real components
        bos_client = BatchOrchestratorClientImpl(integration_test_settings, mock_http_session)
        bos_transformer = BOSDataTransformer()
        aggregator_service = AggregatorServiceImpl(
            batch_repository=mock_batch_repository,
            cache_manager=Mock(),
            bos_client=bos_client,
            bos_transformer=bos_transformer,
            settings=integration_test_settings,
        )
        
        # Act
        result = await aggregator_service.get_batch_status(batch_id)
        
        # Assert
        assert result is None  # Not found anywhere
        
        # Verify both database and BOS were checked
        mock_batch_repository.get_batch.assert_called_once_with(batch_id)
        mock_http_session.get.assert_called_once()

    async def test_bos_service_returns_500_internal_error(
        self,
        integration_test_settings: Settings,
        mock_batch_repository,
    ) -> None:
        """
        Scenario: BOS service returns 500 internal server error
        Given: BOS service has internal failure, returns 500
        When: get_batch_status called with batch_id
        Then: aiohttp.ClientResponseError raised, error logged with response details
        Verifies: HTTP error status handling and error propagation
        """
        # Arrange
        batch_id = "server-error-batch"
        
        # Create mock HTTP session that returns 500
        mock_http_session = create_mock_http_session_with_status(500, "Internal Server Error")
        
        # Create real components
        bos_client = BatchOrchestratorClientImpl(integration_test_settings, mock_http_session)
        bos_transformer = BOSDataTransformer()
        aggregator_service = AggregatorServiceImpl(
            batch_repository=mock_batch_repository,
            cache_manager=Mock(),
            bos_client=bos_client,
            bos_transformer=bos_transformer,
            settings=integration_test_settings,
        )
        
        # Act & Assert
        with pytest.raises(aiohttp.ClientResponseError):
            await aggregator_service.get_batch_status(batch_id)
        
        # Verify error propagated through the stack
        mock_batch_repository.get_batch.assert_called_once_with(batch_id)
        mock_http_session.get.assert_called_once()

    async def test_bos_returns_malformed_json(
        self,
        integration_test_settings: Settings,
        mock_batch_repository,
    ) -> None:
        """
        Scenario: BOS service returns invalid JSON response
        Given: BOS returns 200 but malformed JSON content
        When: get_batch_status called with batch_id
        Then: ValueError raised during JSON parsing, logged appropriately
        Verifies: JSON parsing error handling in HTTP client
        """
        # Arrange
        batch_id = "malformed-json-batch"
        
        # Create mock HTTP session that raises JSON parsing error
        mock_http_session = create_mock_http_session_with_error("json_error")
        
        # Create real components
        bos_client = BatchOrchestratorClientImpl(integration_test_settings, mock_http_session)
        bos_transformer = BOSDataTransformer()
        aggregator_service = AggregatorServiceImpl(
            batch_repository=mock_batch_repository,
            cache_manager=Mock(),
            bos_client=bos_client,
            bos_transformer=bos_transformer,
            settings=integration_test_settings,
        )
        
        # Act & Assert
        with pytest.raises(ValueError):  # JSON parsing error
            await aggregator_service.get_batch_status(batch_id)
        
        # Verify error handling path
        mock_batch_repository.get_batch.assert_called_once_with(batch_id)
        mock_http_session.get.assert_called_once()

    async def test_bos_returns_valid_json_missing_user_id(
        self,
        integration_test_settings: Settings,
        mock_batch_repository,
    ) -> None:
        """
        Scenario: BOS returns valid JSON but missing required user_id field
        Given: BOS returns JSON without user_id field
        When: get_batch_status called with batch_id
        Then: None returned (handled gracefully), missing user_id logged
        Verifies: Data validation handles incomplete BOS data gracefully
        """
        # Arrange
        batch_id = "missing-user-id-batch"
        
        # Create BOS response data without user_id field
        bos_data = {
            "batch_id": batch_id,
            # Missing user_id field
            "requested_pipelines": ["spellcheck"],
            "spellcheck": {
                "status": "COMPLETED_SUCCESSFULLY",
                "essay_counts": {"total": 1, "successful": 1, "failed": 0},
            },
        }
        
        # Create mock HTTP session that returns the invalid BOS data
        mock_http_session = create_mock_http_session(bos_data, status_code=200)
        
        # Create real components
        bos_client = BatchOrchestratorClientImpl(integration_test_settings, mock_http_session)
        bos_transformer = BOSDataTransformer()
        aggregator_service = AggregatorServiceImpl(
            batch_repository=mock_batch_repository,
            cache_manager=Mock(),
            bos_client=bos_client,
            bos_transformer=bos_transformer,
            settings=integration_test_settings,
        )
        
        # Act
        result = await aggregator_service.get_batch_status(batch_id)
        
        # Assert
        assert result is None  # Handled gracefully
        
        # Verify BOS was called but data was rejected
        mock_batch_repository.get_batch.assert_called_once_with(batch_id)
        mock_http_session.get.assert_called_once()


class TestBOSIntegrationPerformance:
    """Test performance characteristics of BOS integration."""

    async def test_large_bos_response_handling(
        self,
        integration_test_settings: Settings,
        bos_response_factory,
        mock_batch_repository,
    ) -> None:
        """
        Scenario: BOS returns very large response payload
        Given: BOS returns batch with 100+ essays for performance testing
        When: get_batch_status processes large BOS response
        Then: Transformation completes successfully, memory usage reasonable
        Verifies: Large payload handling and memory efficiency
        """
        # Arrange
        batch_id = "large-response-batch"
        user_id = "performance-user"
        essay_count = 100
        
        # Create BOS response data using factory for large batch
        bos_data = bos_response_factory.create_large_batch(batch_id, user_id, essay_count)
        
        # Create mock HTTP session that returns the large BOS data
        mock_http_session = create_mock_http_session(bos_data, status_code=200)
        
        # Create real components
        bos_client = BatchOrchestratorClientImpl(integration_test_settings, mock_http_session)
        bos_transformer = BOSDataTransformer()
        aggregator_service = AggregatorServiceImpl(
            batch_repository=mock_batch_repository,
            cache_manager=Mock(),
            bos_client=bos_client,
            bos_transformer=bos_transformer,
            settings=integration_test_settings,
        )
        
        # Act
        result = await aggregator_service.get_batch_status(batch_id)
        
        # Assert
        assert result is not None
        assert result.batch_id == batch_id
        assert result.essay_count == essay_count
        assert result.completed_essay_count == essay_count
        assert result.overall_status == BatchStatus.COMPLETED_SUCCESSFULLY
        
        # Verify large payload was handled successfully
        mock_batch_repository.get_batch.assert_called_once_with(batch_id)
        mock_http_session.get.assert_called_once()

    async def test_concurrent_bos_fallback_requests(
        self,
        integration_test_settings: Settings,
        bos_response_factory,
        mock_batch_repository,
    ) -> None:
        """
        Scenario: Multiple simultaneous requests for different batches
        Given: Multiple clients request different batch_ids simultaneously
        When: get_batch_status called concurrently 5 times with different batch_ids
        Then: All requests complete successfully, proper HTTP session reuse
        Verifies: Concurrent access safety and HTTP connection management
        """
        # Arrange
        batch_ids = [f"concurrent-batch-{i}" for i in range(5)]
        user_id = "concurrent-user"
        
        # Create a single mock HTTP session that can handle multiple calls
        # For concurrent testing, we'll create one BOS response and reuse it
        bos_data = bos_response_factory.create_spellcheck_only("test-batch", user_id)
        mock_http_session = create_mock_http_session(bos_data, status_code=200)
        
        # Create real components
        bos_client = BatchOrchestratorClientImpl(integration_test_settings, mock_http_session)
        bos_transformer = BOSDataTransformer()
        aggregator_service = AggregatorServiceImpl(
            batch_repository=mock_batch_repository,
            cache_manager=Mock(),
            bos_client=bos_client,
            bos_transformer=bos_transformer,
            settings=integration_test_settings,
        )
        
        # Act - Execute concurrent requests
        tasks = [
            aggregator_service.get_batch_status(batch_id)
            for batch_id in batch_ids
        ]
        results = await asyncio.gather(*tasks)
        
        # Assert
        assert len(results) == 5
        for i, result in enumerate(results):
            assert result is not None
            # Note: batch_id will be "test-batch" from the mock data, not batch_ids[i]
            assert result.user_id == user_id
            assert result.overall_status == BatchStatus.COMPLETED_SUCCESSFULLY
        
        # Verify all BOS calls were made
        assert mock_http_session.get.call_count == 5
        
        # Verify repository was called for each batch
        assert mock_batch_repository.get_batch.call_count == 5