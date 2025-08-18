from __future__ import annotations

from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "identity_requests_total",
    "Total number of identity requests",
    labelnames=("route", "method", "status"),
)

REQUEST_LATENCY = Histogram(
    "identity_request_duration_seconds",
    "Latency of identity requests",
    labelnames=("route",),
)
