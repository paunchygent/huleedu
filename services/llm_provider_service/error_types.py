"""LLM Provider Service specific error types."""

from enum import Enum


class LLMProviderErrorType(str, Enum):
    """LLM-specific error types that extend the generic ErrorCode enum."""

    # LLM-specific request errors
    CONTEXT_LENGTH_EXCEEDED = "context_length_exceeded"

    # LLM cost and billing errors
    COST_LIMIT_EXCEEDED = "cost_limit_exceeded"
    BILLING_ERROR = "billing_error"

    # LLM provider-specific errors
    MODEL_NOT_AVAILABLE = "model_not_available"
    PROVIDER_ERROR = "provider_error"

    # LLM response quality errors
    INCOMPLETE_RESPONSE = "incomplete_response"
    SAFETY_FILTER_TRIGGERED = "safety_filter_triggered"


class LLMAlertType(str, Enum):
    """Alert types for LLM cost and usage monitoring."""

    DAILY_LIMIT = "daily_limit"
    MONTHLY_LIMIT = "monthly_limit"
    RATE_SPIKE = "rate_spike"
    PROVIDER_DOWN = "provider_down"
    HIGH_ERROR_RATE = "high_error_rate"
    UNUSUAL_USAGE_PATTERN = "unusual_usage_pattern"
