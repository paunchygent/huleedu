"""Integration tests for API endpoints with cache validation.

This module tests API endpoints with real Redis caching infrastructure
to verify complete cache flow behavior.
"""

import asyncio
from typing import Any, Optional
from unittest.mock import patch

import pytest
from quart.testing import QuartClient

from services.result_aggregator_service.implementations.batch_repository_postgres_impl import (
    BatchRepositoryPostgresImpl,
)
from services.result_aggregator_service.models_db import BatchResult
from services.result_aggregator_service.protocols import CacheManagerProtocol
from services.result_aggregator_service.tests.integration.conftest import (
    IntegrationTestResultAggregatorApp,
)


@pytest.mark.integration
@pytest.mark.asyncio
class TestAPIWithCaching:
    """Integration tests for API endpoints with cache validation."""

    @pytest.mark.slow
    @pytest.mark.integration
    async def test_get_batch_status_cache_flow(
        self,
        integration_test_client: QuartClient,
        auth_headers: dict[str, str],
        setup_test_data: BatchResult,
        integration_test_app: IntegrationTestResultAggregatorApp,
    ) -> None:
        """Test complete cache flow for get_batch_status endpoint."""
        batch_id = "test-batch-001"
        endpoint = f"/internal/v1/batches/{batch_id}/status"

        # Track database queries
        query_count = 0
        original_get_batch = BatchRepositoryPostgresImpl.get_batch

        async def mock_get_batch(self: Any, batch_id: str) -> Optional[BatchResult]:
            nonlocal query_count
            query_count += 1
            return await original_get_batch(self, batch_id)

        with patch.object(BatchRepositoryPostgresImpl, "get_batch", mock_get_batch):
            # Step 1: Cache Miss - First request should hit database
            response1 = await integration_test_client.get(endpoint, headers=auth_headers)
            if response1.status_code != 200:
                error_body = await response1.get_json()
                print(f"Error response: {response1.status_code} - {error_body}")
            assert response1.status_code == 200
            data1 = await response1.get_json()

            # Verify response structure (use client-facing enum values)
            assert data1["batch_id"] == batch_id
            assert data1["user_id"] == "test-user-123"
            # BatchClientStatus values are lowercase strings by contract
            assert data1["overall_status"] == "completed_successfully"
            assert len(data1["essays"]) == 2

            # Verify database was queried
            assert query_count == 1

            # Step 2: Cache Hit - Second request should use cache
            response2 = await integration_test_client.get(endpoint, headers=auth_headers)
            assert response2.status_code == 200
            data2 = await response2.get_json()

            # Response should be identical
            assert data2 == data1

            # Database should NOT be queried again
            assert query_count == 1  # Still 1, no new query

            # Step 3: Cache Invalidation - Simulate batch update
            async with integration_test_app.container() as container:
                cache_manager = await container.get(CacheManagerProtocol)
                await cache_manager.invalidate_batch(batch_id)

            # Step 4: Verify Invalidation - Third request should hit database again
            response3 = await integration_test_client.get(endpoint, headers=auth_headers)
            assert response3.status_code == 200
            data3 = await response3.get_json()

            # Response should still be the same
            assert data3 == data1

            # Database should be queried again after invalidation
            assert query_count == 2

    async def test_get_user_batches_cache_flow(
        self,
        integration_test_client: QuartClient,
        auth_headers: dict[str, str],
        setup_test_data: BatchResult,
        integration_test_app: IntegrationTestResultAggregatorApp,
    ) -> None:
        """Test cache flow for get_user_batches endpoint."""
        user_id = "test-user-123"
        endpoint = f"/internal/v1/batches/user/{user_id}"

        # Create additional batches for pagination testing
        async with integration_test_app.container() as container:
            from services.result_aggregator_service.protocols import BatchRepositoryProtocol

            repo = await container.get(BatchRepositoryProtocol)

            # Create more batches
            for i in range(2, 5):
                await repo.create_batch(
                    batch_id=f"test-batch-{i:03d}", user_id=user_id, essay_count=1
                )

        # Track database queries
        query_count = 0
        original_get_user_batches = BatchRepositoryPostgresImpl.get_user_batches

        async def mock_get_user_batches(
            self: Any, user_id: str, **kwargs: Any
        ) -> list[BatchResult]:
            nonlocal query_count
            query_count += 1
            return await original_get_user_batches(self, user_id, **kwargs)

        with patch.object(BatchRepositoryPostgresImpl, "get_user_batches", mock_get_user_batches):
            # Test with query parameters
            params = {"limit": 2, "offset": 0, "status": "completed_successfully"}

            # Step 1: Cache Miss
            response1 = await integration_test_client.get(
                endpoint, headers=auth_headers, query_string=params
            )
            assert response1.status_code == 200
            data1 = await response1.get_json()

            assert "batches" in data1
            assert len(data1["batches"]) == 1  # Only one completed batch
            assert data1["batches"][0]["batch_id"] == "test-batch-001"
            assert query_count == 1

            # Step 2: Cache Hit
            response2 = await integration_test_client.get(
                endpoint, headers=auth_headers, query_string=params
            )
            assert response2.status_code == 200
            data2 = await response2.get_json()

            assert data2 == data1
            assert query_count == 1  # No new query

            # Step 3: Different parameters should cache separately
            params2 = {"limit": 10, "offset": 0}  # No status filter
            response3 = await integration_test_client.get(
                endpoint, headers=auth_headers, query_string=params2
            )
            assert response3.status_code == 200
            data3 = await response3.get_json()

            assert len(data3["batches"]) == 4  # All batches
            assert query_count == 2  # New query for different params

    async def test_cache_disabled_behavior(
        self,
        integration_test_client: QuartClient,
        auth_headers: dict[str, str],
        setup_test_data: BatchResult,
        integration_test_app: IntegrationTestResultAggregatorApp,
    ) -> None:
        """Test API behavior when caching is disabled."""
        # Temporarily disable caching
        async with integration_test_app.container() as container:
            from services.result_aggregator_service.config import Settings

            settings = await container.get(Settings)
            original_cache_enabled = settings.CACHE_ENABLED
            settings.CACHE_ENABLED = False

        try:
            batch_id = "test-batch-001"
            endpoint = f"/internal/v1/batches/{batch_id}/status"

            # Track database queries
            query_count = 0
            original_get_batch = BatchRepositoryPostgresImpl.get_batch

            async def mock_get_batch(self: Any, batch_id: str) -> Optional[BatchResult]:
                nonlocal query_count
                query_count += 1
                return await original_get_batch(self, batch_id)

            with patch.object(BatchRepositoryPostgresImpl, "get_batch", mock_get_batch):
                # Make multiple requests
                for i in range(3):
                    response = await integration_test_client.get(endpoint, headers=auth_headers)
                    assert response.status_code == 200

                # Each request should hit the database when caching is disabled
                assert query_count == 3

        finally:
            # Restore cache setting
            async with integration_test_app.container() as container:
                from services.result_aggregator_service.config import Settings

                settings = await container.get(Settings)
                settings.CACHE_ENABLED = original_cache_enabled

    @pytest.mark.slow
    @pytest.mark.integration
    async def test_concurrent_cache_operations(
        self,
        integration_test_client: QuartClient,
        auth_headers: dict[str, str],
        setup_test_data: BatchResult,
    ) -> None:
        """Test cache behavior under concurrent requests."""
        batch_id = "test-batch-001"
        endpoint = f"/internal/v1/batches/{batch_id}/status"

        # Make 10 concurrent requests
        async def make_request() -> int:
            response = await integration_test_client.get(endpoint, headers=auth_headers)
            return response.status_code

        tasks = [make_request() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All requests should succeed
        assert all(status == 200 for status in results)

        # Verify cache metrics if available
        # In a real implementation, we'd check Prometheus metrics here
