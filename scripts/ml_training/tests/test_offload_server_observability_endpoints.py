from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer

from scripts.ml_training.essay_scoring.offload.server import create_app


class _DummyEmbedder:
    def embed(self, texts: list[str]):  # type: ignore[no-untyped-def]
        import numpy as np

        return np.zeros((len(texts), 2), dtype=np.float32)


@pytest.mark.asyncio
async def test_offload_server_exposes_healthz_gpu_and_metrics() -> None:
    app = create_app(embedder=_DummyEmbedder())
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        response = await client.get("/healthz")
        assert response.status == 200
        payload = await response.json()

        assert "gpu" in payload
        assert "metrics" in payload
        assert "uptime_seconds" in payload["metrics"]
        assert isinstance(payload["metrics"]["endpoints"], list)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_offload_server_exposes_prometheus_metrics() -> None:
    app = create_app(embedder=_DummyEmbedder())
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        embed_response = await client.post("/v1/embed", json={"texts": ["a", "b"]})
        assert embed_response.status == 200

        metrics_response = await client.get("/metrics")
        assert metrics_response.status == 200
        text = await metrics_response.text()

        assert "huleedu_offload_uptime_seconds" in text
        assert 'endpoint="/v1/embed"' in text
        assert "huleedu_offload_http_requests_total" in text
        assert "huleedu_offload_gpu_available" in text
    finally:
        await client.close()
