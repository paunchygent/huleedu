"""Embedding-only HTTP handler for the offload server."""

from __future__ import annotations

import asyncio
import io
import uuid

import numpy as np
from aiohttp import web

from scripts.ml_training.essay_scoring.offload.http_state import EMBEDDER_KEY
from scripts.ml_training.essay_scoring.offload.models import EmbedRequest
from scripts.ml_training.essay_scoring.offload.settings import settings


async def embed(request: web.Request) -> web.Response:
    corr_id = str(request.get("correlation_id") or "")
    if not corr_id:
        corr_id = str(uuid.uuid4())

    try:
        payload = await request.json()
        embed_request = EmbedRequest.model_validate(payload)
    except Exception as exc:
        return web.json_response(
            {"error": "invalid_request", "detail": str(exc), "correlation_id": corr_id},
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
                "correlation_id": corr_id,
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
                "correlation_id": corr_id,
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
                "correlation_id": corr_id,
            },
            status=400,
        )

    embedder = request.app[EMBEDDER_KEY]

    texts = embed_request.texts
    request["offload_items"] = len(texts)

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
