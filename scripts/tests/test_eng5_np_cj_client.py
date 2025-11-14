from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from aiohttp import web

from scripts.cj_experiments_runners.eng5_np.cj_client import (
    AnchorRegistrationError,
    register_anchor_essays,
)
from scripts.cj_experiments_runners.eng5_np.inventory import FileRecord


async def _start_test_server(handler, port: int) -> web.AppRunner:
    app = web.Application()
    app.router.add_post("/api/v1/anchors/register", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    return runner


@pytest.mark.asyncio
async def test_register_anchor_essays_success(tmp_path: Path, unused_tcp_port: int) -> None:
    anchor_file = tmp_path / "A1.txt"
    anchor_file.write_text("Anchor text", encoding="utf-8")

    async def handler(request: web.Request) -> web.Response:
        payload = await request.json()
        assert payload["grade"] == "A"
        assert payload["anchor_label"] == "A1"
        assert payload["assignment_id"] == "11111111-1111-1111-1111-111111111111"
        assert payload["essay_text"] == "Anchor text"
        return web.json_response(
            {"anchor_id": 1, "storage_id": "abc", "status": "registered"}, status=201
        )

    runner = await _start_test_server(handler, unused_tcp_port)
    try:
        results = await register_anchor_essays(
            anchors=[FileRecord.from_path(anchor_file)],
            assignment_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            cj_service_url=f"http://127.0.0.1:{unused_tcp_port}",
        )
    finally:
        await runner.cleanup()

    assert results[0]["anchor_id"] == 1


@pytest.mark.asyncio
async def test_register_anchor_essays_raises_on_error(tmp_path: Path, unused_tcp_port: int) -> None:
    anchor_file = tmp_path / "B1.txt"
    anchor_file.write_text("Anchor text", encoding="utf-8")

    async def handler(_: web.Request) -> web.Response:
        return web.Response(status=500, text="boom")

    runner = await _start_test_server(handler, unused_tcp_port)
    try:
        with pytest.raises(AnchorRegistrationError):
            await register_anchor_essays(
                anchors=[FileRecord.from_path(anchor_file)],
                assignment_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                cj_service_url=f"http://127.0.0.1:{unused_tcp_port}",
            )
    finally:
        await runner.cleanup()
