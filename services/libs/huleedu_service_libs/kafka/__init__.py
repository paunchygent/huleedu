"""
Kafka utilities for HuleEdu microservices.

This package provides resilient Kafka components with circuit breaker protection
and fallback handling for improved reliability in distributed systems.
"""

from huleedu_service_libs.kafka.fallback_handler import FallbackMessageHandler
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher

__all__ = ["ResilientKafkaPublisher", "FallbackMessageHandler"]
