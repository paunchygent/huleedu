"""Shared app state keys for the Hemma offload HTTP server."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from aiohttp import web

from scripts.ml_training.essay_scoring.features.protocols import EmbeddingExtractorProtocol
from scripts.ml_training.essay_scoring.offload.observability import (
    GpuProbe,
    OffloadServerMetrics,
    ServiceLabels,
)

EMBEDDER_KEY: web.AppKey[EmbeddingExtractorProtocol] = web.AppKey(
    "embedder", EmbeddingExtractorProtocol
)
SPACY_NLP_KEY: web.AppKey[Any] = web.AppKey("spacy_nlp", object)
SPACY_NLP_FAST_KEY: web.AppKey[Any] = web.AppKey("spacy_nlp_fast", object)
EXTRACT_EXECUTOR_KEY: web.AppKey[ThreadPoolExecutor] = web.AppKey(
    "extract_executor", ThreadPoolExecutor
)
METRICS_KEY: web.AppKey[OffloadServerMetrics] = web.AppKey("metrics", OffloadServerMetrics)
GPU_PROBE_KEY: web.AppKey[GpuProbe] = web.AppKey("gpu_probe", GpuProbe)
LABELS_KEY: web.AppKey[ServiceLabels] = web.AppKey("labels", ServiceLabels)
