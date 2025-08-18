from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from services.identity_service.models_db import (
    EmailVerificationToken,
    PasswordResetToken,
    RefreshSession,
    User,
)
from services.identity_service.protocols import SessionRepo, UserRepo


class PostgresUserRepo(UserRepo):
    def __init__(self, engine: AsyncEngine) -> None:
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def create_user(self, email: str, org_id: str | None, password_hash: str) -> dict:
        async with self._session_factory() as session:
            user = User(
                email=email.lower(),
                org_id=org_id,
                password_hash=password_hash,
                roles=["teacher"],
                registered_at=datetime.now(UTC),
            )
            session.add(user)
            await session.flush()
            await session.commit()
            return {
                "id": str(user.id),
                "email": user.email,
                "org_id": user.org_id,
                "roles": user.roles or [],
                "email_verified": user.email_verified,
                "registered_at": user.registered_at,
            }

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        async with self._session_factory() as session:
            stmt = select(User).where(User.email == email.lower())
            res = await session.execute(stmt)
            user = res.scalar_one_or_none()
            if not user:
                return None
            return {
                "id": str(user.id),
                "email": user.email,
                "org_id": user.org_id,
                "roles": user.roles or [],
                "email_verified": user.email_verified,
                "registered_at": user.registered_at,
                "password_hash": user.password_hash,
            }

    async def set_email_verified(self, user_id: str) -> None:
        async with self._session_factory() as session:
            stmt = (
                update(User)
                .where(User.id == UUID(str(user_id)))
                .values(email_verified=True)
                .execution_options(synchronize_session="fetch")
            )
            await session.execute(stmt)
            await session.commit()

    async def create_email_verification_token(
        self, user_id: str, token: str, expires_at: datetime
    ) -> dict:
        async with self._session_factory() as session:
            verification_token = EmailVerificationToken(
                user_id=UUID(str(user_id)),
                token=token,
                expires_at=expires_at,
            )
            session.add(verification_token)
            await session.flush()
            await session.commit()
            return {
                "id": str(verification_token.id),
                "user_id": str(verification_token.user_id),
                "token": verification_token.token,
                "expires_at": verification_token.expires_at,
                "created_at": verification_token.created_at,
                "used_at": verification_token.used_at,
            }

    async def get_email_verification_token(self, token: str) -> Optional[dict]:
        async with self._session_factory() as session:
            stmt = select(EmailVerificationToken).where(EmailVerificationToken.token == token)
            res = await session.execute(stmt)
            verification_token = res.scalar_one_or_none()
            if not verification_token:
                return None
            return {
                "id": str(verification_token.id),
                "user_id": str(verification_token.user_id),
                "token": verification_token.token,
                "expires_at": verification_token.expires_at,
                "created_at": verification_token.created_at,
                "used_at": verification_token.used_at,
            }

    async def mark_token_used(self, token_id: str) -> None:
        async with self._session_factory() as session:
            stmt = (
                update(EmailVerificationToken)
                .where(EmailVerificationToken.id == UUID(str(token_id)))
                .values(used_at=datetime.now(UTC))
                .execution_options(synchronize_session="fetch")
            )
            await session.execute(stmt)
            await session.commit()

    async def invalidate_user_tokens(self, user_id: str) -> None:
        async with self._session_factory() as session:
            stmt = (
                update(EmailVerificationToken)
                .where(EmailVerificationToken.user_id == UUID(str(user_id)))
                .where(EmailVerificationToken.used_at.is_(None))
                .values(used_at=datetime.now(UTC))
                .execution_options(synchronize_session="fetch")
            )
            await session.execute(stmt)
            await session.commit()

    async def create_password_reset_token(
        self, user_id: str, token: str, expires_at: datetime
    ) -> dict:
        async with self._session_factory() as session:
            reset_token = PasswordResetToken(
                user_id=UUID(str(user_id)),
                token=token,
                expires_at=expires_at,
            )
            session.add(reset_token)
            await session.flush()
            await session.commit()
            return {
                "id": str(reset_token.id),
                "user_id": str(reset_token.user_id),
                "token": reset_token.token,
                "expires_at": reset_token.expires_at,
                "created_at": reset_token.created_at,
                "used_at": reset_token.used_at,
            }

    async def get_password_reset_token(self, token: str) -> Optional[dict]:
        async with self._session_factory() as session:
            stmt = select(PasswordResetToken).where(PasswordResetToken.token == token)
            res = await session.execute(stmt)
            reset_token = res.scalar_one_or_none()
            if not reset_token:
                return None
            return {
                "id": str(reset_token.id),
                "user_id": str(reset_token.user_id),
                "token": reset_token.token,
                "expires_at": reset_token.expires_at,
                "created_at": reset_token.created_at,
                "used_at": reset_token.used_at,
            }

    async def mark_reset_token_used(self, token_id: str) -> None:
        async with self._session_factory() as session:
            stmt = (
                update(PasswordResetToken)
                .where(PasswordResetToken.id == UUID(token_id))
                .values(used_at=func.current_timestamp())
            )
            await session.execute(stmt)
            await session.commit()

    async def invalidate_password_reset_tokens(self, user_id: str) -> None:
        async with self._session_factory() as session:
            stmt = (
                update(PasswordResetToken)
                .where(PasswordResetToken.user_id == UUID(str(user_id)))
                .where(PasswordResetToken.used_at.is_(None))
                .values(used_at=datetime.now(UTC))
                .execution_options(synchronize_session="fetch")
            )
            await session.execute(stmt)
            await session.commit()

    async def update_user_password(self, user_id: str, password_hash: str) -> None:
        async with self._session_factory() as session:
            stmt = (
                update(User)
                .where(User.id == UUID(str(user_id)))
                .values(password_hash=password_hash)
            )
            await session.execute(stmt)
            await session.commit()


class PostgresSessionRepo(SessionRepo):
    def __init__(self, engine: AsyncEngine) -> None:
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def store_refresh(self, user_id: str, jti: str, exp_ts: int) -> None:
        async with self._session_factory() as session:
            session.add(RefreshSession(jti=jti, user_id=UUID(str(user_id)), exp_ts=exp_ts))
            await session.commit()

    async def revoke_refresh(self, jti: str) -> None:
        async with self._session_factory() as session:
            obj = await session.get(RefreshSession, jti)
            if obj is not None:
                await session.delete(obj)
            await session.commit()

    async def is_refresh_valid(self, jti: str) -> bool:
        async with self._session_factory() as session:
            obj = await session.get(RefreshSession, jti)
            return obj is not None and obj.exp_ts > int(datetime.now(UTC).timestamp())
