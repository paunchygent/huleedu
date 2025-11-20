from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from aiohttp import ClientSession
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.implementations.content_client_impl import (
    ContentClientImpl,
)


class _FakeResponse:
    def __init__(self, status: int, body: str = "") -> None:
        self.status = status
        self._body = body

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any
    ) -> None:
        return None

    async def text(self) -> str:
        return self._body


class _FakeSession(ClientSession):
    """Fake session that inherits from ClientSession for type compatibility."""

    def __init__(self, response: _FakeResponse) -> None:
        # Don't call super().__init__() to avoid creating real aiohttp session
        self._response = response  # type: ignore[misc]

    def get(self, *_args: Any, **_kwargs: Any) -> _FakeResponse:  # type: ignore[override]
        return self._response


@pytest.mark.asyncio
async def test_content_exists_returns_true_on_200() -> None:
    settings = Settings()
    client = ContentClientImpl(_FakeSession(_FakeResponse(200, "ok")), settings)

    result = await client.content_exists("storage-123", uuid4())

    assert result is True


@pytest.mark.asyncio
async def test_content_exists_returns_false_on_404() -> None:
    settings = Settings()
    client = ContentClientImpl(_FakeSession(_FakeResponse(404, "")), settings)

    result = await client.content_exists("missing-storage", uuid4())

    assert result is False


@pytest.mark.asyncio
async def test_content_exists_raises_on_unexpected_status() -> None:
    settings = Settings()
    client = ContentClientImpl(_FakeSession(_FakeResponse(500, "boom")), settings)

    with pytest.raises(HuleEduError):
        await client.content_exists("storage-err", uuid4())
