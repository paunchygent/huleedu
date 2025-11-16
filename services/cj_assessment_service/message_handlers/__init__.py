"""Message handlers for CJ Assessment Service.

This module contains handlers for different types of Kafka messages processed
by the CJ Assessment Service.
"""

from services.cj_assessment_service.message_handlers.cj_request_handler import (
    handle_cj_assessment_request,
)
from services.cj_assessment_service.message_handlers.llm_callback_handler import (
    handle_llm_comparison_callback,
)

__all__ = [
    "handle_cj_assessment_request",
    "handle_llm_comparison_callback",
]
