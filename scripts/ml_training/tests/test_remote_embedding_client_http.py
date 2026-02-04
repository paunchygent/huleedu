from __future__ import annotations

import asyncio

import numpy as np
import pytest
from aiohttp.test_utils import TestClient, TestServer

from scripts.ml_training.essay_scoring.config import EmbeddingConfig, OffloadConfig
from scripts.ml_training.essay_scoring.offload.embedding_client import RemoteEmbeddingClient
from scripts.ml_training.essay_scoring.offload.metrics import OffloadMetricsCollector
from scripts.ml_training.essay_scoring.offload.server import create_app
from scripts.ml_training.essay_scoring.offload.settings import settings


class _CountingEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        return np.array([[float(len(text)), 1.0] for text in texts], dtype=np.float32)


@pytest.mark.asyncio
async def test_remote_embedding_client_roundtrip_http_and_caches(
    requires_localhost_socket: None,
    tmp_path,
) -> None:
    embedder = _CountingEmbedder()
    app = create_app(embedder=embedder)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        base_url = str(server.make_url("/")).rstrip("/")

        embedding_config = EmbeddingConfig(
            model_name=settings.OFFLOAD_EMBEDDING_MODEL_NAME,
            max_length=settings.OFFLOAD_EMBEDDING_MAX_LENGTH,
        )
        offload_config = OffloadConfig(
            embedding_service_url=base_url,
            language_tool_service_url=None,
            request_timeout_s=5.0,
            embedding_cache_dir=tmp_path,
        )
        metrics = OffloadMetricsCollector()
        remote = RemoteEmbeddingClient(
            base_url=base_url,
            embedding_config=embedding_config,
            offload_config=offload_config,
            metrics=metrics,
        )

        first = await asyncio.to_thread(remote.embed, ["hi", "hello"])
        assert first.shape == (2, 2)
        assert embedder.calls == 1

        second = await asyncio.to_thread(remote.embed, ["hi", "hello"])
        assert np.allclose(first, second)
        assert embedder.calls == 1

        snapshot = metrics.snapshot()
        embed_cache = snapshot["embedding"]["cache"]
        assert embed_cache["misses"] == 2
        assert embed_cache["writes"] == 2
        assert embed_cache["hits"] == 2

        embed_requests = snapshot["embedding"]["requests"]
        assert embed_requests["requests_total"] == 1
        assert embed_requests["requests_ok"] == 1
        assert embed_requests["texts_per_request"]["total"] == 2

        cache_files = list(tmp_path.glob("*.npy"))
        assert cache_files
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_remote_embedding_client_raises_on_unsupported_max_length(
    requires_localhost_socket: None,
    tmp_path,
) -> None:
    embedder = _CountingEmbedder()
    app = create_app(embedder=embedder)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        base_url = str(server.make_url("/")).rstrip("/")

        embedding_config = EmbeddingConfig(
            model_name=settings.OFFLOAD_EMBEDDING_MODEL_NAME,
            max_length=settings.OFFLOAD_EMBEDDING_MAX_LENGTH + 1,
        )
        offload_config = OffloadConfig(
            embedding_service_url=base_url,
            language_tool_service_url=None,
            request_timeout_s=5.0,
            embedding_cache_dir=tmp_path,
        )
        remote = RemoteEmbeddingClient(
            base_url=base_url, embedding_config=embedding_config, offload_config=offload_config
        )

        with pytest.raises(RuntimeError, match="unsupported_max_length"):
            await asyncio.to_thread(remote.embed, ["hello"])
    finally:
        await client.close()
