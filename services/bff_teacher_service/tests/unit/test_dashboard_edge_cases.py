"""Edge case unit tests for teacher dashboard endpoint.

Tests pagination, status filtering, and edge case handling
following Phase 2 requirements.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient, Response
from huleedu_service_libs.error_handling.fastapi import (
    register_error_handlers as register_fastapi_error_handlers,
)
from respx import MockRouter

from services.bff_teacher_service.config import settings
from services.bff_teacher_service.middleware import CorrelationIDMiddleware
from services.bff_teacher_service.tests.test_provider import (
    AuthTestProvider,
    InfrastructureTestProvider,
)

USER_ID = "test-user-pagination"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Create test client with Dishka container and test providers."""
    container = make_async_container(
        InfrastructureTestProvider(),
        AuthTestProvider(user_id=USER_ID),
        FastapiProvider(),
    )

    app = FastAPI(title="bff_teacher_service_test")
    register_fastapi_error_handlers(app)
    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from services.bff_teacher_service.api.v1 import router

    app.include_router(router, prefix="/bff/v1/teacher", tags=["Teacher API"])

    setup_dishka(container, app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    await container.close()


def _make_batch(batch_id: str, status: str = "completed_successfully") -> dict:
    """Create a batch response object for mocking."""
    return {
        "batch_id": batch_id,
        "user_id": USER_ID,
        "overall_status": status,
        "essay_count": 5,
        "completed_essay_count": 5,
        "failed_essay_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "assignment_id": "Test Essay",
    }


class TestPaginationParameters:
    """Tests for pagination query parameters."""

    @pytest.mark.asyncio
    async def test_pagination_default_values(
        self, client: AsyncClient, respx_mock: MockRouter
    ) -> None:
        """Test that default pagination values are used when not specified."""
        batch_id = str(uuid4())

        ras_url_pattern = re.compile(
            rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
        )
        respx_mock.get(ras_url_pattern).mock(
            return_value=Response(
                200,
                json={
                    "batches": [_make_batch(batch_id)],
                    "pagination": {"limit": 20, "offset": 0, "total": 1},
                },
            )
        )

        cms_url_pattern = re.compile(
            rf"{re.escape(settings.CMS_URL)}/internal/v1/batches/class-info\?.*"
        )
        respx_mock.get(cms_url_pattern).mock(return_value=Response(200, json={batch_id: None}))

        response = await client.get("/bff/v1/teacher/dashboard")

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 20
        assert data["offset"] == 0

    @pytest.mark.asyncio
    async def test_pagination_custom_limit(
        self, client: AsyncClient, respx_mock: MockRouter
    ) -> None:
        """Test custom limit parameter is passed to RAS and returned."""
        batch_id = str(uuid4())

        ras_url_pattern = re.compile(
            rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
        )
        respx_mock.get(ras_url_pattern).mock(
            return_value=Response(
                200,
                json={
                    "batches": [_make_batch(batch_id)],
                    "pagination": {"limit": 5, "offset": 0, "total": 10},
                },
            )
        )

        cms_url_pattern = re.compile(
            rf"{re.escape(settings.CMS_URL)}/internal/v1/batches/class-info\?.*"
        )
        respx_mock.get(cms_url_pattern).mock(return_value=Response(200, json={batch_id: None}))

        response = await client.get("/bff/v1/teacher/dashboard?limit=5")

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 5
        assert data["total_count"] == 10

    @pytest.mark.asyncio
    async def test_pagination_custom_offset(
        self, client: AsyncClient, respx_mock: MockRouter
    ) -> None:
        """Test custom offset parameter is passed to RAS and returned."""
        batch_id = str(uuid4())

        ras_url_pattern = re.compile(
            rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
        )
        respx_mock.get(ras_url_pattern).mock(
            return_value=Response(
                200,
                json={
                    "batches": [_make_batch(batch_id)],
                    "pagination": {"limit": 20, "offset": 10, "total": 50},
                },
            )
        )

        cms_url_pattern = re.compile(
            rf"{re.escape(settings.CMS_URL)}/internal/v1/batches/class-info\?.*"
        )
        respx_mock.get(cms_url_pattern).mock(return_value=Response(200, json={batch_id: None}))

        response = await client.get("/bff/v1/teacher/dashboard?offset=10")

        assert response.status_code == 200
        data = response.json()
        assert data["offset"] == 10
        assert data["total_count"] == 50

    @pytest.mark.asyncio
    async def test_pagination_limit_boundary_min(
        self, client: AsyncClient, respx_mock: MockRouter
    ) -> None:
        """Test minimum limit boundary (1)."""
        batch_id = str(uuid4())

        ras_url_pattern = re.compile(
            rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
        )
        respx_mock.get(ras_url_pattern).mock(
            return_value=Response(
                200,
                json={
                    "batches": [_make_batch(batch_id)],
                    "pagination": {"limit": 1, "offset": 0, "total": 100},
                },
            )
        )

        cms_url_pattern = re.compile(
            rf"{re.escape(settings.CMS_URL)}/internal/v1/batches/class-info\?.*"
        )
        respx_mock.get(cms_url_pattern).mock(return_value=Response(200, json={batch_id: None}))

        response = await client.get("/bff/v1/teacher/dashboard?limit=1")

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 1
        assert len(data["batches"]) == 1

    @pytest.mark.asyncio
    async def test_pagination_limit_boundary_max(
        self, client: AsyncClient, respx_mock: MockRouter
    ) -> None:
        """Test maximum limit boundary (100)."""
        batch_id = str(uuid4())

        ras_url_pattern = re.compile(
            rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
        )
        respx_mock.get(ras_url_pattern).mock(
            return_value=Response(
                200,
                json={
                    "batches": [_make_batch(batch_id)],
                    "pagination": {"limit": 100, "offset": 0, "total": 1},
                },
            )
        )

        cms_url_pattern = re.compile(
            rf"{re.escape(settings.CMS_URL)}/internal/v1/batches/class-info\?.*"
        )
        respx_mock.get(cms_url_pattern).mock(return_value=Response(200, json={batch_id: None}))

        response = await client.get("/bff/v1/teacher/dashboard?limit=100")

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 100

    @pytest.mark.asyncio
    async def test_pagination_limit_exceeds_max(self, client: AsyncClient) -> None:
        """Test that limit > 100 is rejected by FastAPI validation."""
        response = await client.get("/bff/v1/teacher/dashboard?limit=101")

        assert response.status_code == 422  # FastAPI validation error

    @pytest.mark.asyncio
    async def test_pagination_limit_below_min(self, client: AsyncClient) -> None:
        """Test that limit < 1 is rejected by FastAPI validation."""
        response = await client.get("/bff/v1/teacher/dashboard?limit=0")

        assert response.status_code == 422  # FastAPI validation error

    @pytest.mark.asyncio
    async def test_pagination_negative_offset(self, client: AsyncClient) -> None:
        """Test that negative offset is rejected by FastAPI validation."""
        response = await client.get("/bff/v1/teacher/dashboard?offset=-1")

        assert response.status_code == 422  # FastAPI validation error

    @pytest.mark.asyncio
    async def test_pagination_metadata_in_empty_response(
        self, client: AsyncClient, respx_mock: MockRouter
    ) -> None:
        """Test pagination metadata is present even with empty batches."""
        ras_url_pattern = re.compile(
            rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
        )
        respx_mock.get(ras_url_pattern).mock(
            return_value=Response(
                200,
                json={"batches": [], "pagination": {"limit": 50, "offset": 10, "total": 0}},
            )
        )

        response = await client.get("/bff/v1/teacher/dashboard?limit=50&offset=10")

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 50
        assert data["offset"] == 10
        assert data["total_count"] == 0
        assert data["batches"] == []


class TestStatusFiltering:
    """Tests for status filter query parameter."""

    @pytest.mark.asyncio
    async def test_status_filter_valid_pending_content(
        self, client: AsyncClient, respx_mock: MockRouter
    ) -> None:
        """Test filtering by pending_content status."""
        batch_id = str(uuid4())

        ras_url_pattern = re.compile(
            rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
        )
        respx_mock.get(ras_url_pattern).mock(
            return_value=Response(
                200,
                json={
                    "batches": [_make_batch(batch_id, "awaiting_content_validation")],
                    "pagination": {"limit": 20, "offset": 0, "total": 1},
                },
            )
        )

        cms_url_pattern = re.compile(
            rf"{re.escape(settings.CMS_URL)}/internal/v1/batches/class-info\?.*"
        )
        respx_mock.get(cms_url_pattern).mock(return_value=Response(200, json={batch_id: None}))

        response = await client.get("/bff/v1/teacher/dashboard?status=pending_content")

        assert response.status_code == 200
        data = response.json()
        assert data["batches"][0]["status"] == "pending_content"

    @pytest.mark.asyncio
    async def test_status_filter_valid_processing(
        self, client: AsyncClient, respx_mock: MockRouter
    ) -> None:
        """Test filtering by processing status."""
        batch_id = str(uuid4())

        ras_url_pattern = re.compile(
            rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
        )
        respx_mock.get(ras_url_pattern).mock(
            return_value=Response(
                200,
                json={
                    "batches": [_make_batch(batch_id, "processing_pipelines")],
                    "pagination": {"limit": 20, "offset": 0, "total": 1},
                },
            )
        )

        cms_url_pattern = re.compile(
            rf"{re.escape(settings.CMS_URL)}/internal/v1/batches/class-info\?.*"
        )
        respx_mock.get(cms_url_pattern).mock(return_value=Response(200, json={batch_id: None}))

        response = await client.get("/bff/v1/teacher/dashboard?status=processing")

        assert response.status_code == 200
        data = response.json()
        assert data["batches"][0]["status"] == "processing"

    @pytest.mark.asyncio
    async def test_status_filter_invalid_returns_400(self, client: AsyncClient) -> None:
        """Test that invalid status filter returns 400 validation error."""
        response = await client.get("/bff/v1/teacher/dashboard?status=invalid_status")

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "status" in data["error"]["details"]["field"]

    @pytest.mark.asyncio
    async def test_status_filter_case_sensitive(self, client: AsyncClient) -> None:
        """Test that status filter is case-sensitive (PENDING_CONTENT != pending_content)."""
        response = await client.get("/bff/v1/teacher/dashboard?status=PENDING_CONTENT")

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_all_valid_status_values(
        self, client: AsyncClient, respx_mock: MockRouter
    ) -> None:
        """Test that all valid status values are accepted."""
        valid_statuses = [
            "pending_content",
            "ready",
            "processing",
            "completed_successfully",
            "completed_with_failures",
            "failed",
            "cancelled",
        ]

        batch_id = str(uuid4())
        ras_url_pattern = re.compile(
            rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
        )
        cms_url_pattern = re.compile(
            rf"{re.escape(settings.CMS_URL)}/internal/v1/batches/class-info\?.*"
        )

        for status in valid_statuses:
            respx_mock.reset()
            respx_mock.get(ras_url_pattern).mock(
                return_value=Response(
                    200,
                    json={
                        "batches": [_make_batch(batch_id)],
                        "pagination": {"limit": 20, "offset": 0, "total": 1},
                    },
                )
            )
            respx_mock.get(cms_url_pattern).mock(return_value=Response(200, json={batch_id: None}))

            response = await client.get(f"/bff/v1/teacher/dashboard?status={status}")
            assert response.status_code == 200, f"Status '{status}' should be valid"


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_batches_with_mixed_class_associations(
        self, client: AsyncClient, respx_mock: MockRouter
    ) -> None:
        """Test handling of batches where some have class associations and others don't."""
        batch_with_class = str(uuid4())
        batch_without_class = str(uuid4())

        ras_url_pattern = re.compile(
            rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
        )
        respx_mock.get(ras_url_pattern).mock(
            return_value=Response(
                200,
                json={
                    "batches": [
                        _make_batch(batch_with_class),
                        _make_batch(batch_without_class),
                    ],
                    "pagination": {"limit": 20, "offset": 0, "total": 2},
                },
            )
        )

        cms_url_pattern = re.compile(
            rf"{re.escape(settings.CMS_URL)}/internal/v1/batches/class-info\?.*"
        )
        respx_mock.get(cms_url_pattern).mock(
            return_value=Response(
                200,
                json={
                    batch_with_class: {"class_id": "class-1", "class_name": "Class 9A"},
                    batch_without_class: None,
                },
            )
        )

        response = await client.get("/bff/v1/teacher/dashboard")

        assert response.status_code == 200
        data = response.json()
        assert len(data["batches"]) == 2

        batch_map = {b["batch_id"]: b for b in data["batches"]}
        assert batch_map[batch_with_class]["class_name"] == "Class 9A"
        assert batch_map[batch_without_class]["class_name"] is None

    @pytest.mark.asyncio
    async def test_combined_pagination_and_status_filter(
        self, client: AsyncClient, respx_mock: MockRouter
    ) -> None:
        """Test using pagination and status filter together."""
        batch_id = str(uuid4())

        ras_url_pattern = re.compile(
            rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
        )
        respx_mock.get(ras_url_pattern).mock(
            return_value=Response(
                200,
                json={
                    "batches": [_make_batch(batch_id, "ready_for_pipeline_execution")],
                    "pagination": {"limit": 10, "offset": 5, "total": 25},
                },
            )
        )

        cms_url_pattern = re.compile(
            rf"{re.escape(settings.CMS_URL)}/internal/v1/batches/class-info\?.*"
        )
        respx_mock.get(cms_url_pattern).mock(return_value=Response(200, json={batch_id: None}))

        response = await client.get("/bff/v1/teacher/dashboard?limit=10&offset=5&status=ready")

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 5
        assert data["total_count"] == 25
        assert data["batches"][0]["status"] == "ready"
