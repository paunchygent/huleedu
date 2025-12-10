"""Unit tests for CMS client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
from respx import MockRouter

from services.bff_teacher_service.clients.cms_client import CMSClientImpl
from services.bff_teacher_service.config import settings

CORRELATION_ID = uuid4()
BATCH_ID_1 = uuid4()
BATCH_ID_2 = uuid4()


@pytest.fixture
async def cms_client() -> AsyncIterator[CMSClientImpl]:
    """Create CMS client with real httpx client for respx mocking."""
    async with httpx.AsyncClient() as http_client:
        yield CMSClientImpl(http_client)


@pytest.mark.asyncio
async def test_get_class_info_for_batches_success(
    cms_client: CMSClientImpl, respx_mock: MockRouter
) -> None:
    """Test successful class info retrieval with mixed results."""
    url = f"{settings.CMS_URL}/internal/v1/batches/class-info"

    respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            json={
                str(BATCH_ID_1): {"class_id": "class-1", "class_name": "Class 9A"},
                str(BATCH_ID_2): None,
            },
        )
    )

    result = await cms_client.get_class_info_for_batches(
        batch_ids=[BATCH_ID_1, BATCH_ID_2],
        correlation_id=CORRELATION_ID,
    )

    assert str(BATCH_ID_1) in result
    class_info_1 = result[str(BATCH_ID_1)]
    assert class_info_1 is not None
    assert class_info_1.class_name == "Class 9A"
    assert str(BATCH_ID_2) in result
    assert result[str(BATCH_ID_2)] is None


@pytest.mark.asyncio
async def test_get_class_info_for_batches_empty_list(
    cms_client: CMSClientImpl, respx_mock: MockRouter
) -> None:
    """Test handling of empty batch list without HTTP call."""
    result = await cms_client.get_class_info_for_batches(
        batch_ids=[],
        correlation_id=CORRELATION_ID,
    )

    assert result == {}
    assert len(respx_mock.calls) == 0


@pytest.mark.asyncio
async def test_get_class_info_for_batches_all_found(
    cms_client: CMSClientImpl, respx_mock: MockRouter
) -> None:
    """Test when all batches have class associations."""
    url = f"{settings.CMS_URL}/internal/v1/batches/class-info"

    respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            json={
                str(BATCH_ID_1): {"class_id": "class-1", "class_name": "Class 9A"},
                str(BATCH_ID_2): {"class_id": "class-2", "class_name": "Class 9B"},
            },
        )
    )

    result = await cms_client.get_class_info_for_batches(
        batch_ids=[BATCH_ID_1, BATCH_ID_2],
        correlation_id=CORRELATION_ID,
    )

    assert len(result) == 2
    assert all(v is not None for v in result.values())
    class_info_1 = result[str(BATCH_ID_1)]
    class_info_2 = result[str(BATCH_ID_2)]
    assert class_info_1 is not None
    assert class_info_2 is not None
    assert class_info_1.class_name == "Class 9A"
    assert class_info_2.class_name == "Class 9B"


@pytest.mark.asyncio
async def test_get_class_info_for_batches_sends_auth_headers(
    cms_client: CMSClientImpl, respx_mock: MockRouter
) -> None:
    """Test that internal auth headers are sent to CMS."""
    url = f"{settings.CMS_URL}/internal/v1/batches/class-info"

    mock_route = respx_mock.get(url).mock(return_value=httpx.Response(200, json={}))

    await cms_client.get_class_info_for_batches(
        batch_ids=[BATCH_ID_1],
        correlation_id=CORRELATION_ID,
    )

    request_headers = mock_route.calls[0].request.headers
    assert "x-internal-api-key" in request_headers
    assert "x-service-id" in request_headers
    assert "x-correlation-id" in request_headers
    assert request_headers["x-correlation-id"] == str(CORRELATION_ID)


@pytest.mark.asyncio
async def test_get_class_info_for_batches_sends_batch_ids_param(
    cms_client: CMSClientImpl, respx_mock: MockRouter
) -> None:
    """Test that batch_ids are sent as comma-separated query param."""
    url = f"{settings.CMS_URL}/internal/v1/batches/class-info"

    mock_route = respx_mock.get(url).mock(return_value=httpx.Response(200, json={}))

    await cms_client.get_class_info_for_batches(
        batch_ids=[BATCH_ID_1, BATCH_ID_2],
        correlation_id=CORRELATION_ID,
    )

    called_url = str(mock_route.calls[0].request.url)
    assert str(BATCH_ID_1) in called_url
    assert str(BATCH_ID_2) in called_url


@pytest.mark.asyncio
async def test_get_class_info_for_batches_http_error(
    cms_client: CMSClientImpl, respx_mock: MockRouter
) -> None:
    """Test handling of HTTP errors from CMS."""
    url = f"{settings.CMS_URL}/internal/v1/batches/class-info"

    respx_mock.get(url).mock(return_value=httpx.Response(500))

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await cms_client.get_class_info_for_batches(
            batch_ids=[BATCH_ID_1],
            correlation_id=CORRELATION_ID,
        )

    assert exc_info.value.response.status_code == 500
