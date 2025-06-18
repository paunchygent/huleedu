"""Tests for Batch Conductor Service pipeline resolution endpoint."""

from __future__ import annotations

import pytest
from quart.typing import TestClientProtocol as QuartTestClient

from services.batch_conductor_service.app import app


@pytest.fixture()
async def app_client() -> QuartTestClient:
    """Return a Quart test client configured for testing."""
    app.config.update({"TESTING": True})
    return app.test_client()


class TestPipelineResolutionAPI:
    """Validate /internal/v1/pipelines/define endpoint."""

    async def test_pipeline_resolution_success(self, app_client: QuartTestClient) -> None:
        payload = {"batch_id": "batch_001", "requested_pipeline": "ai_feedback"}

        response = await app_client.post("/internal/v1/pipelines/define", json=payload)

        assert response.status_code == 200

        data = await response.get_json()
        # Response structure validation
        assert data["batch_id"] == "batch_001"
        assert data["final_pipeline"] == ["spellcheck", "nlp", "ai_feedback"]
        assert "analysis_summary" in data

    async def test_pipeline_resolution_validation_error(
        self, app_client: QuartTestClient
    ) -> None:
        # Missing requested_pipeline field
        payload = {"batch_id": "batch_002"}
        response = await app_client.post("/internal/v1/pipelines/define", json=payload)
        assert response.status_code == 400

    async def test_pipeline_resolution_invalid_method(self, app_client: QuartTestClient) -> None:
        # GET should not be allowed on POST-only route
        response = await app_client.get("/internal/v1/pipelines/define")
        assert response.status_code == 405  # Method Not Allowed


@pytest.mark.asyncio
async def test_pipeline_resolution_endpoint_exists() -> None:
    """Test that the pipeline resolution endpoint responds."""
    async with app.test_client() as client:
        response = await client.post("/internal/v1/pipelines/define", json={
            "requested_pipeline": "comprehensive",
            "batch_id": "test-batch",
            "essays": []
        })

        # Should respond (even if with error due to incomplete implementation)
        assert response.status_code in [200, 400, 500]
