"""Hemma embedding offload HTTP server (research-scoped).

This server is intentionally implemented under `scripts/` (not `services/`) to keep
heavy ML dependencies out of `typecheck-all`.
"""

from __future__ import annotations

import asyncio
import io
import logging

import numpy as np
from aiohttp import web

from scripts.ml_training.essay_scoring.features.embeddings import DebertaEmbedder
from scripts.ml_training.essay_scoring.features.protocols import EmbeddingExtractorProtocol
from scripts.ml_training.essay_scoring.offload.models import EmbedRequest
from scripts.ml_training.essay_scoring.offload.settings import settings

logger = logging.getLogger(__name__)

_EMBEDDER_KEY: web.AppKey[EmbeddingExtractorProtocol] = web.AppKey(
    "embedder", EmbeddingExtractorProtocol
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
    return web.json_response(
        {
            "status": "ok",
            "model_name": settings.OFFLOAD_EMBEDDING_MODEL_NAME,
            "max_length": settings.OFFLOAD_EMBEDDING_MAX_LENGTH,
            "batch_size": settings.OFFLOAD_EMBEDDING_BATCH_SIZE,
        }
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
    app.router.add_post("/v1/embed", _embed)
    app[_EMBEDDER_KEY] = embedder or _build_embedder()
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
