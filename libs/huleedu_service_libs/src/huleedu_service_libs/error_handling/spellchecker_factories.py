"""Factory functions for Spellchecker Service specific errors.

Only contains service-specific error patterns that have no generic equivalent.
For common operations, use generic factory functions from factories.py:
- Database errors: raise_connection_error, raise_processing_error
- Content service errors: raise_content_service_error
- Kafka errors: raise_kafka_publish_error
- Algorithm errors: raise_processing_error
- Configuration errors: raise_configuration_error
"""

from typing import Any, NoReturn, Optional
from uuid import UUID

from common_core.error_enums import SpellcheckerErrorCode

from .error_detail_factory import create_error_detail_with_context
from .huleedu_error import HuleEduError

# =============================================================================
# Spellchecker-Specific Business Logic Error Factories
# =============================================================================


def raise_spell_event_correlation_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    missing_field: Optional[str] = None,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a spell event correlation error.

    Use this for spellchecker-specific correlation ID extraction/validation
    issues from Kafka event messages.
    """
    details = additional_context.copy()
    if missing_field is not None:
        details["missing_field"] = missing_field

    error_detail = create_error_detail_with_context(
        error_code=SpellcheckerErrorCode.SPELL_EVENT_CORRELATION_ERROR,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=details,
    )
    raise HuleEduError(error_detail)
