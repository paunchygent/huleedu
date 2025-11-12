"""Tests for ContentClientImpl store_content behaviour."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import aiohttp
import pytest
from huleedu_service_libs.error_handling import HuleEduError

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.content_client_impl import ContentClientImpl


class FakeResponse:
    """Minimal async context manager mimicking aiohttp response."""

    def __init__(self, status: int, payload: dict[str, Any], text_body: str | None = None) -> None:
        self.status = status
        self._payload = payload
        self._text = text_body or ""
        self.data: bytes | None = None
        self.headers: dict[str, str] | None = None

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    async def json(self) -> dict[str, Any]:
        return self._payload

    async def text(self) -> str:
        return self._text


class FakeSession:
    """Captures POST invocations for assertions."""

    def __init__(self, response: FakeResponse) -> None:
        self._response = response
        self.last_url: str | None = None
        self.last_data: bytes | None = None
        self.last_headers: dict[str, str] | None = None

    def post(self, url: str, *, data: bytes, headers: dict[str, str], timeout: aiohttp.ClientTimeout) -> FakeResponse:  # noqa: D401
        self.last_url = url
        self.last_data = data
        self.last_headers = headers
        return self._response


class PassthroughRetryManager:
    """Retry manager stub that simply calls the operation."""

    async def with_retry(self, operation, **kwargs):  # noqa: ANN001
        return await operation()


@pytest.fixture
def content_settings() -> Settings:
    cfg = Settings()
    cfg.CONTENT_SERVICE_URL = "http://localhost:8080/v1/content"
    return cfg


@pytest.mark.asyncio
async def test_store_content_success(content_settings: Settings) -> None:
    response = FakeResponse(status=201, payload={"storage_id": "abc123"})
    session = FakeSession(response)
    client = ContentClientImpl(session=session, settings=content_settings, retry_manager=PassthroughRetryManager())

    result = await client.store_content("Hello world", content_type="text/plain")

    assert result == {"content_id": "abc123"}
    assert session.last_url == "http://localhost:8080/v1/content"
    assert session.last_data == b"Hello world"
    assert session.last_headers == {"Content-Type": "text/plain"}


@pytest.mark.asyncio
async def test_store_content_missing_storage_id_raises(content_settings: Settings) -> None:
    response = FakeResponse(status=201, payload={})
    session = FakeSession(response)
    client = ContentClientImpl(session=session, settings=content_settings, retry_manager=PassthroughRetryManager())

    with pytest.raises(HuleEduError):
        await client.store_content("Hello", content_type="text/plain")
