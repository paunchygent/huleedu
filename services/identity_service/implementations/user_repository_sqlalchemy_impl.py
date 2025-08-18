from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update

from services.identity_service.models_db import Base, RefreshSession, User
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


class PostgresSessionRepo(SessionRepo):
    def __init__(self, engine: AsyncEngine) -> None:
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def store_refresh(self, user_id: str, jti: str, exp_ts: int) -> None:
        async with self._session_factory() as session:
            session.add(
                RefreshSession(jti=jti, user_id=UUID(str(user_id)), exp_ts=exp_ts)
            )
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
