"""Error handling utilities for HuleEdu services."""

# Legacy imports - will be removed after migration
from huleedu_service_libs.error_handling.class_management_factories import (
    raise_class_not_found,
    raise_course_not_found,
    raise_course_validation_error,
    raise_multiple_course_error,
    raise_student_not_found,
)
from huleedu_service_libs.error_handling.error_detail_factory import (
    create_error_detail_with_context,
)
from huleedu_service_libs.error_handling.factories import (
    raise_ai_feedback_service_error,
    raise_authentication_error,
    raise_authorization_error,
    raise_circuit_breaker_open,
    raise_cj_assessment_service_error,
    raise_configuration_error,
    raise_connection_error,
    raise_content_service_error,
    raise_external_service_error,
    raise_initialization_failed,
    raise_invalid_api_key,
    raise_invalid_configuration,
    raise_invalid_request,
    raise_invalid_response,
    raise_kafka_publish_error,
    raise_missing_required_field,
    raise_nlp_service_error,
    raise_parsing_error,
    raise_processing_error,
    raise_quota_exceeded,
    raise_rate_limit_error,
    raise_request_queued,
    raise_resource_not_found,
    raise_service_unavailable,
    raise_spellcheck_service_error,
    raise_timeout_error,
    raise_unknown_error,
    raise_validation_error,
)

# Framework-specific handlers moved to submodules:
# - FastAPI handlers: from huleedu_service_libs.error_handling.fastapi import register_error_handlers
# - Quart handlers: from huleedu_service_libs.error_handling.quart import register_error_handlers
from huleedu_service_libs.error_handling.file_validation_factories import (
    raise_content_too_long,
    raise_content_too_short,
    raise_empty_content_error,
    raise_raw_storage_failed,
    raise_text_extraction_failed,
    raise_unknown_validation_error,
)
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.error_handling.logging_utils import format_error_for_logging

# Quart handlers moved to submodule (see comment above)
from huleedu_service_libs.error_handling.spellchecker_factories import (
    raise_spell_event_correlation_error,
)
from huleedu_service_libs.error_handling.testing import (
    ErrorCapture,
    ErrorDetailMatcher,
    assert_raises_huleedu_error,
    create_test_error_detail,
    create_test_huleedu_error,
)

__all__ = [
    # Core exception
    "HuleEduError",
    # Core utilities
    "create_error_detail_with_context",
    "format_error_for_logging",
    # Generic error factories
    "raise_unknown_error",
    "raise_validation_error",
    "raise_resource_not_found",
    "raise_configuration_error",
    "raise_external_service_error",
    "raise_kafka_publish_error",
    "raise_content_service_error",
    "raise_spellcheck_service_error",
    "raise_nlp_service_error",
    "raise_ai_feedback_service_error",
    "raise_cj_assessment_service_error",
    "raise_missing_required_field",
    "raise_invalid_configuration",
    "raise_timeout_error",
    "raise_connection_error",
    "raise_service_unavailable",
    "raise_rate_limit_error",
    "raise_quota_exceeded",
    "raise_authentication_error",
    "raise_authorization_error",
    "raise_invalid_api_key",
    "raise_invalid_request",
    "raise_invalid_response",
    "raise_parsing_error",
    "raise_circuit_breaker_open",
    "raise_request_queued",
    "raise_processing_error",
    "raise_initialization_failed",
    # Class management error factories
    "raise_course_not_found",
    "raise_course_validation_error",
    "raise_multiple_course_error",
    "raise_class_not_found",
    "raise_student_not_found",
    # File validation error factories
    "raise_empty_content_error",
    "raise_content_too_short",
    "raise_content_too_long",
    "raise_raw_storage_failed",
    "raise_text_extraction_failed",
    "raise_unknown_validation_error",
    # Spellchecker error factories
    "raise_spell_event_correlation_error",
    # Framework-specific handlers moved to submodules (see imports above)
    # Testing utilities
    "assert_raises_huleedu_error",
    "ErrorCapture",
    "ErrorDetailMatcher",
    "create_test_error_detail",
    "create_test_huleedu_error",
]
