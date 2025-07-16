"""
Standardized, PURE data models for all services.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from common_core.error_enums import ErrorCode


class ErrorDetail(BaseModel):
    """
    The canonical, PURE data model for an error in the HuleEdu platform.
    This model contains only data fields and no behavior.
    """

    error_code: ErrorCode
    message: str
    correlation_id: UUID
    timestamp: datetime
    service: str
    operation: str
    details: dict[str, Any] = Field(default_factory=dict)
    stack_trace: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

    model_config = ConfigDict(frozen=True)
