"""HTTP middleware and endpoints for offload server observability."""

from __future__ import annotations

import time
from typing import Any

from aiohttp import web

from scripts.ml_training.essay_scoring.offload.http_state import (
    GPU_PROBE_KEY,
    LABELS_KEY,
    METRICS_KEY,
)
from scripts.ml_training.essay_scoring.offload.observability import build_prometheus_metrics_text
from scripts.ml_training.essay_scoring.offload.settings import settings


@web.middleware
async def observability_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
    metrics = request.app[METRICS_KEY]
    endpoint_stats = metrics.get_endpoint(method=request.method, endpoint=request.path)

    start = time.monotonic()
    endpoint_stats.record_start()

    status = 500
    try:
        response = await handler(request)
        status = getattr(response, "status", 200)
        return response
    except web.HTTPException as exc:
        status = int(exc.status)
        raise
    finally:
        items = request.get("offload_items")
        endpoint_stats.record_end(
            status=int(status),
            duration_s=float(time.monotonic() - start),
            items=int(items) if items is not None else None,
        )


async def healthz(request: web.Request) -> web.Response:
    status = "ok"
    issues: list[str] = []
    if not settings.OFFLOAD_LANGUAGE_TOOL_JAR_VERSION:
        status = "degraded"
        issues.append("missing_OFFLOAD_LANGUAGE_TOOL_JAR_VERSION")

    gpu = request.app[GPU_PROBE_KEY].snapshot()
    metrics = request.app[METRICS_KEY].snapshot()

    return web.json_response(
        {
            "status": status,
            "issues": issues,
            "model_name": settings.OFFLOAD_EMBEDDING_MODEL_NAME,
            "max_length": settings.OFFLOAD_EMBEDDING_MAX_LENGTH,
            "batch_size": settings.OFFLOAD_EMBEDDING_BATCH_SIZE,
            "gpu": gpu,
            "metrics": metrics,
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


async def metrics(request: web.Request) -> web.Response:
    payload = build_prometheus_metrics_text(
        labels=request.app[LABELS_KEY],
        metrics=request.app[METRICS_KEY],
        gpu=request.app[GPU_PROBE_KEY].snapshot(),
    )
    return web.Response(text=payload, content_type="text/plain; version=0.0.4")
