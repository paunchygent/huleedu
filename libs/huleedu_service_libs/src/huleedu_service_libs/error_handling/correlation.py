"""Correlation context utilities for HTTP boundaries.

Provides a single, uniform representation of correlation IDs across services,
preserving the original inbound value and a canonical UUID form.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import NAMESPACE_OID, UUID, uuid4, uuid5


@dataclass(frozen=True)
class CorrelationContext:
    """Correlation context extracted at the HTTP boundary.

    - original: the exact value provided by the client (header or query), or a generated string
    - uuid: canonical UUID form used internally for typing/telemetry
    - source: where the value was obtained from (header/query/generated)
    """

    original: str
    uuid: UUID
    source: Literal["header", "query", "generated"]


def extract_correlation_context_from_request(request: Any) -> CorrelationContext:
    """Build a CorrelationContext from a Quart/FastAPI-like request object.

    Order of precedence:
    1) X-Correlation-ID header
    2) correlation_id query parameter
    3) generated value
    """
    # Try header first
    correlation_id = request.headers.get("X-Correlation-ID")
    source: Literal["header", "query", "generated"]

    if correlation_id:
        source = "header"
    else:
        # Try query parameter
        correlation_id = request.args.get("correlation_id")
        if correlation_id:
            source = "query"
        else:
            # Generate new if not found
            correlation_id = str(uuid4())
            source = "generated"

    # Canonical UUID form: parse if valid, else derive deterministically
    try:
        canonical = UUID(correlation_id)
    except Exception:
        canonical = uuid5(NAMESPACE_OID, correlation_id)

    return CorrelationContext(original=correlation_id, uuid=canonical, source=source)

