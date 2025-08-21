"""Session management domain handler for Identity Service.

Encapsulates session management business logic including:
- Listing active user sessions with device info
- Revoking specific sessions by JTI
- Revoking all sessions for a user (security action)
- Getting active session count for monitoring
- Comprehensive audit logging for session operations

This handler follows the established domain handler pattern from class_management_service.
"""

from __future__ import annotations

from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

from services.identity_service.protocols import (
    AuditLoggerProtocol,
    UserSessionRepositoryProtocol,
)

logger = create_service_logger("identity_service.domain_handlers.session_management")


class SessionInfo:
    """Model for session information responses."""

    def __init__(
        self,
        jti: str,
        device_name: str | None,
        device_type: str | None,
        ip_address: str | None,
        created_at: str,  # ISO formatted
        last_activity: str | None,  # ISO formatted
        expires_at: str,  # ISO formatted
        is_current: bool = False,
    ):
        self.jti = jti
        self.device_name = device_name
        self.device_type = device_type
        self.ip_address = ip_address
        self.created_at = created_at
        self.last_activity = last_activity
        self.expires_at = expires_at
        self.is_current = is_current

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "session_id": self.jti,
            "device_name": self.device_name,
            "device_type": self.device_type,
            "ip_address": self.ip_address,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "expires_at": self.expires_at,
            "is_current": self.is_current,
        }


class SessionListResult:
    """Result model for session list operations."""

    def __init__(self, sessions: list[SessionInfo]):
        self.sessions = sessions

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "sessions": [session.to_dict() for session in self.sessions],
            "total_count": len(self.sessions),
        }


class SessionActionResult:
    """Result model for session action operations."""

    def __init__(self, message: str, sessions_affected: int = 1):
        self.message = message
        self.sessions_affected = sessions_affected

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "message": self.message,
            "sessions_affected": self.sessions_affected,
        }


class ActiveSessionCountResult:
    """Result model for active session count operations."""

    def __init__(self, active_sessions: int):
        self.active_sessions = active_sessions

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "active_sessions": self.active_sessions,
        }


