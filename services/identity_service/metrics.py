from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge

# General request metrics
REQUEST_COUNT = Counter(
    "identity_requests_total",
    "Total number of identity requests",
    labelnames=("route", "method", "status"),
)

REQUEST_LATENCY = Histogram(
    "identity_request_duration_seconds",
    "Latency of identity requests",
    labelnames=("route",),
)

# Authentication-specific metrics
AUTHENTICATION_ATTEMPTS = Counter(
    "identity_authentication_attempts_total",
    "Total number of authentication attempts",
    labelnames=("status", "failure_reason"),
)

TOKEN_ISSUANCE = Counter(
    "identity_tokens_issued_total",
    "Total number of tokens issued",
    labelnames=("token_type",),
)

PASSWORD_RESET_REQUESTS = Counter(
    "identity_password_reset_requests_total",
    "Total number of password reset requests",
    labelnames=("status",),
)

ACTIVE_SESSIONS = Gauge(
    "identity_active_sessions",
    "Number of currently active user sessions",
)

FAILED_LOGIN_ATTEMPTS = Histogram(
    "identity_failed_login_attempts",
    "Distribution of failed login attempts per user",
    buckets=(1, 2, 3, 5, 10, 25, 50),
)

TOKEN_REVOCATIONS = Counter(
    "identity_token_revocations_total",
    "Total number of token revocations",
    labelnames=("token_type", "reason"),
)

ACCOUNT_LOCKOUTS = Counter(
    "identity_account_lockouts_total",
    "Total number of account lockouts",
    labelnames=("reason",),
)
