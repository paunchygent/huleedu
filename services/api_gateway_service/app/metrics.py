"""Metrics definitions for the API Gateway Service."""

from prometheus_client import Counter, Histogram


class GatewayMetrics:
    """A container for all Prometheus metrics for the API Gateway Service."""

    def __init__(self) -> None:
        self.http_requests_total = Counter(
            "gateway_http_requests_total",
            "Total number of HTTP requests for API Gateway Service.",
            ["method", "endpoint", "http_status"],
        )
        self.http_request_duration_seconds = Histogram(
            "gateway_http_request_duration_seconds",
            "HTTP request duration in seconds for API Gateway Service.",
            ["method", "endpoint"],
        )
        self.events_published_total = Counter(
            "gateway_events_published_total",
            "Total number of Kafka events published by API Gateway Service.",
            ["topic", "event_type"],
        )
        self.downstream_service_calls_total = Counter(
            "gateway_downstream_service_calls_total",
            "Total number of calls to downstream services.",
            ["service", "method", "endpoint", "status_code"],
        )
        self.downstream_service_call_duration_seconds = Histogram(
            "gateway_downstream_service_call_duration_seconds",
            "Duration of calls to downstream services in seconds.",
            ["service", "method", "endpoint"],
        )
        self.websocket_connections_total = Counter(
            "gateway_websocket_connections_total",
            "Total number of WebSocket connections established.",
            ["status"],
        )
        self.api_errors_total = Counter(
            "gateway_api_errors_total",
            "Total number of API errors.",
            ["endpoint", "error_type"],
        )
