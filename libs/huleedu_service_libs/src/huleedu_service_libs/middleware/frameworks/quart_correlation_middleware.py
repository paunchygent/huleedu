"""Correlation context middleware for Quart applications."""

from __future__ import annotations

from typing import TYPE_CHECKING

from quart import g, request

from huleedu_service_libs.error_handling.correlation import (
    CorrelationContext,
    extract_correlation_context_from_request,
)

if TYPE_CHECKING:
    from quart import Quart


def setup_correlation_middleware(app: Quart) -> None:
    """Attach a CorrelationContext to each request in Quart globals (g).

    - Extracts from header/query or generates new value
    - Exposes both original string and canonical UUID forms
    """

    @app.before_request
    async def _set_correlation_context() -> None:  # pragma: no cover - exercised via integration
        ctx: CorrelationContext = extract_correlation_context_from_request(request)
        g.correlation_context = ctx
        # Backwards-compatible convenience accessors
        g.correlation_id = ctx.original
