"""Service-specific metrics for Result Aggregator Service."""

from prometheus_client import Counter, Histogram


class ResultAggregatorMetrics:
    """Service-specific metrics."""

    def __init__(self) -> None:
        # API metrics
        self.api_requests_total = Counter(
            "ras_api_requests_total", "Total API requests", ["endpoint", "method", "status_code"]
        )

        self.api_request_duration = Histogram(
            "ras_api_request_duration_seconds", "API request duration", ["endpoint", "method"]
        )

        self.api_errors_total = Counter(
            "ras_api_errors_total", "Total API errors", ["endpoint", "error_type"]
        )

        # Kafka consumer metrics
        self.messages_processed = Counter(
            "ras_messages_processed_total", "Total messages processed"
        )

        self.message_processing_time = Histogram(
            "ras_message_processing_duration_seconds", "Message processing duration"
        )

        self.consumer_errors = Counter("ras_consumer_errors_total", "Total consumer errors")

        self.dlq_messages_sent = Counter("ras_dlq_messages_sent_total", "Messages sent to DLQ")

        # Database metrics
        self.db_operations = Counter(
            "ras_db_operations_total", "Total database operations", ["operation", "status"]
        )

        self.db_operation_duration = Histogram(
            "ras_db_operation_duration_seconds", "Database operation duration", ["operation"]
        )

        # Cache metrics
        self.cache_hits_total = Counter("ras_cache_hits_total", "Cache hits")

        self.cache_misses_total = Counter("ras_cache_misses_total", "Cache misses")

        # Business metrics
        self.batches_aggregated = Counter(
            "ras_batches_aggregated_total", "Total batches aggregated"
        )

        self.essays_aggregated = Counter(
            "ras_essays_aggregated_total", "Total essays aggregated", ["phase"]
        )
