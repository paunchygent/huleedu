from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from zipfile import ZipFile

import aiohttp
import pytest
from aiohttp import web

from scripts.cj_experiments_runners.eng5_np import content_upload
from scripts.cj_experiments_runners.eng5_np.content_upload import (
    ContentUploadError,
    clear_upload_cache,
    upload_essay_content,
    upload_essays_parallel,
)
from scripts.cj_experiments_runners.eng5_np.inventory import FileRecord


@pytest.fixture(autouse=True)
def reset_upload_cache() -> None:
    clear_upload_cache()
    yield
    clear_upload_cache()


async def _start_test_server(
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    port: int,
) -> web.AppRunner:
    app = web.Application()
    app.router.add_post("/content", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    return runner


def _write_docx(path: Path, text: str) -> None:
    document_xml = f"""<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>
  <w:body>
    <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)


@pytest.mark.asyncio
async def test_upload_essay_content_success(tmp_path: Path, unused_tcp_port: int) -> None:
    essay_path = tmp_path / "essay.txt"
    essay_path.write_text("hello, world", encoding="utf-8")

    async def handler(request: web.Request) -> web.Response:
        payload = await request.read()
        assert payload == b"hello, world"
        return web.json_response({"storage_id": "storage-123"}, status=201)

    runner = await _start_test_server(handler, unused_tcp_port)
    try:
        async with aiohttp.ClientSession() as session:
            storage_id = await upload_essay_content(
                essay_path,
                content_service_url=f"http://127.0.0.1:{unused_tcp_port}/content",
                session=session,
            )
    finally:
        await runner.cleanup()

    assert storage_id == "storage-123"


@pytest.mark.asyncio
async def test_upload_essay_content_raises_on_error(tmp_path: Path, unused_tcp_port: int) -> None:
    essay_path = tmp_path / "essay.txt"
    essay_path.write_text("boom", encoding="utf-8")

    async def handler(_: web.Request) -> web.Response:
        return web.Response(status=500, text="failure")

    runner = await _start_test_server(handler, unused_tcp_port)
    try:
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ContentUploadError):
                await upload_essay_content(
                    essay_path,
                    content_service_url=f"http://127.0.0.1:{unused_tcp_port}/content",
                    session=session,
                )
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_upload_docx_converts_to_text(tmp_path: Path, unused_tcp_port: int) -> None:
    essay_path = tmp_path / "essay.docx"
    _write_docx(essay_path, "Docx payload")

    async def handler(request: web.Request) -> web.Response:
        payload = await request.read()
        assert payload.decode("utf-8") == "Docx payload"
        return web.json_response({"storage_id": "storage-docx"}, status=201)

    runner = await _start_test_server(handler, unused_tcp_port)
    try:
        async with aiohttp.ClientSession() as session:
            storage_id = await upload_essay_content(
                essay_path,
                content_service_url=f"http://127.0.0.1:{unused_tcp_port}/content",
                session=session,
            )
    finally:
        await runner.cleanup()

    assert storage_id == "storage-docx"


@pytest.mark.asyncio
async def test_upload_essays_parallel_reuses_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    file_a = tmp_path / "a.docx"
    file_b = tmp_path / "b.docx"
    file_a.write_text("AAA", encoding="utf-8")
    file_b.write_text("BBB", encoding="utf-8")
    records = [
        FileRecord.from_path(file_a),
        FileRecord.from_path(file_b),
        FileRecord.from_path(file_a),
    ]

    calls: list[str] = []

    async def fake_upload(
        path: Path, *, content_service_url: str, session: aiohttp.ClientSession
    ) -> str:
        del content_service_url, session
        calls.append(path.name)
        await asyncio.sleep(0)
        return f"sid-{path.stem}"

    monkeypatch.setattr(content_upload, "upload_essay_content", fake_upload)

    first_result = await upload_essays_parallel(
        records=records,
        content_service_url="http://content",
        max_concurrent=2,
    )
    assert len(first_result) == 2
    assert len(calls) == 2  # Uploaded once per unique checksum

    second_result = await upload_essays_parallel(
        records=records,
        content_service_url="http://content",
        max_concurrent=2,
    )
    assert second_result == first_result
    assert len(calls) == 2  # Cache prevented re-upload
