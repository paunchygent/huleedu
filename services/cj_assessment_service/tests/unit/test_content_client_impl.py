"""Tests for ContentClientImpl store_content behaviour."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Awaitable, Callable, Dict

import aiohttp
import pytest
from huleedu_service_libs.error_handling import HuleEduError
from unittest.mock import AsyncMock

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

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def json(self) -> dict[str, Any]:
        return self._payload

    async def text(self) -> str:
        return self._text


class RecordingRequestContext:
    """Async context manager that records request metadata."""

    def __init__(self, response: FakeResponse, recorder: Dict[str, Any]) -> None:
        self._response = response
        self._recorder = recorder

    async def __aenter__(self) -> FakeResponse:
        return self._response

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._recorder.setdefault("exits", 0)
        self._recorder["exits"] += 1
        return None


class PassthroughRetryManager:
    """Retry manager stub that simply calls the operation."""

    async def with_retry(
        self, operation: Callable[..., Awaitable[Any]], **kwargs: Any
    ) -> Any:
        return await operation()


@pytest.fixture
def content_settings() -> Settings:
    cfg = Settings()
    cfg.CONTENT_SERVICE_URL = "http://localhost:8080/v1/content"
    return cfg


@pytest.mark.asyncio
async def test_store_content_success(content_settings: Settings) -> None:
    response = FakeResponse(status=201, payload={"storage_id": "abc123"})
    session = AsyncMock(spec=aiohttp.ClientSession)
    recorder: dict[str, Any] = {}

    def _post(
        url: str, *, data: bytes, headers: dict[str, str], timeout: aiohttp.ClientTimeout
    ) -> RecordingRequestContext:
        recorder["url"] = url
        recorder["data"] = data
        recorder["headers"] = headers
        recorder["timeout"] = timeout
        return RecordingRequestContext(response, recorder)

    session.post.side_effect = _post

    client = ContentClientImpl(
        session=session,
        settings=content_settings,
        retry_manager=PassthroughRetryManager(),
    )

    result = await client.store_content("Hello world", content_type="text/plain")

    assert result == {"content_id": "abc123"}
    assert recorder["url"] == "http://localhost:8080/v1/content"
    assert recorder["data"] == b"Hello world"
    assert recorder["headers"] == {"Content-Type": "text/plain"}
    assert isinstance(recorder["timeout"], aiohttp.ClientTimeout)


@pytest.mark.asyncio
async def test_store_content_missing_storage_id_raises(content_settings: Settings) -> None:
    response = FakeResponse(status=201, payload={})
    session = AsyncMock(spec=aiohttp.ClientSession)
    recorder: dict[str, Any] = {}

    def _post(
        url: str, *, data: bytes, headers: dict[str, str], timeout: aiohttp.ClientTimeout
    ) -> RecordingRequestContext:
        recorder["url"] = url
        recorder["data"] = data
        recorder["headers"] = headers
        recorder["timeout"] = timeout
        return RecordingRequestContext(response, recorder)

    session.post.side_effect = _post

    client = ContentClientImpl(
        session=session,
        settings=content_settings,
        retry_manager=PassthroughRetryManager(),
    )

    with pytest.raises(HuleEduError):
        await client.store_content("Hello", content_type="text/plain")
