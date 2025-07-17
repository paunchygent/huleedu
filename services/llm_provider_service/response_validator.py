"""Response validation utilities for LLM Provider Service.

Performance optimized for sub-500ms response times - Phase 7 enhancement.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict
from uuid import UUID

from common_core import EssayComparisonWinner
from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel, Field, ValidationError

from services.llm_provider_service.exceptions import (
    raise_parsing_error,
    raise_validation_error,
)

logger = create_service_logger("llm_provider_service.response_validator")

# Pre-compiled regex patterns for better performance
WINNER_PATTERN = re.compile(
    rf"^({EssayComparisonWinner.ESSAY_A.value}|{EssayComparisonWinner.ESSAY_B.value})$"
)
WINNER_KEYWORDS = {"a", "essay a", "option a", "first", "left"}
WINNER_B_KEYWORDS = {"b", "essay b", "option b", "second", "right"}


class StandardizedLLMResponse(BaseModel):
    """Standardized response format for LLM comparison results."""

    winner: str = Field(
        description="Which essay is better",
        pattern=rf"^({EssayComparisonWinner.ESSAY_A.value}|{EssayComparisonWinner.ESSAY_B.value})$",
    )
    justification: str = Field(
        description="Brief explanation of the choice (max 50 characters)", max_length=50
    )
    confidence: float = Field(description="Confidence score between 1.0 and 5.0", ge=1.0, le=5.0)


def validate_and_normalize_response(
    raw_response: str | Dict[str, Any],
    provider: str = "unknown",
    correlation_id: UUID | None = None,
) -> StandardizedLLMResponse:
    """Validate and normalize LLM response to standardized format.

    Performance optimized for sub-500ms response times.

    Args:
        raw_response: Raw response from LLM (JSON string or dict)
        provider: Provider name for metrics tracking
        correlation_id: Request correlation ID for error tracking

    Returns:
        Validated and normalized response

    Raises:
        HuleEduError: On validation or parsing failures
    """
    start_time = time.perf_counter()

    try:
        # Fast path: check if already parsed dict
        if isinstance(raw_response, dict):
            parsed_data = raw_response
        else:
            try:
                parsed_data = json.loads(raw_response)
            except json.JSONDecodeError as e:
                _record_validation_metrics(provider, "json_parse", start_time, False)
                raise_parsing_error(
                    service="llm_provider_service",
                    operation="response_validation",
                    parse_target="json",
                    message=f"Invalid JSON format: {str(e)}",
                    correlation_id=correlation_id or UUID(int=0),
                    details={"provider": provider},
                )

        # Fast normalization with minimal string operations
        normalized_data = _fast_normalize_fields(parsed_data)

        # Validate against schema with pre-normalized data
        validated_response = StandardizedLLMResponse.model_validate(normalized_data)

        _record_validation_metrics(provider, "success", start_time, True)
        return validated_response

    except ValidationError as e:
        _record_validation_metrics(provider, "validation_error", start_time, False)
        error_msg = _format_validation_errors(e)
        raise_validation_error(
            service="llm_provider_service",
            operation="response_validation",
            field="response_fields",
            message=f"Validation failed: {error_msg}",
            correlation_id=correlation_id or UUID(int=0),
            details={"provider": provider},
        )

    except Exception as e:
        _record_validation_metrics(provider, "unexpected_error", start_time, False)
        raise_validation_error(
            service="llm_provider_service",
            operation="response_validation",
            field="unknown",
            message=f"Unexpected validation error: {str(e)}",
            correlation_id=correlation_id or UUID(int=0),
            details={"provider": provider},
        )


def _fast_normalize_fields(parsed_data: Dict[str, Any]) -> Dict[str, Any]:
    """Fast field normalization with minimal overhead."""
    # Extract fields with defaults
    winner = parsed_data.get("winner", EssayComparisonWinner.ESSAY_A.value)
    justification = parsed_data.get("justification", "Analysis provided")
    confidence = parsed_data.get("confidence", 3.0)

    # Fast winner normalization using pre-compiled patterns
    if not WINNER_PATTERN.match(winner):
        winner_lower = winner.lower().strip()
        if winner_lower in WINNER_B_KEYWORDS:
            winner = EssayComparisonWinner.ESSAY_B.value
        else:
            winner = EssayComparisonWinner.ESSAY_A.value

    # Fast confidence normalization
    if isinstance(confidence, (int, float)):
        confidence = min(5.0, max(1.0, float(confidence)))
    else:
        confidence = 3.0

    # Efficient justification normalization - keep brief for cost control
    justification = str(justification).strip()
    if len(justification) > 50:
        justification = justification[:47] + "..."
    elif len(justification) < 10:
        justification = justification + " - clear choice"

    return {"winner": winner, "justification": justification, "confidence": confidence}


def _format_validation_errors(e: ValidationError) -> str:
    """Efficiently format validation errors."""
    if len(e.errors()) == 1:
        error = e.errors()[0]
        field = " -> ".join(str(loc) for loc in error["loc"])
        return f"{field}: {error['msg']}"

    return "; ".join(
        f"{' -> '.join(str(loc) for loc in error['loc'])}: {error['msg']}" for error in e.errors()
    )


def _record_validation_metrics(
    provider: str, validation_type: str, start_time: float, success: bool
) -> None:
    """Record validation performance metrics."""
    try:
        from services.llm_provider_service.metrics import get_llm_metrics

        metrics = get_llm_metrics()

        duration = time.perf_counter() - start_time
        validation_metric = metrics.get("llm_validation_duration_seconds")
        if validation_metric:
            validation_metric.labels(provider=provider, validation_type=validation_type).observe(
                duration
            )

        # Log slow validations
        if duration > 0.01:  # 10ms threshold
            logger.warning(
                f"Slow validation detected: {duration:.4f}s for {provider} ({validation_type})"
            )
    except Exception:
        # Don't let metrics recording break validation
        pass


# NOTE: convert_to_internal_format function removed - no longer needed
# as internal models now use the same assessment domain language


def validate_and_normalize_response_fast(
    raw_response: Dict[str, Any],
    provider: str = "unknown",
    correlation_id: UUID | None = None,
) -> StandardizedLLMResponse:
    """Ultra-fast validation for pre-parsed dict responses.

    Optimized for scenarios where JSON is already parsed and we need minimal validation.
    Skips some safety checks for maximum performance.

    Args:
        raw_response: Pre-parsed response dict
        provider: Provider name for metrics tracking
        correlation_id: Request correlation ID for error tracking

    Returns:
        Validated response

    Raises:
        HuleEduError: On validation failures
    """
    start_time = time.perf_counter()

    try:
        # Fast normalization without extensive error checking
        normalized_data = _ultra_fast_normalize_fields(raw_response)

        # Direct model creation without extensive validation
        validated_response = StandardizedLLMResponse.model_construct(**normalized_data)

        _record_validation_metrics(provider, "fast_success", start_time, True)
        return validated_response

    except Exception as e:
        _record_validation_metrics(provider, "fast_error", start_time, False)
        raise_validation_error(
            service="llm_provider_service",
            operation="fast_response_validation",
            field="response_fields",
            message=f"Fast validation error: {str(e)}",
            correlation_id=correlation_id or UUID(int=0),
            details={"provider": provider},
        )


def _ultra_fast_normalize_fields(parsed_data: Dict[str, Any]) -> Dict[str, Any]:
    """Ultra-fast field normalization with minimal safety checks."""
    # Direct field access with minimal validation
    winner = parsed_data.get("winner", EssayComparisonWinner.ESSAY_A.value)
    justification = str(parsed_data.get("justification", "Analysis provided"))
    confidence = float(parsed_data.get("confidence", 3.0))

    # Minimal winner validation - just check first character
    if winner and winner[0].upper() == "B":
        winner = EssayComparisonWinner.ESSAY_B.value
    else:
        winner = EssayComparisonWinner.ESSAY_A.value

    # Simple confidence clamping
    confidence = max(1.0, min(5.0, confidence))

    # Simple justification handling - keep brief for cost control
    justification = justification.strip()
    if len(justification) > 50:
        justification = justification[:50]
    elif len(justification) < 10:
        justification = justification + " - choice"

    return {"winner": winner, "justification": justification, "confidence": confidence}


def batch_validate_responses(
    responses: list[Dict[str, Any]],
    provider: str = "unknown",
    correlation_id: UUID | None = None,
) -> list[StandardizedLLMResponse]:
    """Batch validate multiple responses for improved performance.

    Args:
        responses: List of response dicts to validate
        provider: Provider name for metrics tracking
        correlation_id: Request correlation ID for error tracking

    Returns:
        List of validated responses

    Raises:
        HuleEduError: On batch validation failures
    """
    start_time = time.perf_counter()
    results = []

    try:
        for response in responses:
            result = validate_and_normalize_response_fast(response, provider, correlation_id)
            results.append(result)

        _record_validation_metrics(provider, "batch_success", start_time, True)
        return results

    except Exception as e:
        _record_validation_metrics(provider, "batch_error", start_time, False)
        raise_validation_error(
            service="llm_provider_service",
            operation="batch_response_validation",
            field="batch_responses",
            message=f"Batch validation error: {str(e)}",
            correlation_id=correlation_id or UUID(int=0),
            details={"provider": provider, "processed_count": len(results)},
        )


# JSON Schema for external validation (e.g., in API documentation)
STANDARDIZED_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "winner": {
            "type": "string",
            "enum": [EssayComparisonWinner.ESSAY_A.value, EssayComparisonWinner.ESSAY_B.value],
            "description": (
                f"Which essay is better: '{EssayComparisonWinner.ESSAY_A.value}' "
                f"or '{EssayComparisonWinner.ESSAY_B.value}'"
            ),
        },
        "justification": {
            "type": "string",
            "maxLength": 50,
            "description": "Brief explanation of why this essay was chosen (max 50 characters)",
        },
        "confidence": {
            "type": "number",
            "minimum": 1.0,
            "maximum": 5.0,
            "description": "Confidence score between 1.0 and 5.0",
        },
    },
    "required": ["winner", "justification", "confidence"],
    "additionalProperties": False,
}
