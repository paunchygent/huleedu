"""Hemma embedding offload HTTP server (research-scoped).

This server is intentionally implemented under `scripts/` (not `services/`) to keep
heavy ML dependencies out of `typecheck-all`.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import platform
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import numpy as np
from aiohttp import web

from scripts.ml_training.essay_scoring.config import FeatureSet
from scripts.ml_training.essay_scoring.features.embeddings import DebertaEmbedder
from scripts.ml_training.essay_scoring.features.protocols import EmbeddingExtractorProtocol
from scripts.ml_training.essay_scoring.features.schema import build_feature_schema
from scripts.ml_training.essay_scoring.features.tier1_error_readability import Tier1FeatureExtractor
from scripts.ml_training.essay_scoring.features.tier2_syntactic_cohesion import (
    Tier2FeatureExtractor,
)
from scripts.ml_training.essay_scoring.features.tier3_structure import Tier3FeatureExtractor
from scripts.ml_training.essay_scoring.offload.extract_models import (
    ExtractEmbeddingMeta,
    ExtractError,
    ExtractFeatureSchemaMeta,
    ExtractLanguageToolMeta,
    ExtractMeta,
    ExtractRequest,
)
from scripts.ml_training.essay_scoring.offload.models import EmbedRequest
from scripts.ml_training.essay_scoring.offload.settings import settings

logger = logging.getLogger(__name__)

_EMBEDDER_KEY: web.AppKey[EmbeddingExtractorProtocol] = web.AppKey(
    "embedder", EmbeddingExtractorProtocol
)
_SPACY_NLP_KEY: web.AppKey[Any] = web.AppKey("spacy_nlp", object)
_SPACY_NLP_FAST_KEY: web.AppKey[Any] = web.AppKey("spacy_nlp_fast", object)
_EXTRACT_EXECUTOR_KEY: web.AppKey[ThreadPoolExecutor] = web.AppKey(
    "extract_executor", ThreadPoolExecutor
)


def _build_embedder() -> DebertaEmbedder:
    from scripts.ml_training.essay_scoring.config import EmbeddingConfig

    return DebertaEmbedder(
        EmbeddingConfig(
            model_name=settings.OFFLOAD_EMBEDDING_MODEL_NAME,
            max_length=settings.OFFLOAD_EMBEDDING_MAX_LENGTH,
            batch_size=settings.OFFLOAD_EMBEDDING_BATCH_SIZE,
            device=settings.OFFLOAD_TORCH_DEVICE,
        )
    )


async def _healthz(_request: web.Request) -> web.Response:
    status = "ok"
    issues: list[str] = []
    if not settings.OFFLOAD_LANGUAGE_TOOL_JAR_VERSION:
        status = "degraded"
        issues.append("missing_OFFLOAD_LANGUAGE_TOOL_JAR_VERSION")

    return web.json_response(
        {
            "status": status,
            "issues": issues,
            "model_name": settings.OFFLOAD_EMBEDDING_MODEL_NAME,
            "max_length": settings.OFFLOAD_EMBEDDING_MAX_LENGTH,
            "batch_size": settings.OFFLOAD_EMBEDDING_BATCH_SIZE,
            "extract": {
                "schema_version": settings.OFFLOAD_EXTRACT_SCHEMA_VERSION,
                "max_items": settings.OFFLOAD_EXTRACT_MAX_ITEMS,
                "max_request_bytes": settings.OFFLOAD_EXTRACT_MAX_REQUEST_BYTES,
                "max_response_bytes": settings.OFFLOAD_EXTRACT_MAX_RESPONSE_BYTES,
                "language_tool_url": settings.OFFLOAD_LANGUAGE_TOOL_URL,
                "language_tool_jar_version": settings.OFFLOAD_LANGUAGE_TOOL_JAR_VERSION,
            },
        }
    )


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
                    "Embedder returned unexpected shape "
                    f"expected_rows={len(missing)} got_shape={tuple(vectors.shape)}"
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


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode(
        "utf-8"
    )


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _gather_versions() -> dict[str, str]:
    from importlib.metadata import version as _dist_version  # noqa: PLC0415

    import numpy as _np  # noqa: PLC0415
    import spacy as _spacy  # noqa: PLC0415
    import textdescriptives as _textdescriptives  # noqa: PLC0415
    import torch as _torch  # noqa: PLC0415
    import transformers as _transformers  # noqa: PLC0415

    versions: dict[str, str] = {
        "python": platform.python_version(),
        "numpy": _np.__version__,
        "torch": _torch.__version__,
        "transformers": _transformers.__version__,
        "spacy": _spacy.__version__,
        "textdescriptives": _textdescriptives.__version__,
    }
    try:
        versions["en_core_web_sm"] = _dist_version("en-core-web-sm")
    except Exception:
        versions["en_core_web_sm"] = "unknown"
    return versions


def _server_fingerprint_payload(*, embedding_dim: int) -> dict[str, Any]:
    schema = build_feature_schema(embedding_dim)
    return {
        "schema_version": int(settings.OFFLOAD_EXTRACT_SCHEMA_VERSION),
        "embedding": {
            "model_name": settings.OFFLOAD_EMBEDDING_MODEL_NAME,
            "max_length": int(settings.OFFLOAD_EMBEDDING_MAX_LENGTH),
            "batch_size": int(settings.OFFLOAD_EMBEDDING_BATCH_SIZE),
            "pooling": "cls",
            "dim": int(embedding_dim),
            "torch_device": settings.OFFLOAD_TORCH_DEVICE,
        },
        "language_tool": {
            "language": "en-US",
            "request_options": {},
            "service_url": settings.OFFLOAD_LANGUAGE_TOOL_URL,
            "jar_version": settings.OFFLOAD_LANGUAGE_TOOL_JAR_VERSION,
        },
        "feature_schema": schema.model_dump(mode="json"),
        "versions": _gather_versions(),
    }


def _build_meta(*, embedding_dim: int) -> ExtractMeta:
    if not settings.OFFLOAD_LANGUAGE_TOOL_JAR_VERSION:
        raise RuntimeError(
            "OFFLOAD_LANGUAGE_TOOL_JAR_VERSION is required for cache-safe server_fingerprint."
        )

    fingerprint_payload = _server_fingerprint_payload(embedding_dim=embedding_dim)
    fingerprint = _sha256_hex(_canonical_json_bytes(fingerprint_payload))
    schema = build_feature_schema(embedding_dim)

    return ExtractMeta(
        schema_version=int(settings.OFFLOAD_EXTRACT_SCHEMA_VERSION),
        server_fingerprint=fingerprint,
        git_sha=settings.OFFLOAD_GIT_SHA,
        versions=fingerprint_payload["versions"],
        embedding=ExtractEmbeddingMeta(
            model_name=settings.OFFLOAD_EMBEDDING_MODEL_NAME,
            max_length=int(settings.OFFLOAD_EMBEDDING_MAX_LENGTH),
            pooling="cls",
            dim=int(embedding_dim),
        ),
        language_tool=ExtractLanguageToolMeta(
            language="en-US",
            request_options={},
            service_url=settings.OFFLOAD_LANGUAGE_TOOL_URL,
            jar_version=settings.OFFLOAD_LANGUAGE_TOOL_JAR_VERSION,
        ),
        feature_schema=ExtractFeatureSchemaMeta(
            tier1=list(schema.tier1),
            tier2=list(schema.tier2),
            tier3=list(schema.tier3),
            combined=list(schema.combined),
        ),
    )


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


def _ensure_spacy_loaded(app: web.Application) -> tuple[Any, Any]:
    if _SPACY_NLP_KEY not in app:
        from scripts.ml_training.essay_scoring.features.spacy_pipeline import (  # noqa: PLC0415
            load_spacy_model,
        )

        app[_SPACY_NLP_KEY] = load_spacy_model("en_core_web_sm", enable_readability=True)
    if _SPACY_NLP_FAST_KEY not in app:
        from scripts.ml_training.essay_scoring.features.spacy_pipeline import (  # noqa: PLC0415
            load_spacy_model,
        )

        app[_SPACY_NLP_FAST_KEY] = load_spacy_model("en_core_web_sm", enable_readability=False)
    return app[_SPACY_NLP_KEY], app[_SPACY_NLP_FAST_KEY]


async def _extract(request: web.Request) -> web.Response:
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

    request_bytes = len(_canonical_json_bytes(extract_request.model_dump(mode="json")))
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

    app = request.app
    embedder = app[_EMBEDDER_KEY]
    embed_cache = _RequestScopedEmbeddingCache(embedder=embedder, cache={})

    try:
        loop = asyncio.get_running_loop()
        executor = app[_EXTRACT_EXECUTOR_KEY]

        def _compute() -> tuple[ExtractMeta, bytes]:
            nlp, nlp_fast = _ensure_spacy_loaded(app)
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

            meta = _build_meta(embedding_dim=embedding_dim)
            body = _zip_bundle(meta=meta, embeddings=embeddings, handcrafted=handcrafted)
            return meta, body

        meta, body = await loop.run_in_executor(executor, _compute)
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


async def _embed(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        embed_request = EmbedRequest.model_validate(payload)
    except Exception as exc:
        return web.json_response(
            {"error": "invalid_request", "detail": str(exc)},
            status=400,
        )

    if (
        embed_request.model_name
        and embed_request.model_name != settings.OFFLOAD_EMBEDDING_MODEL_NAME
    ):
        return web.json_response(
            {
                "error": "unsupported_model",
                "detail": (
                    "Requested model_name does not match server configuration. "
                    f"requested={embed_request.model_name} "
                    f"configured={settings.OFFLOAD_EMBEDDING_MODEL_NAME}"
                ),
            },
            status=400,
        )

    if (
        embed_request.max_length
        and embed_request.max_length != settings.OFFLOAD_EMBEDDING_MAX_LENGTH
    ):
        return web.json_response(
            {
                "error": "unsupported_max_length",
                "detail": (
                    "Requested max_length does not match server configuration. "
                    f"requested={embed_request.max_length} "
                    f"configured={settings.OFFLOAD_EMBEDDING_MAX_LENGTH}"
                ),
            },
            status=400,
        )

    if (
        embed_request.batch_size
        and embed_request.batch_size != settings.OFFLOAD_EMBEDDING_BATCH_SIZE
    ):
        return web.json_response(
            {
                "error": "unsupported_batch_size",
                "detail": (
                    "Requested batch_size does not match server configuration. "
                    f"requested={embed_request.batch_size} "
                    f"configured={settings.OFFLOAD_EMBEDDING_BATCH_SIZE}"
                ),
            },
            status=400,
        )

    app = request.app
    embedder = app[_EMBEDDER_KEY]

    texts = embed_request.texts

    def _run_embed() -> np.ndarray:
        embeddings = embedder.embed(texts)
        if embeddings.dtype != np.float32:
            embeddings = embeddings.astype(np.float32, copy=False)
        return embeddings

    embeddings = await asyncio.to_thread(_run_embed)

    buf = io.BytesIO()
    np.save(buf, embeddings, allow_pickle=False)
    body = buf.getvalue()

    return web.Response(
        body=body,
        headers={
            "X-Embedding-Model": settings.OFFLOAD_EMBEDDING_MODEL_NAME,
            "X-Embedding-DType": "float32",
        },
        content_type="application/octet-stream",
    )


def create_app(*, embedder: EmbeddingExtractorProtocol | None = None) -> web.Application:
    app = web.Application()
    app.router.add_get("/healthz", _healthz)
    app.router.add_post("/v1/extract", _extract)
    app.router.add_post("/v1/embed", _embed)
    app[_EMBEDDER_KEY] = embedder or _build_embedder()
    app[_EXTRACT_EXECUTOR_KEY] = ThreadPoolExecutor(max_workers=1)
    # Load spaCy models eagerly to avoid cross-thread mutation of app state.
    from scripts.ml_training.essay_scoring.features.spacy_pipeline import (  # noqa: PLC0415
        load_spacy_model,
    )

    app[_SPACY_NLP_KEY] = load_spacy_model("en_core_web_sm", enable_readability=True)
    app[_SPACY_NLP_FAST_KEY] = load_spacy_model("en_core_web_sm", enable_readability=False)
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info(
        "Starting offload server host=%s port=%s",
        settings.OFFLOAD_HTTP_HOST,
        settings.OFFLOAD_HTTP_PORT,
    )
    web.run_app(create_app(), host=settings.OFFLOAD_HTTP_HOST, port=settings.OFFLOAD_HTTP_PORT)


if __name__ == "__main__":
    main()
