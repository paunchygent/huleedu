from __future__ import annotations

import io

import numpy as np
import pytest
from aiohttp.test_utils import TestClient, TestServer

from scripts.ml_training.essay_scoring.offload.server import create_app


class _DummyEmbedder:
    def embed(self, texts: list[str]) -> np.ndarray:
        # 2-dim embeddings to keep test small and deterministic
        return np.array([[float(len(text)), 1.0] for text in texts], dtype=np.float32)


@pytest.mark.asyncio
async def test_embed_returns_npy_payload() -> None:
    app = create_app(embedder=_DummyEmbedder())
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        response = await client.post("/v1/embed", json={"texts": ["hi", "hello"]})
        assert response.status == 200
        assert response.headers.get("X-Embedding-DType") == "float32"
        body = await response.read()
        array = np.load(io.BytesIO(body))
        assert array.shape == (2, 2)
        assert array.dtype == np.float32
        assert array[0, 0] == 2.0
        assert array[1, 0] == 5.0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_embed_rejects_missing_texts() -> None:
    app = create_app(embedder=_DummyEmbedder())
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        response = await client.post("/v1/embed", json={})
        assert response.status == 400
        payload = await response.json()
        assert payload["error"] == "invalid_request"
    finally:
        await client.close()
