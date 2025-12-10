"""Unit tests for teacher routes.

Tests dashboard endpoint with mocked backend services using respx.
Follows API Gateway test patterns with Dishka DI.
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

USER_ID = "test-user-dashboard"


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


@pytest.mark.asyncio
async def test_get_dashboard_success(client: AsyncClient, respx_mock: MockRouter) -> None:
    """Test successful dashboard retrieval with batch and class data."""
    batch_id = str(uuid4())

    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    respx_mock.get(ras_url_pattern).mock(
        return_value=Response(
            200,
            json={
                "batches": [
                    {
                        "batch_id": batch_id,
                        "user_id": USER_ID,
                        "overall_status": "completed_successfully",
                        "essay_count": 5,
                        "completed_essay_count": 5,
                        "failed_essay_count": 0,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "assignment_id": "Hamlet Essay",
                    }
                ],
                "pagination": {"limit": 100, "offset": 0, "total": 1},
            },
        )
    )

    cms_url_pattern = re.compile(
        rf"{re.escape(settings.CMS_URL)}/internal/v1/batches/class-info\?.*"
    )
    respx_mock.get(cms_url_pattern).mock(
        return_value=Response(
            200,
            json={batch_id: {"class_id": "class-1", "class_name": "Class 9A"}},
        )
    )

    response = await client.get("/bff/v1/teacher/dashboard")

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert len(data["batches"]) == 1
    assert data["batches"][0]["batch_id"] == batch_id
    assert data["batches"][0]["class_name"] == "Class 9A"
    assert data["batches"][0]["status"] == "completed_successfully"
    assert data["batches"][0]["title"] == "Hamlet Essay"


@pytest.mark.asyncio
async def test_get_dashboard_empty(client: AsyncClient, respx_mock: MockRouter) -> None:
    """Test dashboard with no batches."""
    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    respx_mock.get(ras_url_pattern).mock(
        return_value=Response(
            200,
            json={"batches": [], "pagination": {"limit": 100, "offset": 0, "total": 0}},
        )
    )

    response = await client.get("/bff/v1/teacher/dashboard")

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0
    assert data["batches"] == []


@pytest.mark.asyncio
async def test_get_dashboard_guest_batch_no_class(
    client: AsyncClient, respx_mock: MockRouter
) -> None:
    """Test dashboard with guest batch (no class association)."""
    batch_id = str(uuid4())

    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    respx_mock.get(ras_url_pattern).mock(
        return_value=Response(
            200,
            json={
                "batches": [
                    {
                        "batch_id": batch_id,
                        "user_id": USER_ID,
                        "overall_status": "processing_pipelines",
                        "essay_count": 3,
                        "completed_essay_count": 1,
                        "failed_essay_count": 0,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "assignment_id": None,
                    }
                ],
                "pagination": {"limit": 100, "offset": 0, "total": 1},
            },
        )
    )

    cms_url_pattern = re.compile(
        rf"{re.escape(settings.CMS_URL)}/internal/v1/batches/class-info\?.*"
    )
    respx_mock.get(cms_url_pattern).mock(
        return_value=Response(
            200,
            json={batch_id: None},
        )
    )

    response = await client.get("/bff/v1/teacher/dashboard")

    assert response.status_code == 200
    data = response.json()
    assert len(data["batches"]) == 1
    assert data["batches"][0]["class_name"] is None
    assert data["batches"][0]["title"] == "Untitled Batch"
    assert data["batches"][0]["status"] == "processing"


@pytest.mark.asyncio
async def test_get_dashboard_status_mapping(client: AsyncClient, respx_mock: MockRouter) -> None:
    """Test that internal statuses are mapped to client statuses."""
    batch_id = str(uuid4())

    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    respx_mock.get(ras_url_pattern).mock(
        return_value=Response(
            200,
            json={
                "batches": [
                    {
                        "batch_id": batch_id,
                        "user_id": USER_ID,
                        "overall_status": "awaiting_content_validation",
                        "essay_count": 10,
                        "completed_essay_count": 0,
                        "failed_essay_count": 0,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                ],
                "pagination": {"limit": 100, "offset": 0, "total": 1},
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
    assert data["batches"][0]["status"] == "pending_content"


@pytest.mark.asyncio
async def test_get_dashboard_ras_error(client: AsyncClient, respx_mock: MockRouter) -> None:
    """Test handling of RAS service errors.

    External service errors are translated to 502 Bad Gateway.
    """
    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    respx_mock.get(ras_url_pattern).mock(return_value=Response(503))

    response = await client.get("/bff/v1/teacher/dashboard")

    assert response.status_code == 502
    data = response.json()
    assert "error" in data


@pytest.mark.asyncio
async def test_get_dashboard_cms_error(client: AsyncClient, respx_mock: MockRouter) -> None:
    """Test handling of CMS service errors.

    External service errors are translated to 502 Bad Gateway.
    """
    batch_id = str(uuid4())

    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RAS_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    respx_mock.get(ras_url_pattern).mock(
        return_value=Response(
            200,
            json={
                "batches": [
                    {
                        "batch_id": batch_id,
                        "user_id": USER_ID,
                        "overall_status": "completed_successfully",
                        "essay_count": 5,
                        "completed_essay_count": 5,
                        "failed_essay_count": 0,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                ],
                "pagination": {"limit": 100, "offset": 0, "total": 1},
            },
        )
    )

    cms_url_pattern = re.compile(
        rf"{re.escape(settings.CMS_URL)}/internal/v1/batches/class-info\?.*"
    )
    respx_mock.get(cms_url_pattern).mock(return_value=Response(500))

    response = await client.get("/bff/v1/teacher/dashboard")

    assert response.status_code == 502
    data = response.json()
    assert "error" in data


@pytest.fixture
async def client_no_auth() -> AsyncIterator[AsyncClient]:
    """Create test client WITHOUT auth provider to test missing X-User-ID."""
    from services.bff_teacher_service.di import (
        BFFTeacherProvider,
        RequestContextProvider,
    )

    container = make_async_container(
        BFFTeacherProvider(),
        RequestContextProvider(),
        FastapiProvider(),
    )

    app = FastAPI(title="bff_teacher_service_test_no_auth")
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


@pytest.mark.asyncio
async def test_get_dashboard_missing_user_id_header(client_no_auth: AsyncClient) -> None:
    """Test that missing X-User-ID header returns 401 authentication error.

    When requests bypass API Gateway or lack proper authentication headers,
    the BFF should reject them with an authentication error.
    """
    response = await client_no_auth.get("/bff/v1/teacher/dashboard")

    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "AUTHENTICATION_ERROR"
