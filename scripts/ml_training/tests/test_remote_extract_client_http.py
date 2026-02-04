from __future__ import annotations

import asyncio

import numpy as np
import pytest
from aiohttp.test_utils import TestClient, TestServer

from scripts.ml_training.essay_scoring.config import (
    EmbeddingConfig,
    FeatureSet,
    OffloadBackend,
    OffloadConfig,
)
from scripts.ml_training.essay_scoring.features.tier1_error_readability import Tier1FeatureExtractor
from scripts.ml_training.essay_scoring.offload.extract_client import RemoteExtractClient
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
async def test_remote_extract_client_roundtrip_http_and_caches(tmp_path, monkeypatch) -> None:
    settings.OFFLOAD_LANGUAGE_TOOL_JAR_VERSION = "6.3"

    def _fake_fetch_remote(  # noqa: ARG001
        _self, *, text: str, request_options: dict[str, object]
    ) -> dict[str, object]:
        return {
            "errors": [
                {"category_id": "PUNCTUATION", "rule_id": "PUNCT_RULE"},
                {"category_id": "SPELLING", "rule_id": "SPELL_RULE"},
                {"category_id": "GRAMMAR", "rule_id": "GRAMMAR_RULE"},
            ]
        }

    monkeypatch.setattr(
        Tier1FeatureExtractor, "_fetch_remote_language_tool_response", _fake_fetch_remote
    )
    monkeypatch.setattr(
        Tier1FeatureExtractor,
        "_compute_text_stats_from_doc",
        lambda _self, _doc: {
            "word_count": 100.0,
            "avg_sentence_length": 10.0,
            "ttr": 0.5,
            "avg_word_length": 4.0,
            "flesch_kincaid": 5.0,
            "smog": 8.0,
            "coleman_liau": 9.0,
            "ari": 7.0,
        },
    )

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
            backend=OffloadBackend.HEMMA,
            offload_service_url=base_url,
            embedding_service_url=None,
            language_tool_service_url=None,
            request_timeout_s=5.0,
            embedding_cache_dir=tmp_path / "emb",
            handcrafted_cache_dir=tmp_path / "hand",
        )
        metrics = OffloadMetricsCollector()
        remote = RemoteExtractClient(
            base_url=base_url,
            embedding_config=embedding_config,
            offload_config=offload_config,
            metrics=metrics,
        )

        first = await asyncio.to_thread(
            remote.extract,
            ["hi", "hello"],
            ["p1", "p2"],
            FeatureSet.COMBINED,
        )
        assert first.embeddings is not None
        assert first.handcrafted is not None
        assert first.embeddings.shape == (2, 2)
        assert first.handcrafted.shape == (2, 11 + 9 + 5)
        assert embedder.calls == 1

        second = await asyncio.to_thread(
            remote.extract,
            ["hi", "hello"],
            ["p1", "p2"],
            FeatureSet.COMBINED,
        )
        assert second.embeddings is not None
        assert second.handcrafted is not None
        assert np.allclose(first.embeddings, second.embeddings)
        assert np.allclose(first.handcrafted, second.handcrafted)
        assert embedder.calls == 1

        snapshot = metrics.snapshot()
        assert snapshot["extract"]["requests"]["requests_total"] == 1
        assert snapshot["extract"]["requests"]["requests_ok"] == 1
        assert snapshot["extract"]["cache"]["hits"] > 0
    finally:
        await client.close()
