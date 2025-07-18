"""
Unit tests for Batch Conductor Service health endpoint.

This module tests the health check API endpoint functionality.
"""

from __future__ import annotations

import pytest

from services.batch_conductor_service.app import app


@pytest.mark.asyncio
async def test_health_check() -> None:
    """Test the health check endpoint returns correct status and format."""
    async with app.test_client() as client:
        response = await client.get("/healthz")

        assert response.status_code == 200

        data = await response.get_json()
        assert data is not None
        assert "status" in data
        assert data["status"] == "healthy"
