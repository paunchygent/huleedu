"""Audit logger implementation for security events."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.identity_service.models_db import AuditLog
from services.identity_service.protocols import AuditLoggerProtocol

logger = create_service_logger("identity_service.audit")


class AuditLoggerImpl(AuditLoggerProtocol):
    """Database-backed audit logger implementation."""
    
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        """
        Initialize audit logger with database session factory.
        
        Args:
            session_factory: Factory for creating database sessions
        """
        self.session_factory = session_factory
    
    async def log_action(
        self,
        action: str,
        user_id: UUID | None,
        details: dict[str, Any] | None,
        ip_address: str | None,
        user_agent: str | None,
        correlation_id: UUID
    ) -> None:
        """
        Log an audit event to the database.
        
        Args:
            action: The action being performed
            user_id: User ID if authenticated
            details: Additional details about the action
            ip_address: Client IP address
            user_agent: Client user agent string
            correlation_id: Request correlation ID
        """
        try:
            async with self.session_factory() as session:
                audit_log = AuditLog(
                    action=action,
                    user_id=user_id,
                    details=details,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    correlation_id=correlation_id
                )
                
                session.add(audit_log)
                await session.commit()
                
                logger.info(
                    f"Audit log created: {action}",
                    extra={
                        "action": action,
                        "user_id": str(user_id) if user_id else None,
                        "correlation_id": str(correlation_id),
                        "ip_address": ip_address,
                    }
                )
                
        except Exception as e:
            # Log the error but don't fail the operation
            logger.error(
                f"Failed to create audit log: {e}",
                extra={
                    "action": action,
                    "user_id": str(user_id) if user_id else None,
                    "correlation_id": str(correlation_id),
                    "error": str(e),
                }
            )
    
    async def log_login_attempt(
        self,
        email: str,
        success: bool,
        user_id: UUID | None,
        ip_address: str | None,
        user_agent: str | None,
        correlation_id: UUID,
        failure_reason: str | None = None
    ) -> None:
        """
        Log a login attempt.
        
        Args:
            email: Email address used for login
            success: Whether the login was successful
            user_id: User ID if login was successful
            ip_address: Client IP address
            user_agent: Client user agent string
            correlation_id: Request correlation ID
            failure_reason: Reason for failure if applicable
        """
        action = "login_success" if success else "login_failure"
        
        details = {
            "email": email,
            "success": success,
        }
        
        if failure_reason:
            details["failure_reason"] = failure_reason
        
        await self.log_action(
            action=action,
            user_id=user_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id
        )
    
    async def log_password_change(
        self,
        user_id: UUID,
        ip_address: str | None,
        user_agent: str | None,
        correlation_id: UUID
    ) -> None:
        """
        Log a password change event.
        
        Args:
            user_id: User who changed their password
            ip_address: Client IP address
            user_agent: Client user agent string
            correlation_id: Request correlation ID
        """
        await self.log_action(
            action="password_change",
            user_id=user_id,
            details={"event": "Password successfully changed"},
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id
        )
    
    async def log_token_operation(
        self,
        operation: str,
        user_id: UUID,
        jti: str | None,
        ip_address: str | None,
        user_agent: str | None,
        correlation_id: UUID
    ) -> None:
        """
        Log token operations (refresh, revoke, etc.).
        
        Args:
            operation: Type of token operation
            user_id: User performing the operation
            jti: JWT ID if applicable
            ip_address: Client IP address
            user_agent: Client user agent string
            correlation_id: Request correlation ID
        """
        details: dict[str, Any] = {
            "operation": operation,
        }
        
        if jti:
            # Only store first 8 chars of JTI for security
            details["jti_prefix"] = jti[:8] if len(jti) > 8 else jti
        
        await self.log_action(
            action=f"token_{operation}",
            user_id=user_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id
        )