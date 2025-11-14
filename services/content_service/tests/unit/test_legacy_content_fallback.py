"""Unit tests for legacy filesystem fallback logic."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_content_service_error,
    raise_resource_not_found,
)

from services.content_service.api.content_routes import (
    LEGACY_FALLBACK_CONTENT_TYPE,
    _get_content_with_legacy_fallback,
)


class _RepositoryWithPrimaryData:
    async def get_content(self, content_id: str, correlation_id: uuid.UUID) -> tuple[bytes, str]:
        return b"primary-bytes", "text/plain"

    async def save_content(
        self,
        content_id: str,
        content_data: bytes,
        content_type: str,
        correlation_id: uuid.UUID,
    ) -> None:
        raise AssertionError("save_content should not run when primary content exists")

    async def content_exists(self, content_id: str) -> bool:  # pragma: no cover - protocol stub
        return True


class _MissingRepository:
    def __init__(self, fail_backfill: bool = False) -> None:
        self.fail_backfill = fail_backfill
        self.save_attempts = 0

    async def get_content(self, content_id: str, correlation_id: uuid.UUID) -> tuple[bytes, str]:
        raise_resource_not_found(
            service="content_service",
            operation="get_content",
            resource_type="content",
            resource_id=content_id,
            correlation_id=correlation_id,
        )

    async def save_content(
        self,
        content_id: str,
        content_data: bytes,
        content_type: str,
        correlation_id: uuid.UUID,
    ) -> None:
        self.save_attempts += 1
        if self.fail_backfill:
            raise_content_service_error(
                service="content_service",
                operation="save_content",
                message="Simulated backfill failure",
                correlation_id=correlation_id,
                content_id=content_id,
            )

    async def content_exists(self, content_id: str) -> bool:  # pragma: no cover - protocol stub
        return False


class _LegacyStore:
    def __init__(self, file_path: Path | None) -> None:
        self._file_path = file_path
        self.path_requests = 0

    async def save_content(self, content_data: bytes, correlation_id: uuid.UUID) -> str:  # pragma: no cover
        raise NotImplementedError

    async def get_content_path(self, content_id: str, correlation_id: uuid.UUID) -> Path:
        self.path_requests += 1
        if self._file_path is None:
            raise_resource_not_found(
                service="content_service",
                operation="get_content_path",
                resource_type="content",
                resource_id=content_id,
                correlation_id=correlation_id,
            )
        return self._file_path

    async def content_exists(self, content_id: str, correlation_id: uuid.UUID) -> bool:  # pragma: no cover
        return self._file_path is not None and self._file_path.exists()


@pytest.mark.asyncio
async def test_primary_repository_content_is_returned_without_legacy_lookup(tmp_path: Path) -> None:
    """Verify we short-circuit when the database already has the payload."""

    repository = _RepositoryWithPrimaryData()
    legacy_store = _LegacyStore(tmp_path / "unused")
    content_id = uuid.uuid4().hex
    correlation_id = uuid.uuid4()

    payload = await _get_content_with_legacy_fallback(
        content_id,
        repository,
        legacy_store,
        correlation_id,
    )

    assert payload == (b"primary-bytes", "text/plain")
    assert legacy_store.path_requests == 0


@pytest.mark.asyncio
async def test_falls_back_to_filesystem_and_backfills(tmp_path: Path) -> None:
    """Verify legacy blobs are read and persisted when DB misses."""

    legacy_file = tmp_path / "legacy.bin"
    legacy_bytes = b"legacy-payload"
    legacy_file.write_bytes(legacy_bytes)

    repository = _MissingRepository()
    legacy_store = _LegacyStore(legacy_file)
    content_id = uuid.uuid4().hex
    correlation_id = uuid.uuid4()

    payload = await _get_content_with_legacy_fallback(
        content_id,
        repository,
        legacy_store,
        correlation_id,
    )

    assert payload == (legacy_bytes, LEGACY_FALLBACK_CONTENT_TYPE)
    assert repository.save_attempts == 1
    assert legacy_store.path_requests == 1


@pytest.mark.asyncio
async def test_raises_not_found_when_legacy_blob_missing(tmp_path: Path) -> None:
    """If neither storage contains the blob we bubble up RESOURCE_NOT_FOUND."""

    repository = _MissingRepository()
    legacy_store = _LegacyStore(file_path=None)
    content_id = uuid.uuid4().hex
    correlation_id = uuid.uuid4()

    with pytest.raises(HuleEduError) as exc_info:
        await _get_content_with_legacy_fallback(
            content_id,
            repository,
            legacy_store,
            correlation_id,
        )

    assert exc_info.value.error_detail.error_code == "RESOURCE_NOT_FOUND"
    assert repository.save_attempts == 0


@pytest.mark.asyncio
async def test_backfill_failures_do_not_block_responses(tmp_path: Path) -> None:
    """Failed persistence attempts should not break legacy downloads."""

    legacy_file = tmp_path / "legacy.bin"
    legacy_file.write_bytes(b"legacy")

    repository = _MissingRepository(fail_backfill=True)
    legacy_store = _LegacyStore(legacy_file)
    content_id = uuid.uuid4().hex
    correlation_id = uuid.uuid4()

    payload = await _get_content_with_legacy_fallback(
        content_id,
        repository,
        legacy_store,
        correlation_id,
    )

    assert payload == (b"legacy", LEGACY_FALLBACK_CONTENT_TYPE)
    assert repository.save_attempts == 1
