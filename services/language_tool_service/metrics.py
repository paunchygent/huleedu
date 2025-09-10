"""Shared Prometheus metrics for Language Tool Service.

This module defines a singleton dictionary `METRICS` containing all
Prometheus collectors used by the Language Tool Service. The metrics are created
once at import-time and are injected via Dishka so both HTTP routes and
worker components share the same collectors and avoid duplicated
registration errors.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import REGISTRY, Counter, Histogram


def _create_metrics() -> dict[str, Any]:
    """Create Prometheus metric collectors for the Language Tool Service."""

    return {
        # HTTP request metrics
        "request_count": Counter(
            "language_tool_service_http_requests_total",
            "Total number of HTTP requests",
            ["method", "endpoint", "status"],
            registry=REGISTRY,
        ),
        "request_duration": Histogram(
            "language_tool_service_http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            registry=REGISTRY,
        ),
        # Grammar categorization metrics
        "grammar_analysis_total": Counter(
            "language_tool_service_grammar_analysis_total",
            "Total grammar analysis requests processed",
            ["status", "text_length_range"],
            registry=REGISTRY,
        ),
        "grammar_analysis_duration_seconds": Histogram(
            "language_tool_service_grammar_analysis_duration_seconds",
            "Time spent analyzing text for grammar errors",
            registry=REGISTRY,
        ),
        # Language Tool wrapper health metrics
        "language_tool_health_checks_total": Counter(
            "language_tool_service_health_checks_total",
            "Total health check requests to Language Tool wrapper",
            ["status"],
            registry=REGISTRY,
        ),
        # Language Tool wrapper performance metrics
        "wrapper_duration_seconds": Histogram(
            "language_tool_service_wrapper_duration_seconds",
            "Time spent in Language Tool wrapper calls",
            ["language"],
            registry=REGISTRY,
        ),
        # API error tracking metrics
        "api_errors_total": Counter(
            "language_tool_service_api_errors_total",
            "Total API errors by endpoint and error type",
            ["endpoint", "error_type"],
            registry=REGISTRY,
        ),
    }


# Singleton instance shared across the application
METRICS: dict[str, Any] = _create_metrics()
