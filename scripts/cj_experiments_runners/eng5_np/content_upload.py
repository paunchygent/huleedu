"""Content Service upload helpers for ENG5 NP runner."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

import aiohttp
from aiohttp.client_exceptions import ClientError, ContentTypeError
import typer

from scripts.cj_experiments_runners.eng5_np.inventory import FileRecord
from scripts.cj_experiments_runners.eng5_np.text_extraction import extract_text, TextExtractionError
from scripts.cj_experiments_runners.eng5_np.utils import sha256_of_file

_UPLOAD_CACHE: dict[str, str] = {}


class ContentUploadError(RuntimeError):
    """Raised when Content Service uploads fail."""


async def upload_essay_content(
    path: Path,
    *,
    content_service_url: str,
    session: aiohttp.ClientSession,
) -> str:
    """Upload an essay file to the Content Service and return its storage_id."""

    if not path.exists():
        raise ContentUploadError(f"Essay file not found: {path}")

    try:
        text_content = await asyncio.to_thread(extract_text, path)
    except TextExtractionError as exc:
        raise ContentUploadError(str(exc)) from exc

    file_bytes = text_content.encode("utf-8")
    if not file_bytes:
        raise ContentUploadError(f"Essay file is empty after text extraction: {path}")

    try:
        async with session.post(
            content_service_url,
            data=file_bytes,
            headers={"Content-Type": "application/octet-stream"},
        ) as response:
            if response.status != 201:
                body = await response.text()
                raise ContentUploadError(
                    f"Content upload failed ({response.status}) for {path.name}: {body[:200]}"
                )

            try:
                payload = await response.json(content_type=None)
            except (json.JSONDecodeError, ContentTypeError) as exc:  # pragma: no cover - network edge
                raise ContentUploadError("Content Service returned invalid JSON") from exc

    except ClientError as exc:
        raise ContentUploadError(f"Content upload request failed for {path.name}") from exc

    storage_id = payload.get("storage_id")
    if not storage_id:
        raise ContentUploadError("Content Service response missing storage_id")

    typer.echo(
        f"Uploaded {path.name} -> storage_id={storage_id}",
        err=True,
    )
    return str(storage_id)


async def upload_essays_parallel(
    *,
    records: Sequence[FileRecord],
    content_service_url: str,
    max_concurrent: int = 10,
) -> dict[str, str]:
    """Upload multiple essays concurrently with simple checksum-based caching."""

    if max_concurrent < 1:
        raise ValueError("max_concurrent must be >= 1")

    unique_records: dict[str, FileRecord] = {}
    for record in records:
        if not record.exists:
            continue
        checksum = record.checksum or sha256_of_file(record.path)
        unique_records[checksum] = record

    cached: dict[str, str] = {}
    for checksum, storage_id in _UPLOAD_CACHE.items():
        if checksum in unique_records:
            cached[checksum] = storage_id

    pending = {k: v for k, v in unique_records.items() if k not in cached}
    if not pending:
        return dict(cached)

    typer.echo(
        f"Uploading {len(pending)} unique essays to Content Service {content_service_url}",
        err=True,
    )

    semaphore = asyncio.Semaphore(max_concurrent)
    timeout = aiohttp.ClientTimeout(total=300)
    storage_map = dict(cached)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async def _upload(checksum: str, record: FileRecord) -> None:
            async with semaphore:
                storage_id = await upload_essay_content(
                    record.path,
                    content_service_url=content_service_url,
                    session=session,
                )
            _UPLOAD_CACHE[checksum] = storage_id
            storage_map[checksum] = storage_id

        await asyncio.gather(
            *(_upload(checksum, record) for checksum, record in pending.items())
        )

    return storage_map


def clear_upload_cache() -> None:
    """Testing helper to reset the in-memory upload cache."""

    _UPLOAD_CACHE.clear()
