from __future__ import annotations

from quart import Blueprint, jsonify, request
from quart_dishka import inject
from dishka import FromDishka

from services.identity_service.api.schemas import (
    LoginRequest,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
    TokenPair,
)
import time
from services.identity_service.protocols import PasswordHasher, TokenIssuer, UserRepo, SessionRepo

bp = Blueprint("auth", __name__, url_prefix="/v1/auth")


@bp.post("/register")
@inject
async def register(
    user_repo: FromDishka[UserRepo], hasher: FromDishka[PasswordHasher]
):
    payload = RegisterRequest(**(await request.get_json()))
    user = await user_repo.create_user(
        payload.email, payload.org_id, hasher.hash(payload.password)
    )
    return jsonify(RegisterResponse(**user).model_dump(mode="json")), 201


@bp.post("/login")
@inject
async def login(
    user_repo: FromDishka[UserRepo],
    tokens: FromDishka[TokenIssuer],
    hasher: FromDishka[PasswordHasher],
    sessions: FromDishka[SessionRepo],
):
    payload = LoginRequest(**(await request.get_json()))
    user = await user_repo.get_user_by_email(payload.email)
    if not user:
        return jsonify({"error": "invalid_credentials"}), 401
    # Verify password
    if not hasher.verify(user.get("password_hash", ""), payload.password):
        return jsonify({"error": "invalid_credentials"}), 401
    access = tokens.issue_access_token(
        user_id=user["id"], org_id=user.get("org_id"), roles=user.get("roles", [])
    )
    refresh, jti = tokens.issue_refresh_token(user_id=user["id"])
    # Store refresh session
    await sessions.store_refresh(user_id=user["id"], jti=jti, exp_ts=int(time.time()) + 86400)
    pair = TokenPair(access_token=access, refresh_token=refresh, expires_in=3600)
    return jsonify(pair.model_dump(mode="json"))


@bp.get("/me")
async def me():
    # In production, validate JWT via API Gateway
    return jsonify(MeResponse(user_id="dev", email="dev@example.com").model_dump(mode="json"))
