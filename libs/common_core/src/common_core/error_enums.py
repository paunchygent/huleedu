"""
common_core.error_enums - Centralized error code definitions.
"""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    KAFKA_PUBLISH_ERROR = "KAFKA_PUBLISH_ERROR"
    CONTENT_SERVICE_ERROR = "CONTENT_SERVICE_ERROR"
    SPELLCHECK_SERVICE_ERROR = "SPELLCHECK_SERVICE_ERROR"
    NLP_SERVICE_ERROR = "NLP_SERVICE_ERROR"
    AI_FEEDBACK_SERVICE_ERROR = "AI_FEEDBACK_SERVICE_ERROR"
    CJ_ASSESSMENT_SERVICE_ERROR = "CJ_ASSESSMENT_SERVICE_ERROR"
    LLM_PROVIDER_SERVICE_ERROR = "LLM_PROVIDER_SERVICE_ERROR"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"  # For APIs
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"  # For business logic

    # Generic external service errors (can be used by any service)
    TIMEOUT = "TIMEOUT"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    RATE_LIMIT = "RATE_LIMIT"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"  # Access denied / permission denied
    INVALID_API_KEY = "INVALID_API_KEY"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    PARSING_ERROR = "PARSING_ERROR"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
    REQUEST_QUEUED = "REQUEST_QUEUED"
    PROCESSING_ERROR = "PROCESSING_ERROR"  # Internal processing failures
    INITIALIZATION_FAILED = "INITIALIZATION_FAILED"  # Job/process initialization failures


class ClassManagementErrorCode(str, Enum):
    """
    Specific error codes for Class Management Service.
    """

    COURSE_NOT_FOUND = "COURSE_NOT_FOUND"
    COURSE_VALIDATION_ERROR = "COURSE_VALIDATION_ERROR"
    MULTIPLE_COURSE_ERROR = "MULTIPLE_COURSE_ERROR"
    CLASS_NOT_FOUND = "CLASS_NOT_FOUND"
    STUDENT_NOT_FOUND = "STUDENT_NOT_FOUND"


class FileValidationErrorCode(str, Enum):
    """
    Specific error codes for file validation failures.
    """

    EMPTY_CONTENT = "EMPTY_CONTENT"
    CONTENT_TOO_SHORT = "CONTENT_TOO_SHORT"
    CONTENT_TOO_LONG = "CONTENT_TOO_LONG"
    RAW_STORAGE_FAILED = "RAW_STORAGE_FAILED"
    TEXT_EXTRACTION_FAILED = "TEXT_EXTRACTION_FAILED"
    UNKNOWN_VALIDATION_ERROR = "UNKNOWN_VALIDATION_ERROR"


class SpellcheckerErrorCode(str, Enum):
    """
    Business logic specific error codes for spellchecker service operations.

    Note: Common operations use generic ErrorCode enum (CONNECTION_ERROR,
    PROCESSING_ERROR, CONTENT_SERVICE_ERROR, KAFKA_PUBLISH_ERROR, etc.)
    """

    # Spellchecker-specific business logic errors only
    SPELL_EVENT_CORRELATION_ERROR = "SPELL_EVENT_CORRELATION_ERROR"


class LLMErrorCode(str, Enum):
    """
    Error codes specific to LLM Provider Service.

    Covers provider communication, request validation, processing,
    and response handling errors.
    """

    # Provider errors
    PROVIDER_UNAVAILABLE = "LLM_PROVIDER_UNAVAILABLE"
    PROVIDER_RATE_LIMIT = "LLM_PROVIDER_RATE_LIMIT"
    PROVIDER_TIMEOUT = "LLM_PROVIDER_TIMEOUT"
    PROVIDER_API_ERROR = "LLM_PROVIDER_API_ERROR"

    # Request errors
    INVALID_PROMPT = "LLM_INVALID_PROMPT"
    CONTENT_TOO_LONG = "LLM_CONTENT_TOO_LONG"
    INVALID_CONFIG = "LLM_INVALID_CONFIG"

    # Processing errors
    QUEUE_FULL = "LLM_QUEUE_FULL"
    INTERNAL_ERROR = "LLM_INTERNAL_ERROR"
    CALLBACK_TOPIC_MISSING = "LLM_CALLBACK_TOPIC_MISSING"
    INVALID_CALLBACK_TOPIC = "LLM_INVALID_CALLBACK_TOPIC"

    # Response errors
    PARSING_ERROR = "LLM_PARSING_ERROR"
    INVALID_RESPONSE = "LLM_INVALID_RESPONSE"
    COST_LIMIT_EXCEEDED = "LLM_COST_LIMIT_EXCEEDED"

    # System errors
    CONFIGURATION_ERROR = "LLM_CONFIGURATION_ERROR"


class BatchConductorErrorCode(str, Enum):
    """
    Specific error codes for Batch Conductor Service pipeline operations.
    
    These codes provide domain-specific error classification for pipeline
    dependency resolution, cycle detection, and compatibility validation.
    Follows service-specific enum pattern for architectural consistency.
    """
    
    PIPELINE_DEPENDENCY_RESOLUTION_FAILED = "BCS_PIPELINE_DEPENDENCY_RESOLUTION_FAILED"
    PIPELINE_DEPENDENCY_CYCLE_DETECTED = "BCS_PIPELINE_DEPENDENCY_CYCLE_DETECTED"
    PIPELINE_COMPATIBILITY_FAILED = "BCS_PIPELINE_COMPATIBILITY_FAILED"


class CJAssessmentErrorCode(str, Enum):
    """
    CJ Assessment Service domain-specific error codes.
    
    These codes represent errors unique to the Comparative Judgement algorithm
    and callback correlation system. Generic errors like timeouts or external
    service failures should use the base ErrorCode enum.
    """
    
    # Comparative Judgement Algorithm Specifics
    CJ_INSUFFICIENT_COMPARISONS = "CJ_INSUFFICIENT_COMPARISONS"  # Not enough comparisons for reliable scoring
    CJ_SCORE_CONVERGENCE_FAILED = "CJ_SCORE_CONVERGENCE_FAILED"  # Bradley-Terry didn't converge
    CJ_COMPARISON_IMBALANCE = "CJ_COMPARISON_IMBALANCE"  # Some essays over/under compared
    
    # CJ Callback Correlation
    CJ_CALLBACK_CORRELATION_FAILED = "CJ_CALLBACK_CORRELATION_FAILED"  # Can't match callback to comparison pair
