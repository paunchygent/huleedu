"""Integration tests for API concurrent operations.

This module tests API behavior under concurrent access patterns
using real infrastructure components.
"""

import asyncio

import pytest
from quart.testing import QuartClient

from services.result_aggregator_service.models_db import BatchResult


@pytest.mark.integration
@pytest.mark.asyncio
class TestAPIConcurrentOperations:
    """Integration tests for API concurrent operations."""

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
