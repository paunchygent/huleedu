from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
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

