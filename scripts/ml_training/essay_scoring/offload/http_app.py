"""aiohttp application wiring for the Hemma offload server."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from aiohttp import web

from scripts.ml_training.essay_scoring.features.protocols import EmbeddingExtractorProtocol
from scripts.ml_training.essay_scoring.offload.embedder_factory import build_embedder
from scripts.ml_training.essay_scoring.offload.handlers_embed import embed
from scripts.ml_training.essay_scoring.offload.handlers_extract import extract
from scripts.ml_training.essay_scoring.offload.handlers_observability import (
    healthz,
    metrics,
    observability_middleware,
)
from scripts.ml_training.essay_scoring.offload.http_state import (
    EMBEDDER_KEY,
    EXTRACT_EXECUTOR_KEY,
    GPU_PROBE_KEY,
    LABELS_KEY,
    METRICS_KEY,
)
from scripts.ml_training.essay_scoring.offload.observability import (
    GpuProbe,
    OffloadServerMetrics,
    ServiceLabels,
)
from scripts.ml_training.essay_scoring.offload.settings import settings
from scripts.ml_training.essay_scoring.offload.spacy_runtime import load_spacy_models

logger = logging.getLogger(__name__)


def create_app(*, embedder: EmbeddingExtractorProtocol | None = None) -> web.Application:
    app = web.Application(middlewares=[observability_middleware])
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/metrics", metrics)
    app.router.add_post("/v1/extract", extract)
    app.router.add_post("/v1/embed", embed)

    app[EMBEDDER_KEY] = embedder or build_embedder()
    app[EXTRACT_EXECUTOR_KEY] = ThreadPoolExecutor(max_workers=1)
    app[METRICS_KEY] = OffloadServerMetrics()
    app[GPU_PROBE_KEY] = GpuProbe()
    app[LABELS_KEY] = ServiceLabels.from_env(
        service="essay_scoring_offload",
        version=settings.OFFLOAD_GIT_SHA,
    )

    load_spacy_models(app=app, spacy_model="en_core_web_sm")
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info(
        "Starting offload server host=%s port=%s",
        settings.OFFLOAD_HTTP_HOST,
        settings.OFFLOAD_HTTP_PORT,
    )
    web.run_app(create_app(), host=settings.OFFLOAD_HTTP_HOST, port=settings.OFFLOAD_HTTP_PORT)
