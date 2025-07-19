"""FastAPI-specific error handling for HuleEdu services."""

from huleedu_service_libs.error_handling.fastapi_handlers import (
    extract_correlation_id,
    register_error_handlers,
)

__all__ = [
    "register_error_handlers",
    "extract_correlation_id",
]
