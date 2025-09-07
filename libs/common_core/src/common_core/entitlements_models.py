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


class CreditCheckRequestV1(BaseModel):
    user_id: str
    org_id: Optional[str] = None
    metric: str
    amount: int = 1


class CreditCheckResponseV1(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    required_credits: int
    available_credits: int
    source: Optional[str] = None  # "user" or "org"


class CreditConsumptionV1(BaseModel):
    user_id: str
    org_id: Optional[str] = None
    metric: str
    amount: int
    batch_id: Optional[str] = None
    correlation_id: str


# Bulk credit check models (shared between BOS and Entitlements)
class BulkCreditCheckRequestV1(BaseModel):
    user_id: str
    org_id: Optional[str] = None
    requirements: dict[str, int]
    correlation_id: Optional[str] = None


class PerMetricCreditStatusV1(BaseModel):
    required: int
    available: int
    allowed: bool
    source: Optional[str] = None  # "user" or "org"
    reason: Optional[str] = (
        None  # e.g., "insufficient_credits" | "rate_limit_exceeded" | "policy_denied"
    )


class BulkCreditCheckResponseV1(BaseModel):
    allowed: bool
    required_credits: int
    available_credits: int
    per_metric: dict[str, PerMetricCreditStatusV1]
    denial_reason: Optional[str] = None
    correlation_id: str
