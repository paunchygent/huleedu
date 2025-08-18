from __future__ import annotations

from datetime import datetime
from typing import Dict, Literal

from pydantic import BaseModel, EmailStr, Field


class NotificationEmailRequestedV1(BaseModel):
    message_id: str
    template_id: str
    to: EmailStr
    variables: Dict[str, str] = Field(default_factory=dict)
    category: Literal[
        "verification",
        "password_reset",
        "receipt",
        "teacher_notification",
        "system",
    ]
    correlation_id: str


class EmailSentV1(BaseModel):
    message_id: str
    provider: str
    sent_at: datetime
    correlation_id: str


class EmailDeliveryFailedV1(BaseModel):
    message_id: str
    provider: str
    failed_at: datetime
    reason: str
    correlation_id: str
