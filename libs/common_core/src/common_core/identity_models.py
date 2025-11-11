"""Identity Service event models for authentication and user management.

Event data models for identity events (user registration, email verification,
password reset, login). Used by Identity Service to publish auth lifecycle events.

See: libs/common_core/docs/identity-threading.md
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr

from common_core.identity_enums import LoginFailureReason


class UserRegisteredV1(BaseModel):
    """User registration event data.

    Producer: Identity Service
    Consumers: Email Service (welcome email), Entitlements Service (create quota)
    """

    user_id: str
    org_id: Optional[str] = None  # Org context if user registered under organization
    email: EmailStr
    registered_at: datetime
    correlation_id: str


class EmailVerificationRequestedV1(BaseModel):
    """Email verification request event data.

    Producer: Identity Service
    Consumer: Email Service (sends verification email)
    """

    user_id: str
    email: EmailStr
    verification_token: str
    expires_at: datetime
    correlation_id: str


class EmailVerifiedV1(BaseModel):
    """Email verification completion event data.

    Producer: Identity Service
    Consumers: Entitlements Service (activate account), Analytics
    """

    user_id: str
    verified_at: datetime
    correlation_id: str


class PasswordResetRequestedV1(BaseModel):
    """Password reset request event data.

    Producer: Identity Service
    Consumer: Email Service (sends reset email)
    """

    user_id: str
    email: EmailStr
    token_id: str
    expires_at: datetime
    correlation_id: str


class PasswordResetCompletedV1(BaseModel):
    """Password reset completion event data.

    Producer: Identity Service
    Consumers: Analytics, Audit logging
    """

    user_id: str
    reset_at: datetime
    correlation_id: str


class LoginSucceededV1(BaseModel):
    """Successful login event data.

    Producer: Identity Service
    Consumers: Analytics, Audit logging
    """

    user_id: str
    org_id: Optional[str] = None  # Org context if org-scoped login
    timestamp: datetime
    correlation_id: str


class LoginFailedV1(BaseModel):
    """Failed login attempt event data.

    Producer: Identity Service
    Consumers: Security monitoring, Rate limiting
    """

    email: EmailStr
    reason: LoginFailureReason
    timestamp: datetime
    correlation_id: str


class JwksPublicKeyV1(BaseModel):
    """JWKS public key for JWT signature verification.

    Used in JWKS endpoint response for API Gateway to verify JWT tokens.
    Standard RFC 7517 format.
    """

    kid: str  # Key ID
    kty: str  # Key type (RSA)
    n: str  # RSA modulus
    e: str  # RSA exponent
    alg: Literal["RS256"] = "RS256"  # Algorithm
    use: Literal["sig"] = "sig"  # Key use (signature)


class JwksResponseV1(BaseModel):
    """JWKS endpoint response containing public keys.

    Standard RFC 7517 JWKS format. API Gateway fetches this to verify
    JWT tokens issued by Identity Service.
    """

    keys: List[JwksPublicKeyV1]
