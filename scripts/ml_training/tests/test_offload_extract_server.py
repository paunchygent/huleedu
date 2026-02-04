from __future__ import annotations

import io
import json
import zipfile

import numpy as np
import pytest
from aiohttp.test_utils import TestClient, TestServer

from scripts.ml_training.essay_scoring.config import FeatureSet
from scripts.ml_training.essay_scoring.features.tier1_error_readability import Tier1FeatureExtractor
from scripts.ml_training.essay_scoring.offload.server import create_app
from scripts.ml_training.essay_scoring.offload.settings import settings


class _CountingEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        return np.array([[float(len(text)), 1.0] for text in texts], dtype=np.float32)


@pytest.mark.asyncio
async def test_offload_extract_combined_returns_zip_with_meta_and_arrays(monkeypatch) -> None:
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
        response = await client.post(
            "/v1/extract",
            json={
                "texts": ["Hello world.", "This is a test."],
                "prompts": ["Prompt A", "Prompt B"],
                "feature_set": FeatureSet.COMBINED.value,
            },
        )
        assert response.status == 200
        body = await response.read()

        with zipfile.ZipFile(io.BytesIO(body), "r") as zf:
            assert set(zf.namelist()) == {"meta.json", "embeddings.npy", "handcrafted.npy"}
            meta = json.loads(zf.read("meta.json").decode("utf-8"))
            assert meta["schema_version"] == 1
            assert meta["server_fingerprint"]

            embeddings = np.load(io.BytesIO(zf.read("embeddings.npy")))
            handcrafted = np.load(io.BytesIO(zf.read("handcrafted.npy")))

        assert embeddings.shape == (2, 2)
        assert handcrafted.shape == (2, 11 + 9 + 5)

        # Tier2 embeds (unique texts) + embeddings.npy should reuse the request-scoped cache.
        assert embedder.calls == 1
    finally:
        await client.close()
