"""Metrics definitions for the Class Management Service."""

from prometheus_client import Counter, Histogram


class CmsMetrics:
    """A container for all Prometheus metrics for the service."""

    def __init__(self):
        self.http_requests_total = Counter(
            "cms_http_requests_total",
            "Total number of HTTP requests for Class Management Service.",
            ["method", "endpoint", "http_status"],
        )
        self.http_request_duration_seconds = Histogram(
            "cms_http_request_duration_seconds",
            "HTTP request duration in seconds for Class Management Service.",
            ["method", "endpoint"],
        )
        self.class_creations_total = Counter(
            "cms_class_creations_total",
            "Total number of classes created successfully.",
        )
        self.student_creations_total = Counter(
            "cms_student_creations_total",
            "Total number of students created successfully.",
        )
        self.api_errors_total = Counter(
            "cms_api_errors_total",
            "Total number of API errors.",
            ["endpoint", "error_type"],
        )
