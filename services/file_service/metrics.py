"""Shared Prometheus metrics for File Service.

This module defines a singleton dictionary `METRICS` containing all
Prometheus collectors used by the File Service. The metrics are created
once at import-time and are injected via Dishka so both HTTP routes and
worker components share the same collectors and avoid duplicated
registration errors.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import REGISTRY, Counter, Histogram


def _create_metrics() -> dict[str, Any]:
    """Create Prometheus metric collectors for the File Service."""

    return {
        # Generic counter used throughout the core logic to track upload result
        # Labels mirror those in `core_logic.process_single_file_upload`
        "request_count": Counter(
            "request_count",
            "Total number of HTTP requests",
            ["method", "endpoint", "status"],
            registry=REGISTRY,
        ),
        "request_duration": Histogram(
            "request_duration",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            registry=REGISTRY,
        ),
        "files_uploaded_total": Counter(
            "file_service_files_uploaded_total",
            "Total files received by the File Service, classified by outcome.",
            ["file_type", "validation_status", "batch_id"],  # label names
            registry=REGISTRY,
        ),
        # Technical duration metrics (currently not referenced but useful)
        "text_extraction_duration_seconds": Histogram(
            "file_service_text_extraction_duration_seconds",
            "Time spent extracting text from files.",
            registry=REGISTRY,
        ),
        "content_validation_duration_seconds": Histogram(
            "file_service_content_validation_duration_seconds",
            "Time spent validating extracted content.",
            registry=REGISTRY,
        ),
    }


# Singleton instance shared across the application
METRICS: dict[str, Any] = _create_metrics()
