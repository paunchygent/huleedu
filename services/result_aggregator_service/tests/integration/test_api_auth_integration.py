"""Integration tests for API authentication and error handling.

This module tests API authentication requirements and error responses
using real infrastructure components.
"""

import pytest
from quart.testing import QuartClient

from services.result_aggregator_service.models_db import BatchResult


@pytest.mark.integration
@pytest.mark.asyncio
class TestAPIAuthentication:
    """Integration tests for API authentication and error handling."""

    async def test_authentication_failure(
        self, integration_test_client: QuartClient, setup_test_data: BatchResult
    ) -> None:
        """Test API authentication requirements."""
        endpoint = "/internal/v1/batches/test-batch-001/status"

        # No headers
        response = await integration_test_client.get(endpoint)
        assert response.status_code == 401

        # Missing API key
        response = await integration_test_client.get(
            endpoint, headers={"X-Service-ID": "test-service"}
        )
        assert response.status_code == 401

        # Invalid API key
        response = await integration_test_client.get(
            endpoint, headers={"X-Internal-API-Key": "wrong-key", "X-Service-ID": "test-service"}
        )
        assert response.status_code == 401

    async def test_batch_not_found(
        self, integration_test_client: QuartClient, auth_headers: dict[str, str]
    ) -> None:
        """Test 404 response for non-existent batch."""
        endpoint = "/internal/v1/batches/non-existent-batch/status"

        response = await integration_test_client.get(endpoint, headers=auth_headers)
        assert response.status_code == 404

        data = await response.get_json()
        assert data["error"] == "Batch not found"
