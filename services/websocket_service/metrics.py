from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram


class WebSocketMetrics:
    """Prometheus metrics for WebSocket service."""

    def __init__(self):
        # Standard HTTP metrics - defined directly like other services
        self.http_request_duration_seconds = Histogram(
            "websocket_http_request_duration_seconds",
            "HTTP request duration in seconds for WebSocket Service.",
            ["method", "endpoint"],
        )
        self.http_requests_total = Counter(
            "websocket_http_requests_total",
            "Total number of HTTP requests for WebSocket Service.",
            ["method", "endpoint", "http_status"],
        )
        self.http_requests_in_progress = Gauge(
            "websocket_http_requests_in_progress",
            "Number of HTTP requests in progress for WebSocket Service.",
            ["method", "endpoint"],
        )

        # WebSocket-specific metrics
        self.websocket_connections_total = Counter(
            "websocket_connections_total",
            "Total number of WebSocket connections",
            ["status"],  # status: accepted, rejected, closed
        )

        self.websocket_active_connections = Gauge(
            "websocket_active_connections",
            "Number of currently active WebSocket connections",
            ["user_id"],
        )

        self.websocket_messages_sent_total = Counter(
            "websocket_messages_sent_total",
            "Total number of messages sent to WebSocket clients",
            ["user_id"],
        )

        self.websocket_messages_failed_total = Counter(
            "websocket_messages_failed_total",
            "Total number of failed message sends",
            ["user_id", "error_type"],
        )

        self.redis_subscription_duration_seconds = Histogram(
            "redis_subscription_duration_seconds",
            "Duration of Redis subscription in seconds",
            ["channel_prefix"],
        )

        self.jwt_validation_total = Counter(
            "jwt_validation_total",
            "Total number of JWT validation attempts",
            ["result"],  # result: success, expired, invalid
        )

        self.websocket_connection_duration_seconds = Histogram(
            "websocket_connection_duration_seconds",
            "Duration of WebSocket connections in seconds",
            buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600],
        )
