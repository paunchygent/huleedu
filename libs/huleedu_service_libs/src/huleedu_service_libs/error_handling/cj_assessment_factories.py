"""Factory functions for CJ Assessment Service domain-specific errors.

This module provides factory functions ONLY for errors that are truly unique
to the Comparative Judgement algorithm. These are domain-specific errors that
have no generic equivalent.

For common operations, use generic factory functions from factories.py:
- External service errors: raise_external_service_error
- Processing errors: raise_processing_error
- Validation errors: raise_validation_error
- Kafka errors: raise_kafka_publish_error
- Content service errors: raise_content_service_error
"""

from typing import Any, NoReturn, Optional
from uuid import UUID

from common_core.error_enums import CJAssessmentErrorCode

from .error_detail_factory import create_error_detail_with_context
from .huleedu_error import HuleEduError

# =============================================================================
# CJ Assessment Domain-Specific Error Factories
# =============================================================================


def raise_cj_insufficient_comparisons(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    batch_id: Optional[str] = None,
    comparison_count: Optional[int] = None,
    required_count: Optional[int] = None,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a CJ insufficient comparisons error.

    Use this when there aren't enough valid comparisons to compute reliable
    Bradley-Terry scores. This is a domain-specific error unique to the
    Comparative Judgement algorithm.

    Args:
        service: The service name raising the error
        operation: The operation being performed when the error occurred
        message: Human-readable error message
        correlation_id: Correlation ID for request tracing
        batch_id: Optional batch ID being processed
        comparison_count: Optional number of comparisons available
        required_count: Optional minimum comparisons required
        **additional_context: Additional error context details
    """
    details = {
        "batch_id": batch_id,
        "comparison_count": comparison_count,
        "required_count": required_count,
        **additional_context,
    }

    error_detail = create_error_detail_with_context(
        error_code=CJAssessmentErrorCode.CJ_INSUFFICIENT_COMPARISONS,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=details,
    )
    raise HuleEduError(error_detail)


def raise_cj_score_convergence_failed(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    batch_id: Optional[str] = None,
    iteration_count: Optional[int] = None,
    convergence_error: Optional[str] = None,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a CJ score convergence failure error.

    Use this when the Bradley-Terry iterative algorithm fails to converge
    within the maximum number of iterations or encounters mathematical errors.
    This is specific to the Comparative Judgement scoring algorithm.

    Args:
        service: The service name raising the error
        operation: The operation being performed when the error occurred
        message: Human-readable error message
        correlation_id: Correlation ID for request tracing
        batch_id: Optional batch ID being processed
        iteration_count: Optional number of iterations attempted
        convergence_error: Optional description of convergence issue
        **additional_context: Additional error context details
    """
    details = {
        "batch_id": batch_id,
        "iteration_count": iteration_count,
        "convergence_error": convergence_error,
        **additional_context,
    }

    error_detail = create_error_detail_with_context(
        error_code=CJAssessmentErrorCode.CJ_SCORE_CONVERGENCE_FAILED,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=details,
    )
    raise HuleEduError(error_detail)


def raise_cj_comparison_imbalance(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    batch_id: Optional[str] = None,
    imbalance_details: Optional[dict[str, int]] = None,
    min_comparisons: Optional[int] = None,
    max_comparisons: Optional[int] = None,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a CJ comparison imbalance error.

    Use this when the distribution of comparisons across essays is severely
    imbalanced, which could lead to unreliable rankings. This is specific
    to the Comparative Judgement pair generation algorithm.

    Args:
        service: The service name raising the error
        operation: The operation being performed when the error occurred
        message: Human-readable error message
        correlation_id: Correlation ID for request tracing
        batch_id: Optional batch ID being processed
        imbalance_details: Optional dict of essay_id to comparison count
        min_comparisons: Optional minimum comparisons per essay
        max_comparisons: Optional maximum comparisons per essay
        **additional_context: Additional error context details
    """
    details = {
        "batch_id": batch_id,
        "imbalance_details": imbalance_details,
        "min_comparisons": min_comparisons,
        "max_comparisons": max_comparisons,
        **additional_context,
    }

    error_detail = create_error_detail_with_context(
        error_code=CJAssessmentErrorCode.CJ_COMPARISON_IMBALANCE,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=details,
    )
    raise HuleEduError(error_detail)


def raise_cj_callback_correlation_failed(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    callback_correlation_id: Optional[UUID] = None,
    batch_id: Optional[str] = None,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a CJ callback correlation failure error.

    Use this when an LLM callback cannot be correlated to its original
    comparison pair. This is specific to the CJ Assessment Service's
    callback processing system.

    Args:
        service: The service name raising the error
        operation: The operation being performed when the error occurred
        message: Human-readable error message
        correlation_id: Correlation ID for request tracing
        callback_correlation_id: Optional correlation ID from the callback
        batch_id: Optional batch ID if known
        **additional_context: Additional error context details
    """
    details = {
        "callback_correlation_id": callback_correlation_id,
        "batch_id": batch_id,
        **additional_context,
    }

    error_detail = create_error_detail_with_context(
        error_code=CJAssessmentErrorCode.CJ_CALLBACK_CORRELATION_FAILED,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=details,
    )
    raise HuleEduError(error_detail)
