from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

SubjectType = Literal["org", "user"]


class SubjectRefV1(BaseModel):
    type: SubjectType
    id: str  # uuid


class EntitlementDefinitionV1(BaseModel):
    feature: str  # e.g., "batch_process", "ai_tool_usage", "essay_assessed"
    limit_per_window: Optional[int] = None  # None means unlimited
    window_seconds: Optional[int] = None  # e.g., per 60s or per 30 days (2592000)
    cost_per_unit: Optional[float] = None  # for metered billing/pay-as-you-go


class PlanV1(BaseModel):
    plan_id: str
    name: str
    entitlements: List[EntitlementDefinitionV1]


class SubscriptionActivatedV1(BaseModel):
    subject: SubjectRefV1
    plan_id: str
    activated_at: datetime
    correlation_id: str


class SubscriptionChangedV1(BaseModel):
    subject: SubjectRefV1
    old_plan_id: Optional[str] = None
    new_plan_id: str
    changed_at: datetime
    correlation_id: str


class SubscriptionCanceledV1(BaseModel):
    subject: SubjectRefV1
    plan_id: str
    canceled_at: datetime
    correlation_id: str


class UsageAuthorizedV1(BaseModel):
    subject: SubjectRefV1
    metric: str
    amount: int = 1
    authorization_id: str
    expires_at: Optional[datetime] = None
    correlation_id: str


class UsageRecordedV1(BaseModel):
    subject: SubjectRefV1
    metric: str
    amount: int = 1
    period_start: datetime
    period_end: datetime
    correlation_id: str


class CreditBalanceChangedV1(BaseModel):
    subject: SubjectRefV1
    delta: int
    new_balance: int
    reason: str
    correlation_id: str


class RateLimitExceededV1(BaseModel):
    subject: SubjectRefV1
    metric: str
    limit: int
    window_seconds: int
    correlation_id: str


class ResourceAccessGrantedV1(BaseModel):
    resource_id: str
    subject: SubjectRefV1 | None = None
    email_hash: Optional[str] = None  # hashed student email for privacy
    rights: List[str] = ["read"]
    expires_at: Optional[datetime] = None
    correlation_id: str
