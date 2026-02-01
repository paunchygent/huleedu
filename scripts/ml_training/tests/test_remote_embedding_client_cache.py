from __future__ import annotations

import numpy as np

from scripts.ml_training.essay_scoring.config import EmbeddingConfig, OffloadConfig
from scripts.ml_training.essay_scoring.offload import embedding_client
from scripts.ml_training.essay_scoring.offload.embedding_client import RemoteEmbeddingClient


def test_remote_embedding_client_disk_cache(tmp_path, monkeypatch) -> None:
    embedding_config = EmbeddingConfig(
        model_name="microsoft/deberta-v3-base",
        max_length=512,
        batch_size=8,
        device=None,
    )
    offload_config = OffloadConfig(
        embedding_service_url="http://127.0.0.1:19000",
        language_tool_service_url=None,
        request_timeout_s=5.0,
        embedding_cache_dir=tmp_path,
    )

    calls: list[int] = []

    def _fake_fetch(self: RemoteEmbeddingClient, texts: list[str]) -> np.ndarray:  # noqa: ARG001
        calls.append(len(texts))
        return np.arange(len(texts) * 3, dtype=np.float32).reshape(len(texts), 3)

    monkeypatch.setattr(RemoteEmbeddingClient, "_fetch_embeddings", _fake_fetch)

    client = RemoteEmbeddingClient(
        base_url="http://127.0.0.1:19000",
        embedding_config=embedding_config,
        offload_config=offload_config,
    )

    first = client.embed(["a", "bb"])
    assert first.shape == (2, 3)
    assert calls == [2]

    second = client.embed(["a", "bb"])
    assert np.allclose(first, second)
    assert calls == [2]


def test_remote_embedding_client_batches_large_requests(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(embedding_client, "_MAX_EMBEDDING_REQUEST_BYTES", 200)

    embedding_config = EmbeddingConfig(
        model_name="microsoft/deberta-v3-base",
        max_length=512,
        batch_size=8,
        device=None,
    )
    offload_config = OffloadConfig(
        embedding_service_url="http://127.0.0.1:19000",
        language_tool_service_url=None,
        request_timeout_s=5.0,
        embedding_cache_dir=tmp_path,
    )

    calls: list[int] = []

    def _fake_fetch(self: RemoteEmbeddingClient, texts: list[str]) -> np.ndarray:  # noqa: ARG001
        calls.append(len(texts))
        rows = [
            [float(len(text)), float(ord(text[:1] or "x")), float(len(text) + ord(text[:1] or "x"))]
            for text in texts
        ]
        return np.array(rows, dtype=np.float32)

    monkeypatch.setattr(RemoteEmbeddingClient, "_fetch_embeddings", _fake_fetch)

    client = RemoteEmbeddingClient(
        base_url="http://127.0.0.1:19000",
        embedding_config=embedding_config,
        offload_config=offload_config,
    )

    texts = ["a" * 80, "b" * 80, "c" * 80]
    matrix = client.embed(texts)

    assert matrix.shape == (3, 3)
    assert sum(calls) == 3
    assert len(calls) > 1
