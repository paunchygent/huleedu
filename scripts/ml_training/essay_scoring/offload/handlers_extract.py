"""Combined extract endpoint for Hemma offload (embeddings + handcrafted)."""

from __future__ import annotations

import asyncio
import io
import logging
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import numpy as np
from aiohttp import web

from scripts.ml_training.essay_scoring.config import FeatureSet
from scripts.ml_training.essay_scoring.features.protocols import EmbeddingExtractorProtocol
from scripts.ml_training.essay_scoring.features.tier1_error_readability import Tier1FeatureExtractor
from scripts.ml_training.essay_scoring.features.tier2_syntactic_cohesion import (
    Tier2FeatureExtractor,
)
from scripts.ml_training.essay_scoring.features.tier3_structure import Tier3FeatureExtractor
from scripts.ml_training.essay_scoring.offload.extract_meta import build_meta, canonical_json_bytes
from scripts.ml_training.essay_scoring.offload.extract_models import (
    ExtractError,
    ExtractMeta,
    ExtractRequest,
)
from scripts.ml_training.essay_scoring.offload.http_state import (
    EMBEDDER_KEY,
    EXTRACT_EXECUTOR_KEY,
)
from scripts.ml_training.essay_scoring.offload.settings import settings
from scripts.ml_training.essay_scoring.offload.spacy_runtime import get_spacy_models

logger = logging.getLogger(__name__)


@dataclass
class _RequestScopedEmbeddingCache(EmbeddingExtractorProtocol):
    embedder: EmbeddingExtractorProtocol
    cache: dict[str, np.ndarray]

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)

        missing: list[str] = []
        for text in texts:
            if text not in self.cache:
                missing.append(text)

        if missing:
            vectors = self.embedder.embed(missing)
            if vectors.ndim != 2 or vectors.shape[0] != len(missing):
                raise RuntimeError(
                    "Embedding extractor returned invalid shape "
                    f"shape={getattr(vectors, 'shape', None)} expected_rows={len(missing)}"
                )
            if vectors.dtype != np.float32:
                vectors = vectors.astype(np.float32, copy=False)
            for idx, text in enumerate(missing):
                self.cache[text] = vectors[idx]

        dim = int(next(iter(self.cache.values())).shape[0])
        out = np.zeros((len(texts), dim), dtype=np.float32)
        for idx, text in enumerate(texts):
            out[idx] = self.cache[text]
        return out

    def embedding_dim(self) -> int:
        if not self.cache:
            return 0
        first = next(iter(self.cache.values()))
        return int(first.shape[0])


def _as_float32_matrix(rows: list[list[float]]) -> np.ndarray:
    return np.asarray(rows, dtype=np.float32)


def _stack_handcrafted(
    tier1: list[Any],
    tier2: list[Any],
    tier3: list[Any],
) -> np.ndarray:
    rows: list[list[float]] = []
    for t1, t2, t3 in zip(tier1, tier2, tier3, strict=True):
        rows.append(list(t1.to_list()) + list(t2.to_list()) + list(t3.to_list()))
    return _as_float32_matrix(rows)


