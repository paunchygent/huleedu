"""Factory functions for Batch Conductor Service specific errors.

This module provides standardized factory functions for Batch Conductor Service
pipeline-specific error scenarios that require additional context beyond generic factories.

For common operations, use generic factory functions from factories.py:
- Unknown pipeline: raise_resource_not_found (resource_type="pipeline")
- Configuration errors: raise_configuration_error
- Processing errors: raise_processing_error
- External service errors: raise_external_service_error
"""

from typing import Any, NoReturn, Optional
from uuid import UUID

from common_core.error_enums import BatchConductorErrorCode

from .error_detail_factory import create_error_detail_with_context
from .huleedu_error import HuleEduError

# =============================================================================
# Batch Conductor Service Specific Pipeline Error Factories
# =============================================================================


def raise_pipeline_dependency_resolution_failed(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    batch_id: Optional[str] = None,
    requested_pipeline: Optional[str] = None,
    resolution_stage: Optional[str] = None,
    dependency_error: Optional[str] = None,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a pipeline dependency resolution failure error.

    Use this for complex pipeline dependency resolution failures that require
    batch context, pipeline information, and resolution stage details.

    Args:
        service: The service name raising the error
        operation: The operation being performed when the error occurred
        message: Human-readable error message
        correlation_id: Correlation ID for request tracing
        batch_id: Optional batch ID being processed
        requested_pipeline: Optional pipeline name that failed resolution
        resolution_stage: Optional stage where resolution failed (e.g., "dependency_analysis", "topological_sort")
        dependency_error: Optional underlying dependency error details
        **additional_context: Additional error context details
    """
    details = {
        "batch_id": batch_id,
        "requested_pipeline": requested_pipeline,
        "resolution_stage": resolution_stage,
        "dependency_error": dependency_error,
        **additional_context,
    }

    error_detail = create_error_detail_with_context(
        error_code=BatchConductorErrorCode.PIPELINE_DEPENDENCY_RESOLUTION_FAILED,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=details,
    )
    raise HuleEduError(error_detail)


def raise_pipeline_dependency_cycle_detected(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    pipeline_name: Optional[str] = None,
    cycle_steps: Optional[list[str]] = None,
    detection_stage: Optional[str] = None,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a pipeline dependency cycle detection error.

    Use this for circular dependency detection in pipeline configurations
    that require cycle information and detection context.

    Args:
        service: The service name raising the error
        operation: The operation being performed when the error occurred
        message: Human-readable error message
        correlation_id: Correlation ID for request tracing
        pipeline_name: Optional pipeline name where cycle was detected
        cycle_steps: Optional list of steps involved in the cycle
        detection_stage: Optional stage where cycle was detected (e.g., "configuration_validation", "topological_sort")
        **additional_context: Additional error context details
    """
    details = {
        "pipeline_name": pipeline_name,
        "cycle_steps": cycle_steps,
        "detection_stage": detection_stage,
        **additional_context,
    }

    error_detail = create_error_detail_with_context(
        error_code=BatchConductorErrorCode.PIPELINE_DEPENDENCY_CYCLE_DETECTED,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=details,
    )
    raise HuleEduError(error_detail)


def raise_pipeline_compatibility_failed(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    pipeline_name: Optional[str] = None,
    batch_metadata: Optional[dict[str, Any]] = None,
    compatibility_issue: Optional[str] = None,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a pipeline compatibility validation error.

    Use this for pipeline compatibility validation failures that require
    pipeline information and batch metadata context.

    Args:
        service: The service name raising the error
        operation: The operation being performed when the error occurred
        message: Human-readable error message
        correlation_id: Correlation ID for request tracing
        pipeline_name: Optional pipeline name that failed compatibility check
        batch_metadata: Optional batch metadata that caused compatibility issue
        compatibility_issue: Optional description of the compatibility issue
        **additional_context: Additional error context details
    """
    details = {
        "pipeline_name": pipeline_name,
        "batch_metadata": batch_metadata,
        "compatibility_issue": compatibility_issue,
        **additional_context,
    }

    error_detail = create_error_detail_with_context(
        error_code=BatchConductorErrorCode.PIPELINE_COMPATIBILITY_FAILED,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=details,
    )
    raise HuleEduError(error_detail)
