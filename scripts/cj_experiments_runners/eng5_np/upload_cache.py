"""Disk-backed Content Service upload cache for the ENG5 NP runner.

Purpose:
    Persist `storage_id` results from Content Service uploads keyed by local file checksum so
    repeated ENG5 runs can reuse already-uploaded content instead of re-uploading essays.

Relationships:
    - Wraps `scripts.cj_experiments_runners.eng5_np.content_upload.upload_essays_parallel`.
    - Used by ENG5 mode handlers (`execute`, `anchor-align-test`) before composing CJ requests.
    - Cache file is stored under `RunnerSettings.output_dir` and is safe to delete; it is only an
      optimization layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from scripts.cj_experiments_runners.eng5_np.inventory import FileRecord
from scripts.cj_experiments_runners.eng5_np.utils import sha256_of_file

_CACHE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class UploadCacheOutcome:
    """Summary of a cached upload operation."""

    cache_path: Path
    reused_count: int
    uploaded_count: int
    cache_ignored_reason: str | None = None


def default_cache_path(*, output_dir: Path) -> Path:
    """Return the default cache file location for a given artefact output directory."""

    return output_dir / "content_upload_cache.json"


def _safe_load_json(path: Path) -> tuple[object | None, str | None]:
    """Load JSON from disk, differentiating missing vs invalid JSON."""

    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, None
    except json.JSONDecodeError:
        return None, "cache_file_invalid_json"


@dataclass(frozen=True)
class UploadCacheReadResult:
    """Parsed cache file contents (or a reason it could not be used)."""

    entries: dict[str, str]
    content_service_url: str | None
    error: str | None


def _read_cache_file(cache_path: Path) -> UploadCacheReadResult:
    payload, load_error = _safe_load_json(cache_path)
    if load_error:
        return UploadCacheReadResult(entries={}, content_service_url=None, error=load_error)
    if payload is None:
        return UploadCacheReadResult(entries={}, content_service_url=None, error=None)
    if not isinstance(payload, dict):
        return UploadCacheReadResult(
            entries={}, content_service_url=None, error="cache_file_invalid_format"
        )

    schema_version = payload.get("schema_version")
    if schema_version != _CACHE_SCHEMA_VERSION:
        return UploadCacheReadResult(
            entries={}, content_service_url=None, error="cache_file_schema_mismatch"
        )

    raw_url = payload.get("content_service_url")
    cache_url = raw_url if isinstance(raw_url, str) else None

    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, dict):
        return UploadCacheReadResult(
            entries={},
            content_service_url=cache_url,
            error="cache_file_missing_entries",
        )

    entries: dict[str, str] = {}
    for key, value in raw_entries.items():
        if isinstance(key, str) and isinstance(value, str):
            entries[key] = value

    return UploadCacheReadResult(entries=entries, content_service_url=cache_url, error=None)


def _write_cache_file(
    *,
    cache_path: Path,
    content_service_url: str,
    entries: Mapping[str, str],
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _CACHE_SCHEMA_VERSION,
        "content_service_url": content_service_url,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "entries": dict(entries),
    }
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(cache_path)


def upload_records_with_cache(
    *,
    records: Sequence[FileRecord],
    content_service_url: str,
    cache_path: Path,
    force_reupload: bool,
    uploader: Callable[[Sequence[FileRecord], str], Mapping[str, str]] | None = None,
) -> tuple[dict[str, str], UploadCacheOutcome]:
    """Upload records to Content Service with a disk-backed checksum cache.

    Args:
        records: File records to upload (non-existing files are ignored).
        content_service_url: Content Service upload endpoint URL.
        cache_path: Location of the cache JSON file.
        force_reupload: When True, bypass cache reads and upload all inputs again.
        uploader: Optional override (primarily for tests). It must return a mapping of
            `checksum -> storage_id` for the uploaded records.

    Returns:
        (storage_id_map, outcome)
    """
    if uploader is None:
        import asyncio

        from scripts.cj_experiments_runners.eng5_np.content_upload import upload_essays_parallel

        def _default_uploader(
            to_upload: Sequence[FileRecord],
            url: str,
        ) -> Mapping[str, str]:
            return asyncio.run(
                upload_essays_parallel(
                    records=to_upload,
                    content_service_url=url,
                )
            )

        uploader = _default_uploader

    unique_records: dict[str, FileRecord] = {}
    for record in records:
        if not record.exists:
            continue
        checksum = record.checksum or sha256_of_file(record.path)
        unique_records[checksum] = record

    cache = _read_cache_file(cache_path)
    cache_ignored_reason = cache.error
    cached_entries = cache.entries
    if (
        cached_entries
        and cache.content_service_url
        and cache.content_service_url != content_service_url
    ):
        cached_entries = {}
        cache_ignored_reason = "content_service_url_changed"

    effective_cached = {} if force_reupload else cached_entries
    cache_hits = sum(1 for checksum in unique_records if checksum in effective_cached)

    pending: list[FileRecord] = [
        record for checksum, record in unique_records.items() if checksum not in effective_cached
    ]

    uploaded_entries: dict[str, str] = {}
    if pending:
        uploaded_entries = dict(uploader(pending, content_service_url))

    merged_entries: dict[str, str] = dict(cached_entries)
    merged_entries.update(uploaded_entries)

    # Validate that we can resolve storage IDs for all requested records.
    missing_checksums = [c for c in unique_records if c not in merged_entries]
    if missing_checksums:
        raise KeyError(
            "Content upload cache missing storage_id for "
            f"{len(missing_checksums)} record(s): {missing_checksums[:3]}"
        )

    # Persist cache updates. This is best-effort (but should not silently fail).
    _write_cache_file(
        cache_path=cache_path,
        content_service_url=content_service_url,
        entries=merged_entries,
    )

    storage_id_map = {checksum: merged_entries[checksum] for checksum in unique_records}
    outcome = UploadCacheOutcome(
        cache_path=cache_path,
        reused_count=cache_hits,
        uploaded_count=len(uploaded_entries),
        cache_ignored_reason=cache_ignored_reason,
    )
    return storage_id_map, outcome
