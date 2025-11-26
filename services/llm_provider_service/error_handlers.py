"""LLM Provider Service error handlers with metrics integration.

Extracts provider/model context from error details for Prometheus metrics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.error_handling.quart_handlers import create_error_response
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Response

from services.llm_provider_service.metrics import get_metrics

if TYPE_CHECKING:
    from quart import Quart

logger = create_service_logger("llm_provider_service.error_handlers")


def register_lps_error_handlers(app: Quart) -> None:
    """Register LPS-specific error handlers with metrics integration.

    Extends the libs error handling pattern with LPS-specific metrics.
    Uses create_error_response factory for consistent response structure.

    Args:
        app: The Quart application instance
    """
    metrics = get_metrics()

    @app.errorhandler(HuleEduError)
    async def handle_huleedu_error(error: HuleEduError) -> Tuple[Response, int]:
        """Handle HuleEduError with metrics tracking."""
        details = error.error_detail.details
        provider = details.get("provider", "unknown")
        model = details.get("model", "unknown")
        error_type = details.get("error_type", error.error_detail.error_code.value)

        # Increment error metrics with provider/model context
        metrics["llm_requests_total"].labels(
            provider=provider,
            model=model,
            request_type="comparison",
            status="failed",
        ).inc()

        metrics["llm_provider_errors_total"].labels(
            provider=provider,
            model=model,
            error_type=str(error_type),
        ).inc()

        # Log with structured context
        logger.error(
            f"HuleEduError: {error.error_detail.message}",
            extra={
                "correlation_id": str(error.error_detail.correlation_id),
                "error_code": error.error_detail.error_code.value,
                "provider": provider,
                "model": model,
                "error_type": error_type,
            },
        )

        return create_error_response(error.error_detail)
