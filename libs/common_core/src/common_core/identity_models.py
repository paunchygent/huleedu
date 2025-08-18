from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr


class UserRegisteredV1(BaseModel):
    user_id: str
    org_id: Optional[str] = None
    email: EmailStr
    registered_at: datetime
    correlation_id: str


class EmailVerificationRequestedV1(BaseModel):
    user_id: str
    email: EmailStr
    token_id: str
    expires_at: datetime
    correlation_id: str


class EmailVerifiedV1(BaseModel):
    user_id: str
    verified_at: datetime
    correlation_id: str


class PasswordResetRequestedV1(BaseModel):
    user_id: str
    email: EmailStr
    token_id: str
    expires_at: datetime
    correlation_id: str


class LoginSucceededV1(BaseModel):
    user_id: str
    org_id: Optional[str] = None
    timestamp: datetime
    correlation_id: str


class LoginFailedV1(BaseModel):
    email: EmailStr
    reason: Literal["invalid_credentials", "locked", "unverified", "other"]
    timestamp: datetime
    correlation_id: str


class JwksPublicKeyV1(BaseModel):
    kid: str
    kty: str
    n: str
    e: str
    alg: Literal["RS256"] = "RS256"
    use: Literal["sig"] = "sig"


class JwksResponseV1(BaseModel):
    keys: List[JwksPublicKeyV1]
