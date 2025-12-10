"""Unit tests for RAS client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from respx import MockRouter

from services.bff_teacher_service.clients.ras_client import RASClientImpl
from services.bff_teacher_service.config import settings

USER_ID = "test-user-123"
CORRELATION_ID = uuid4()


@pytest.fixture
async def ras_client() -> AsyncIterator[RASClientImpl]:
    """Create RAS client with real httpx client for respx mocking."""
    async with httpx.AsyncClient() as http_client:
        yield RASClientImpl(http_client)


@pytest.mark.asyncio
async def test_get_batches_for_user_success(
    ras_client: RASClientImpl, respx_mock: MockRouter
) -> None:
    """Test successful batch retrieval."""
    batch_id = str(uuid4())
    url = f"{settings.RAS_URL}/internal/v1/batches/user/{USER_ID}"

    respx_mock.get(url).mock(
        return_value=httpx.Response(
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
                "pagination": {"limit": 20, "offset": 0, "total": 1},
            },
        )
    )

    batches, pagination = await ras_client.get_batches_for_user(
        user_id=USER_ID,
        correlation_id=CORRELATION_ID,
    )

    assert len(batches) == 1
    assert batches[0].batch_id == batch_id
    assert batches[0].overall_status == "completed_successfully"
    assert pagination["total"] == 1


@pytest.mark.asyncio
async def test_get_batches_for_user_with_pagination(
    ras_client: RASClientImpl, respx_mock: MockRouter
) -> None:
    """Test batch retrieval with custom pagination."""
    url = f"{settings.RAS_URL}/internal/v1/batches/user/{USER_ID}"

    mock_route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            json={"batches": [], "pagination": {"limit": 50, "offset": 100, "total": 200}},
        )
    )

    batches, pagination = await ras_client.get_batches_for_user(
        user_id=USER_ID,
        correlation_id=CORRELATION_ID,
        limit=50,
        offset=100,
    )

    assert len(batches) == 0
    assert pagination["limit"] == 50
    assert pagination["offset"] == 100

    called_url = str(mock_route.calls[0].request.url)
    assert "limit=50" in called_url
    assert "offset=100" in called_url


@pytest.mark.asyncio
async def test_get_batches_for_user_with_status_filter(
    ras_client: RASClientImpl, respx_mock: MockRouter
) -> None:
    """Test batch retrieval with status filter."""
    url = f"{settings.RAS_URL}/internal/v1/batches/user/{USER_ID}"

    mock_route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            json={"batches": [], "pagination": {"limit": 20, "offset": 0, "total": 0}},
        )
    )

    await ras_client.get_batches_for_user(
        user_id=USER_ID,
        correlation_id=CORRELATION_ID,
        status="processing_pipelines",
    )

    called_url = str(mock_route.calls[0].request.url)
    assert "status=processing_pipelines" in called_url


@pytest.mark.asyncio
async def test_get_batches_for_user_empty_response(
    ras_client: RASClientImpl, respx_mock: MockRouter
) -> None:
    """Test handling of empty batch list."""
    url = f"{settings.RAS_URL}/internal/v1/batches/user/{USER_ID}"

    respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            json={"batches": [], "pagination": {"limit": 20, "offset": 0, "total": 0}},
        )
    )

    batches, pagination = await ras_client.get_batches_for_user(
        user_id=USER_ID,
        correlation_id=CORRELATION_ID,
    )

    assert batches == []
    assert pagination["total"] == 0


@pytest.mark.asyncio
async def test_get_batches_for_user_sends_auth_headers(
    ras_client: RASClientImpl, respx_mock: MockRouter
) -> None:
    """Test that internal auth headers are sent to RAS."""
    url = f"{settings.RAS_URL}/internal/v1/batches/user/{USER_ID}"

    mock_route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            json={"batches": [], "pagination": {"limit": 20, "offset": 0, "total": 0}},
        )
    )

    await ras_client.get_batches_for_user(
        user_id=USER_ID,
        correlation_id=CORRELATION_ID,
    )

    request_headers = mock_route.calls[0].request.headers
    assert "x-internal-api-key" in request_headers
    assert "x-service-id" in request_headers
    assert "x-correlation-id" in request_headers
    assert request_headers["x-correlation-id"] == str(CORRELATION_ID)


@pytest.mark.asyncio
async def test_get_batches_for_user_http_error(
    ras_client: RASClientImpl, respx_mock: MockRouter
) -> None:
    """Test handling of HTTP errors from RAS."""
    url = f"{settings.RAS_URL}/internal/v1/batches/user/{USER_ID}"

    respx_mock.get(url).mock(return_value=httpx.Response(503))

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await ras_client.get_batches_for_user(
            user_id=USER_ID,
            correlation_id=CORRELATION_ID,
        )

    assert exc_info.value.response.status_code == 503