def _zip_bundle(
    *, meta: ExtractMeta, embeddings: np.ndarray | None, handcrafted: np.ndarray | None
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("meta.json", meta.model_dump_json(indent=2))

        if embeddings is not None:
            tmp = io.BytesIO()
            np.save(tmp, embeddings.astype(np.float32, copy=False), allow_pickle=False)
            zf.writestr("embeddings.npy", tmp.getvalue())

        if handcrafted is not None:
            tmp = io.BytesIO()
            np.save(tmp, handcrafted.astype(np.float32, copy=False), allow_pickle=False)
            zf.writestr("handcrafted.npy", tmp.getvalue())

    return buf.getvalue()


def _executor(app: web.Application) -> ThreadPoolExecutor:
    return app[EXTRACT_EXECUTOR_KEY]


async def extract(request: web.Request) -> web.Response:
    corr_id = str(request.get("correlation_id") or "")
    if not corr_id:
        import uuid  # noqa: PLC0415

        corr_id = str(uuid.uuid4())

    try:
        payload = await request.json()
        extract_request = ExtractRequest.model_validate(payload)
    except Exception as exc:
        error = ExtractError(
            schema_version=int(settings.OFFLOAD_EXTRACT_SCHEMA_VERSION),
            error="invalid_request",
            detail=str(exc),
            correlation_id=corr_id,
        )
        return web.json_response(error.model_dump(mode="json"), status=400)

    request_bytes = len(canonical_json_bytes(extract_request.model_dump(mode="json")))
    if request_bytes > settings.OFFLOAD_EXTRACT_MAX_REQUEST_BYTES:
        error = ExtractError(
            schema_version=int(settings.OFFLOAD_EXTRACT_SCHEMA_VERSION),
            error="request_too_large",
            detail=(
                "Request body exceeds limit "
                f"bytes={request_bytes} limit={settings.OFFLOAD_EXTRACT_MAX_REQUEST_BYTES}"
            ),
            correlation_id=corr_id,
        )
        return web.json_response(error.model_dump(mode="json"), status=413)

    n_items = len(extract_request.texts)
    if n_items > settings.OFFLOAD_EXTRACT_MAX_ITEMS:
        error = ExtractError(
            schema_version=int(settings.OFFLOAD_EXTRACT_SCHEMA_VERSION),
            error="too_many_items",
            detail=(
                f"Too many items in request n={n_items} limit={settings.OFFLOAD_EXTRACT_MAX_ITEMS}"
            ),
            correlation_id=corr_id,
        )
        return web.json_response(error.model_dump(mode="json"), status=413)

    request["offload_items"] = n_items

    app = request.app
    embedder = app[EMBEDDER_KEY]
    embed_cache = _RequestScopedEmbeddingCache(embedder=embedder, cache={})

    try:
        loop = asyncio.get_running_loop()

        def _compute() -> tuple[ExtractMeta, bytes]:
            nlp, nlp_fast = get_spacy_models(app)
            tier1 = Tier1FeatureExtractor(
                nlp=nlp,
                language_tool_url=settings.OFFLOAD_LANGUAGE_TOOL_URL,
                request_timeout_s=60.0,
                language_tool_cache_dir=None,
                language_tool_max_concurrency=int(settings.OFFLOAD_LANGUAGE_TOOL_MAX_CONCURRENCY),
            )
            tier2 = Tier2FeatureExtractor(
                nlp=nlp_fast,
                embedding_extractor=embed_cache,
            )
            tier3 = Tier3FeatureExtractor(
                nlp=nlp_fast,
            )

            handcrafted = None
            embeddings = None

            if extract_request.feature_set in {FeatureSet.HANDCRAFTED, FeatureSet.COMBINED}:
                tier1_features = tier1.extract_batch(extract_request.texts)
                tier2_features = tier2.extract_batch(extract_request.texts, extract_request.prompts)
                tier3_features = [
                    tier3.extract(t, p)
                    for t, p in zip(extract_request.texts, extract_request.prompts, strict=True)
                ]
                handcrafted = _stack_handcrafted(tier1_features, tier2_features, tier3_features)

            if extract_request.feature_set in {FeatureSet.EMBEDDINGS, FeatureSet.COMBINED}:
                embeddings = embed_cache.embed(extract_request.texts)

            embedding_dim = embed_cache.embedding_dim()
            if embedding_dim <= 0 and embeddings is not None and embeddings.ndim == 2:
                embedding_dim = int(embeddings.shape[1])

            meta = build_meta(embedding_dim=embedding_dim)
            body = _zip_bundle(meta=meta, embeddings=embeddings, handcrafted=handcrafted)
            return meta, body

        meta, body = await loop.run_in_executor(_executor(app), _compute)
    except RuntimeError as exc:
        if "LanguageTool offload" in str(exc):
            error = ExtractError(
                schema_version=int(settings.OFFLOAD_EXTRACT_SCHEMA_VERSION),
                error="dependency_unavailable",
                detail=str(exc),
                correlation_id=corr_id,
            )
            return web.json_response(error.model_dump(mode="json"), status=503)
        logger.exception("Extract failed correlation_id=%s", corr_id)
        error = ExtractError(
            schema_version=int(settings.OFFLOAD_EXTRACT_SCHEMA_VERSION),
            error="internal_error",
            detail=str(exc),
            correlation_id=corr_id,
        )
        return web.json_response(error.model_dump(mode="json"), status=500)
    except Exception as exc:
        logger.exception("Extract failed correlation_id=%s", corr_id)
        error = ExtractError(
            schema_version=int(settings.OFFLOAD_EXTRACT_SCHEMA_VERSION),
            error="internal_error",
            detail=str(exc),
            correlation_id=corr_id,
        )
        return web.json_response(error.model_dump(mode="json"), status=500)

    if len(body) > settings.OFFLOAD_EXTRACT_MAX_RESPONSE_BYTES:
        error = ExtractError(
            schema_version=int(settings.OFFLOAD_EXTRACT_SCHEMA_VERSION),
            error="response_too_large",
            detail=(
                "Response exceeds limit "
                f"bytes={len(body)} limit={settings.OFFLOAD_EXTRACT_MAX_RESPONSE_BYTES}"
            ),
            correlation_id=corr_id,
        )
        return web.json_response(error.model_dump(mode="json"), status=500)

    return web.Response(
        body=body,
        headers={
            "X-Schema-Version": str(meta.schema_version),
            "X-Server-Fingerprint": meta.server_fingerprint,
        },
        content_type="application/zip",
    )