class SessionManagementHandler:
    """Encapsulates session management business logic for Identity Service.

    Handles session operations with:
    - Complete session listing with device information
    - Individual session revocation for security
    - Bulk session revocation (logout from all devices)
    - Active session monitoring and counting
    - Comprehensive audit logging for security events
    - Current session identification (optional)
    """

    def __init__(
        self,
        user_session_repo: UserSessionRepositoryProtocol,
        audit_logger: AuditLoggerProtocol,
    ):
        self._user_session_repo = user_session_repo
        self._audit_logger = audit_logger

    async def list_user_sessions(
        self,
        user_id: str,
        current_jti: str | None,  # JTI of current session (optional)
        correlation_id: UUID,
    ) -> SessionListResult:
        """List all active sessions for a user.

        Args:
            user_id: User ID from authenticated context
            current_jti: JTI of current session to mark as current (optional)
            correlation_id: Request correlation ID for observability

        Returns:
            SessionListResult with list of active sessions

        Raises:
            HuleEduError: If user validation fails
        """
        user_uuid = UUID(user_id)

        # Get all active sessions for the user
        session_data = await self._user_session_repo.get_user_sessions(user_uuid)

        # Convert to SessionInfo objects
        sessions = []
        for session in session_data:
            session_info = SessionInfo(
                jti=session["jti"],
                device_name=session.get("device_name"),
                device_type=session.get("device_type"),
                ip_address=session.get("ip_address"),
                created_at=session["created_at"].isoformat() if session.get("created_at") else "",
                last_activity=session["last_activity"].isoformat()
                if session.get("last_activity")
                else None,
                expires_at=session["expires_at"].isoformat() if session.get("expires_at") else "",
                is_current=session["jti"] == current_jti if current_jti else False,
            )
            sessions.append(session_info)

        # Sort by creation date (newest first)
        sessions.sort(key=lambda s: s.created_at, reverse=True)

        logger.info(
            "User sessions listed successfully",
            extra={
                "user_id": user_id,
                "session_count": len(sessions),
                "correlation_id": str(correlation_id),
            },
        )

        return SessionListResult(sessions)

    async def revoke_session(
        self,
        user_id: str,
        session_id: str,  # JTI
        correlation_id: UUID,
        ip_address: str | None = None,
    ) -> SessionActionResult:
        """Revoke a specific session.

        Args:
            user_id: User ID from authenticated context
            session_id: JTI of session to revoke
            correlation_id: Request correlation ID for observability
            ip_address: Client IP address for audit logging

        Returns:
            SessionActionResult with success message

        Raises:
            HuleEduError: If session not found or doesn't belong to user
        """
        # Get session details for validation and audit
        session = await self._user_session_repo.get_session(session_id)

        if not session:
            logger.warning(
                "Attempt to revoke non-existent session",
                extra={
                    "user_id": user_id,
                    "session_id": session_id,
                    "correlation_id": str(correlation_id),
                },
            )
            return SessionActionResult("Session not found or already revoked", 0)

        # Verify session belongs to the authenticated user
        if str(session.get("user_id")) != user_id:
            await self._audit_logger.log_action(
                action="session_revoke_unauthorized",
                user_id=UUID(user_id) if user_id else None,
                details={
                    "attempted_session_id": session_id,
                    "session_owner_id": str(session.get("user_id")),
                },
                ip_address=ip_address,
                user_agent=None,
                correlation_id=correlation_id,
            )

            logger.warning(
                "Unauthorized attempt to revoke session",
                extra={
                    "user_id": user_id,
                    "session_id": session_id,
                    "session_owner": session.get("user_id"),
                    "correlation_id": str(correlation_id),
                },
            )
            return SessionActionResult("Session not found or already revoked", 0)

        # Revoke the session
        revoked = await self._user_session_repo.revoke_session(session_id)

        if revoked:
            # Audit log successful session revocation
            await self._audit_logger.log_action(
                action="session_revoked",
                user_id=UUID(user_id) if user_id else None,
                details={
                    "revoked_session_id": session_id,
                    "device_name": session.get("device_name"),
                    "device_type": session.get("device_type"),
                },
                ip_address=ip_address,
                user_agent=None,
                correlation_id=correlation_id,
            )

            logger.info(
                "Session revoked successfully",
                extra={
                    "user_id": user_id,
                    "session_id": session_id,
                    "device_name": session.get("device_name"),
                    "correlation_id": str(correlation_id),
                },
            )

            return SessionActionResult("Session revoked successfully", 1)
        else:
            logger.warning(
                "Failed to revoke session",
                extra={
                    "user_id": user_id,
                    "session_id": session_id,
                    "correlation_id": str(correlation_id),
                },
            )
            return SessionActionResult("Session not found or already revoked", 0)

    async def revoke_all_sessions(
        self,
        user_id: str,
        correlation_id: UUID,
        exclude_current: bool = True,
        current_jti: str | None = None,
        ip_address: str | None = None,
    ) -> SessionActionResult:
        """Revoke all sessions for a user (logout from all devices).

        Args:
            user_id: User ID from authenticated context
            exclude_current: Whether to exclude current session from revocation
            current_jti: JTI of current session to exclude (if exclude_current=True)
            correlation_id: Request correlation ID for observability
            ip_address: Client IP address for audit logging

        Returns:
            SessionActionResult with count of revoked sessions

        Raises:
            HuleEduError: If user validation fails
        """
        user_uuid = UUID(user_id)

        # Get current sessions for audit logging before revocation
        sessions_before = await self._user_session_repo.get_user_sessions(user_uuid)

        if exclude_current and current_jti:
            # Filter out current session for counting and audit
            sessions_to_revoke = [s for s in sessions_before if s["jti"] != current_jti]

            # Revoke all except current
            revoked_count = 0
            for session in sessions_to_revoke:
                if await self._user_session_repo.revoke_session(session["jti"]):
                    revoked_count += 1
        else:
            # Revoke all sessions including current
            revoked_count = await self._user_session_repo.revoke_all_user_sessions(user_uuid)

        # Audit log bulk session revocation
        await self._audit_logger.log_action(
            action="all_sessions_revoked",
            user_id=UUID(user_id) if user_id else None,
            details={
                "sessions_revoked": revoked_count,
                "excluded_current": exclude_current,
                "current_session": current_jti if exclude_current else None,
            },
            ip_address=ip_address,
            user_agent=None,
            correlation_id=correlation_id,
        )

        logger.info(
            "All sessions revoked successfully",
            extra={
                "user_id": user_id,
                "sessions_revoked": revoked_count,
                "excluded_current": exclude_current,
                "correlation_id": str(correlation_id),
            },
        )

        message = f"Successfully revoked {revoked_count} session(s)"
        if exclude_current and current_jti:
            message += " (excluding current session)"

        return SessionActionResult(message, revoked_count)

    async def get_active_session_count(
        self,
        user_id: str,
        correlation_id: UUID,
    ) -> ActiveSessionCountResult:
        """Get count of active sessions for a user.

        Args:
            user_id: User ID from authenticated context
            correlation_id: Request correlation ID for observability

        Returns:
            ActiveSessionCountResult with session count

        Raises:
            HuleEduError: If user validation fails
        """
        user_uuid = UUID(user_id)

        # Get all active sessions for counting
        sessions = await self._user_session_repo.get_user_sessions(user_uuid)
        active_count = len(sessions)

        logger.debug(
            "Active session count retrieved",
            extra={
                "user_id": user_id,
                "active_sessions": active_count,
                "correlation_id": str(correlation_id),
            },
        )

        return ActiveSessionCountResult(active_count)
