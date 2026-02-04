"""ENG5 essay persistence & manifest caching tests.

Purpose:
    Validate the disk-backed Content Service upload cache used by the ENG5 NP runner so repeated
    runs can reuse `storage_id` values instead of re-uploading unchanged essays.

Relationships:
    - Implementation lives in `scripts.cj_experiments_runners.eng5_np.upload_cache`.
    - R7 tracker: `TASKS/programs/eng5/eng5-runner-assumption-hardening.md`.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.cj_experiments_runners.eng5_np.inventory import FileRecord
from scripts.cj_experiments_runners.eng5_np.upload_cache import upload_records_with_cache


def _make_records(tmp_path: Path) -> list[FileRecord]:
    essay_a = tmp_path / "essay_a.docx"
    essay_b = tmp_path / "essay_b.docx"
    essay_a.write_text("hello", encoding="utf-8")
    essay_b.write_text("world", encoding="utf-8")
    return [
        FileRecord.from_path(essay_a),
        FileRecord.from_path(essay_b),
    ]


def _write_cache(
    *,
    cache_path: Path,
    content_service_url: str,
    entries: dict[str, str],
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "content_service_url": content_service_url,
        "updated_at": "2026-02-04T00:00:00+00:00",
        "entries": entries,
    }
    cache_path.write_text(json.dumps(payload), encoding="utf-8")


class TestEng5ManifestCaching:
    def test_first_run_uploads_all_essays_and_writes_cache(self, tmp_path: Path) -> None:
        records = _make_records(tmp_path)
        cache_path = tmp_path / "content_upload_cache.json"
        calls: list[tuple[list[FileRecord], str]] = []

        def uploader(to_upload: list[FileRecord], url: str) -> dict[str, str]:
            calls.append((list(to_upload), url))
            return {r.checksum: f"storage-{idx}" for idx, r in enumerate(to_upload)}

        storage_id_map, outcome = upload_records_with_cache(
            records=records,
            content_service_url="http://content/v1/content",
            cache_path=cache_path,
            force_reupload=False,
            uploader=uploader,
        )

        assert outcome.reused_count == 0
        assert outcome.uploaded_count == 2
        assert len(calls) == 1
        assert len(calls[0][0]) == 2
        assert calls[0][1] == "http://content/v1/content"

        assert set(storage_id_map) == {r.checksum for r in records}
        assert cache_path.exists()
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        assert payload["content_service_url"] == "http://content/v1/content"
        assert set(payload["entries"]) == {r.checksum for r in records}

    def test_second_run_reuses_cached_storage_ids(self, tmp_path: Path) -> None:
        records = _make_records(tmp_path)
        cache_path = tmp_path / "content_upload_cache.json"
        cached_entries = {r.checksum: f"cached-{idx}" for idx, r in enumerate(records)}
        _write_cache(
            cache_path=cache_path,
            content_service_url="http://content/v1/content",
            entries=cached_entries,
        )

        def uploader(_to_upload: list[FileRecord], _url: str) -> dict[str, str]:
            raise AssertionError("Uploader must not be called when cache fully covers inputs.")

        storage_id_map, outcome = upload_records_with_cache(
            records=records,
            content_service_url="http://content/v1/content",
            cache_path=cache_path,
            force_reupload=False,
            uploader=uploader,
        )

        assert outcome.reused_count == 2
        assert outcome.uploaded_count == 0
        assert storage_id_map == cached_entries

    def test_force_reupload_ignores_cache_and_overwrites_it(self, tmp_path: Path) -> None:
        records = _make_records(tmp_path)
        cache_path = tmp_path / "content_upload_cache.json"
        _write_cache(
            cache_path=cache_path,
            content_service_url="http://content/v1/content",
            entries={r.checksum: "stale" for r in records},
        )

        def uploader(to_upload: list[FileRecord], _url: str) -> dict[str, str]:
            return {r.checksum: f"fresh-{idx}" for idx, r in enumerate(to_upload)}

        storage_id_map, outcome = upload_records_with_cache(
            records=records,
            content_service_url="http://content/v1/content",
            cache_path=cache_path,
            force_reupload=True,
            uploader=uploader,
        )

        assert outcome.reused_count == 0
        assert outcome.uploaded_count == 2
        assert all(value.startswith("fresh-") for value in storage_id_map.values())
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        assert payload["entries"] == storage_id_map

    def test_partial_cache_only_uploads_missing_essays(self, tmp_path: Path) -> None:
        records = _make_records(tmp_path)
        cache_path = tmp_path / "content_upload_cache.json"
        cached_entries = {records[0].checksum: "cached-0"}
        _write_cache(
            cache_path=cache_path,
            content_service_url="http://content/v1/content",
            entries=cached_entries,
        )
        calls: list[tuple[list[FileRecord], str]] = []

        def uploader(to_upload: list[FileRecord], url: str) -> dict[str, str]:
            calls.append((list(to_upload), url))
            return {r.checksum: "fresh-1" for r in to_upload}

        storage_id_map, outcome = upload_records_with_cache(
            records=records,
            content_service_url="http://content/v1/content",
            cache_path=cache_path,
            force_reupload=False,
            uploader=uploader,
        )

        assert outcome.reused_count == 1
        assert outcome.uploaded_count == 1
        assert len(calls) == 1
        assert len(calls[0][0]) == 1
        assert calls[0][0][0].checksum == records[1].checksum
        assert storage_id_map == {
            records[0].checksum: "cached-0",
            records[1].checksum: "fresh-1",
        }

    def test_cache_ignored_when_content_service_url_changes(self, tmp_path: Path) -> None:
        records = _make_records(tmp_path)
        cache_path = tmp_path / "content_upload_cache.json"
        _write_cache(
            cache_path=cache_path,
            content_service_url="http://old-content/v1/content",
            entries={r.checksum: "stale" for r in records},
        )
        calls: list[tuple[list[FileRecord], str]] = []

        def uploader(to_upload: list[FileRecord], url: str) -> dict[str, str]:
            calls.append((list(to_upload), url))
            return {r.checksum: f"fresh-{idx}" for idx, r in enumerate(to_upload)}

        _storage_id_map, outcome = upload_records_with_cache(
            records=records,
            content_service_url="http://new-content/v1/content",
            cache_path=cache_path,
            force_reupload=False,
            uploader=uploader,
        )

        assert outcome.cache_ignored_reason == "content_service_url_changed"
        assert outcome.reused_count == 0
        assert outcome.uploaded_count == 2
        assert len(calls) == 1
