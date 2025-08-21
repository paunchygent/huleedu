"""User session repository implementation with device tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.identity_service.models_db import UserSession
from services.identity_service.protocols import UserSessionRepositoryProtocol

logger = create_service_logger("identity_service.session_repo")


class UserSessionRepositoryImpl(UserSessionRepositoryProtocol):
    """Database-backed user session repository with device tracking."""
    
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        """
        Initialize session repository with database session factory.
        
        Args:
            session_factory: Factory for creating database sessions
        """
        self.session_factory = session_factory
    
    async def create_session(
        self,
        user_id: UUID,
        jti: str,
        expires_at: datetime,
        device_name: str | None,
        device_type: str | None,
        ip_address: str | None,
        user_agent: str | None
    ) -> None:
        """
        Create a new user session.
        
        Args:
            user_id: User ID
            jti: JWT ID
            expires_at: Session expiration time
            device_name: Name of the device
            device_type: Type of device (mobile, desktop, etc.)
            ip_address: Client IP address
            user_agent: Client user agent string
        """
        try:
            async with self.session_factory() as session:
                user_session = UserSession(
                    user_id=user_id,
                    jti=jti,
                    expires_at=expires_at,
                    device_name=device_name,
                    device_type=device_type,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                
                session.add(user_session)
                await session.commit()
                
                logger.info(
                    "Session created",
                    extra={
                        "user_id": str(user_id),
                        "jti_prefix": jti[:8] if len(jti) > 8 else jti,
                        "device_type": device_type,
                    }
                )
                
        except Exception as e:
            logger.error(
                f"Failed to create session: {e}",
                extra={
                    "user_id": str(user_id),
                    "error": str(e),
                }
            )
            raise
    
    async def get_user_sessions(self, user_id: UUID) -> list[dict[str, Any]]:
        """
        Get all active sessions for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of session dictionaries
        """
        try:
            async with self.session_factory() as session:
                # Query for active sessions (not revoked and not expired)
                now = datetime.now(timezone.utc)
                
                stmt = select(UserSession).where(
                    and_(
                        UserSession.user_id == user_id,
                        UserSession.revoked_at.is_(None),
                        UserSession.expires_at > now
                    )
                ).order_by(UserSession.created_at.desc())
                
                result = await session.execute(stmt)
                sessions = result.scalars().all()
                
                return [
                    {
                        "id": str(s.id),
                        "jti": s.jti,
                        "device_name": s.device_name,
                        "device_type": s.device_type,
                        "ip_address": s.ip_address,
                        "user_agent": s.user_agent,
                        "last_activity": s.last_activity.isoformat() if s.last_activity else None,
                        "created_at": s.created_at.isoformat() if s.created_at else None,
                        "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                    }
                    for s in sessions
                ]
                
        except Exception as e:
            logger.error(
                f"Failed to get user sessions: {e}",
                extra={
                    "user_id": str(user_id),
                    "error": str(e),
                }
            )
            return []
    
    async def revoke_session(self, jti: str) -> bool:
        """
        Revoke a specific session.
        
        Args:
            jti: JWT ID of the session to revoke
            
        Returns:
            True if session was revoked, False if not found
        """
        try:
            async with self.session_factory() as session:
                now = datetime.now(timezone.utc)
                
                stmt = update(UserSession).where(
                    and_(
                        UserSession.jti == jti,
                        UserSession.revoked_at.is_(None)
                    )
                ).values(revoked_at=now)
                
                result = await session.execute(stmt)
                await session.commit()
                
                if result.rowcount > 0:
                    logger.info(
                        "Session revoked",
                        extra={
                            "jti_prefix": jti[:8] if len(jti) > 8 else jti,
                        }
                    )
                    return True
                
                return False
                
        except Exception as e:
            logger.error(
                f"Failed to revoke session: {e}",
                extra={
                    "jti_prefix": jti[:8] if len(jti) > 8 else jti,
                    "error": str(e),
                }
            )
            return False
    
    async def revoke_all_user_sessions(self, user_id: UUID) -> int:
        """
        Revoke all sessions for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Number of sessions revoked
        """
        try:
            async with self.session_factory() as session:
                now = datetime.now(timezone.utc)
                
                stmt = update(UserSession).where(
                    and_(
                        UserSession.user_id == user_id,
                        UserSession.revoked_at.is_(None)
                    )
                ).values(revoked_at=now)
                
                result = await session.execute(stmt)
                await session.commit()
                
                count = result.rowcount
                
                if count > 0:
                    logger.info(
                        f"Revoked {count} sessions for user",
                        extra={
                            "user_id": str(user_id),
                            "count": count,
                        }
                    )
                
                return count
                
        except Exception as e:
            logger.error(
                f"Failed to revoke all user sessions: {e}",
                extra={
                    "user_id": str(user_id),
                    "error": str(e),
                }
            )
            return 0
    
    async def update_last_activity(self, jti: str) -> bool:
        """
        Update the last activity timestamp for a session.
        
        Args:
            jti: JWT ID of the session
            
        Returns:
            True if session was updated, False if not found
        """
        try:
            async with self.session_factory() as session:
                now = datetime.now(timezone.utc)
                
                stmt = update(UserSession).where(
                    and_(
                        UserSession.jti == jti,
                        UserSession.revoked_at.is_(None),
                        UserSession.expires_at > now
                    )
                ).values(last_activity=now)
                
                result = await session.execute(stmt)
                await session.commit()
                
                return result.rowcount > 0
                
        except Exception as e:
            logger.error(
                f"Failed to update session activity: {e}",
                extra={
                    "jti_prefix": jti[:8] if len(jti) > 8 else jti,
                    "error": str(e),
                }
            )
            return False
    
    async def get_session(self, jti: str) -> dict[str, Any] | None:
        """
        Get session details by JTI.
        
        Args:
            jti: JWT ID
            
        Returns:
            Session dictionary or None if not found
        """
        try:
            async with self.session_factory() as session:
                stmt = select(UserSession).where(UserSession.jti == jti)
                
                result = await session.execute(stmt)
                user_session = result.scalar_one_or_none()
                
                if user_session:
                    return {
                        "id": str(user_session.id),
                        "user_id": str(user_session.user_id),
                        "jti": user_session.jti,
                        "device_name": user_session.device_name,
                        "device_type": user_session.device_type,
                        "ip_address": user_session.ip_address,
                        "user_agent": user_session.user_agent,
                        "last_activity": user_session.last_activity.isoformat() if user_session.last_activity else None,
                        "created_at": user_session.created_at.isoformat() if user_session.created_at else None,
                        "expires_at": user_session.expires_at.isoformat() if user_session.expires_at else None,
                        "revoked_at": user_session.revoked_at.isoformat() if user_session.revoked_at else None,
                    }
                
                return None
                
        except Exception as e:
            logger.error(
                f"Failed to get session: {e}",
                extra={
                    "jti_prefix": jti[:8] if len(jti) > 8 else jti,
                    "error": str(e),
                }
            )
            return None
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Remove expired sessions from the database.
        
        Returns:
            Number of sessions cleaned up
        """
        try:
            async with self.session_factory() as session:
                now = datetime.now(timezone.utc)
                
                # Delete sessions that are either expired or revoked more than 30 days ago
                stmt = select(UserSession).where(
                    UserSession.expires_at < now
                )
                
                result = await session.execute(stmt)
                expired_sessions = result.scalars().all()
                
                for expired_session in expired_sessions:
                    await session.delete(expired_session)
                
                await session.commit()
                
                count = len(expired_sessions)
                
                if count > 0:
                    logger.info(
                        f"Cleaned up {count} expired sessions",
                        extra={"count": count}
                    )
                
                return count
                
        except Exception as e:
            logger.error(
                f"Failed to cleanup expired sessions: {e}",
                extra={"error": str(e)}
            )
            return 0