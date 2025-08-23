from __future__ import annotations

from typing import List, Optional

from common_core.metadata_models import PersonNameV1
from pydantic import BaseModel, EmailStr

# Reuse the cross-cutting person name model from common_core
# Keep the historical name for backward compatibility in imports/tests
PersonNameSchema = PersonNameV1


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    person_name: PersonNameSchema
    organization_name: str
    org_id: Optional[str] = None


class RegisterResponse(BaseModel):
    user_id: str
    email: EmailStr
    org_id: Optional[str] = None
    email_verification_required: bool = True


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class MeResponse(BaseModel):
    user_id: str
    email: EmailStr
    org_id: Optional[str] = None
    roles: List[str] = []
    email_verified: bool = False


class RequestEmailVerificationRequest(BaseModel):
    pass


class RequestEmailVerificationResponse(BaseModel):
    message: str
    correlation_id: str


class VerifyEmailRequest(BaseModel):
    token: str


class VerifyEmailResponse(BaseModel):
    message: str


class RequestPasswordResetRequest(BaseModel):
    email: EmailStr


class RequestPasswordResetResponse(BaseModel):
    message: str
    correlation_id: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ResetPasswordResponse(BaseModel):
    message: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class IntrospectRequest(BaseModel):
    token: str


class IntrospectResponse(BaseModel):
    active: bool
    sub: str | None = None
    exp: int | None = None
    iat: int | None = None
    jti: str | None = None
    org_id: str | None = None
    roles: list[str] = []
    token_type: str = "access_token"


class RevokeTokenRequest(BaseModel):
    token: str
    token_type_hint: str = "refresh_token"


class RevokeTokenResponse(BaseModel):
    revoked: bool


class ProfileResponse(BaseModel):
    """Response schema for profile operations."""

    person_name: PersonNameSchema
    display_name: Optional[str] = None
    locale: Optional[str] = None


class ProfileRequest(BaseModel):
    """Request schema for profile updates."""

    first_name: str
    last_name: str
    display_name: Optional[str] = None
    locale: Optional[str] = None
