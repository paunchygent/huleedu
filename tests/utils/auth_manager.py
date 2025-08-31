"""
Test Authentication Manager

Industry-standard test authentication utilities for functional tests.
Provides JWT token generation and user management without requiring
external authentication services during testing.

Based on testing best practices:
- Self-contained test authentication
- Configurable user contexts
- JWT standard compliance
- Easy migration to real auth services
"""

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, cast

import jwt
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("test.auth_manager")


class AuthTestUser:
    """Test user representation for functional tests."""

    def __init__(
        self,
        user_id: str,
        email: str,
        name: str,
        role: str = "teacher",
        organization_id: Optional[str] = None,
    ):
        self.user_id = user_id
        self.email = email
        self.name = name
        self.role = role
        self.organization_id = organization_id or f"test_org_{user_id}"
        self.created_at = datetime.now(timezone.utc)

    def to_jwt_payload(self) -> Dict[str, Any]:
        """Convert user to JWT payload format."""
        payload: Dict[str, Any] = {
            "sub": self.user_id,  # Standard JWT subject claim
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "iat": int(time.time()),  # Issued at
            "exp": int(
                (datetime.now(timezone.utc) + timedelta(hours=24)).timestamp()
            ),  # Expires in 24h
            "iss": "huledu-test-auth",  # Issuer
            "aud": "huledu-services",  # Audience
        }
        # Include org_id claim only when non-empty/non-null to allow individual users
        if self.organization_id:
            payload["org_id"] = self.organization_id
        return payload


class AuthTestManager:
    """
    Test authentication manager for functional tests.

    Provides JWT token generation and user management without requiring
    external authentication services. Designed for easy migration to
    real authentication when available.
    """

    def __init__(self, jwt_secret: str = "test-secret-key"):
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = "HS256"
        self._test_users: Dict[str, AuthTestUser] = {}
        self._default_user: Optional[AuthTestUser] = None

        # Create a default test user
        self._create_default_test_user()

        # Test correlation ID for tracking
        self._test_correlation_id = str(uuid.uuid4())

    def _create_default_test_user(self) -> None:
        """Create a default test user for convenience."""
        default_user = AuthTestUser(
            user_id="test_user_123",
            email="test.teacher@huledu.test",
            name="Test Teacher",
            role="teacher",
        )
        self._test_users[default_user.user_id] = default_user
        self._default_user = default_user
        logger.info(f"Created default test user: {default_user.user_id}")

    def create_test_user(
        self,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        name: Optional[str] = None,
        role: str = "teacher",
        organization_id: Optional[str] = None,
    ) -> AuthTestUser:
        """
        Create a new test user.

        Args:
            user_id: Unique user identifier (auto-generated if None)
            email: User email (auto-generated if None)
            name: User display name (auto-generated if None)
            role: User role (default: teacher)
            organization_id: Organization identifier (auto-generated if None)

        Returns:
            AuthTestUser: Created test user
        """
        if user_id is None:
            user_id = f"test_user_{uuid.uuid4().hex[:8]}"

        if email is None:
            email = f"{user_id}@huledu.test"

        if name is None:
            name = f"Test User {user_id[-8:]}"

        user = AuthTestUser(
            user_id=user_id,
            email=email,
            name=name,
            role=role,
            organization_id=organization_id,
        )

        self._test_users[user_id] = user
        logger.info(f"Created test user: {user_id} ({email})")
        return user

    def get_test_user(self, user_id: str) -> Optional[AuthTestUser]:
        """Get a test user by ID."""
        return self._test_users.get(user_id)

    def get_default_user(self) -> AuthTestUser:
        """Get the default test user."""
        if self._default_user is None:
            raise RuntimeError("No default test user available")
        return self._default_user

    def generate_jwt_token(self, user: Optional[AuthTestUser] = None) -> str:
        """
        Generate a JWT token for a test user.

        Args:
            user: Test user (uses default if None)

        Returns:
            str: JWT token
        """
        if user is None:
            user = self.get_default_user()

        payload = user.to_jwt_payload()
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

        logger.debug(f"Generated JWT token for user {user.user_id}")
        return token

    def get_auth_headers(self, user: Optional[AuthTestUser] = None) -> Dict[str, str]:
        """
        Get authentication headers for HTTP requests.

        Args:
            user: Test user (uses default if None)

        Returns:
            Dict[str, str]: Headers including X-User-ID and Authorization
        """
        if user is None:
            user = self.get_default_user()

        token = self.generate_jwt_token(user)

        return {
            "X-User-ID": user.user_id,
            "Authorization": f"Bearer {token}",
            "X-Test-Auth": "true",  # Marker for test authentication
        }

    # New helpers for org-identity variations
    def create_org_user(self, org_id: str, **kwargs) -> AuthTestUser:
        """Create a test user associated with a specific organization."""
        return self.create_test_user(organization_id=org_id, **kwargs)

    def create_individual_user(self, **kwargs) -> AuthTestUser:
        """Create a test user without any organization identity (individual flow)."""
        # Pass empty string so to_jwt_payload omits org_id claim
        return self.create_test_user(organization_id="", **kwargs)

    def generate_jwt_with_org_claim(
        self, user: Optional[AuthTestUser] = None, org_claim_name: str = "org_id"
    ) -> str:
        """
        Generate a JWT token using a specific claim name for organization identity.

        Args:
            user: Test user (uses default if None)
            org_claim_name: Which claim to use for organization identity
                             (e.g., 'org_id', 'org', 'organization_id').

        Returns:
            str: Encoded JWT token
        """
        if user is None:
            user = self.get_default_user()

        # Base payload without org_id
        payload = user.to_jwt_payload()
        org_value = None
        # If user has an organization (via instance), prefer that
        if user.organization_id:
            org_value = user.organization_id
        # If org_id exists in payload (from to_jwt_payload), move it to requested claim
        if "org_id" in payload:
            org_value = payload.pop("org_id")
        if org_value:
            payload[org_claim_name] = org_value

        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        logger.debug(
            f"Generated JWT token for user {user.user_id} with org claim '{org_claim_name}'"
        )
        return token

    def validate_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate a JWT token (for testing token validation logic).

        Args:
            token: JWT token to validate

        Returns:
            Optional[Dict[str, Any]]: Decoded payload if valid, None if invalid
        """
        try:
            payload = cast(
                Dict[str, Any], jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            )
            return payload
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            return None

    def get_correlation_id(self) -> str:
        """
        Get the test correlation ID for tracking events.

        Returns:
            str: Test correlation ID
        """
        return self._test_correlation_id

    def create_teacher_user(self, _class_designation: str = "Test Class") -> AuthTestUser:
        """Create a test teacher user with class context."""
        user_id = f"teacher_{uuid.uuid4().hex[:8]}"
        return self.create_test_user(
            user_id=user_id,
            email=f"{user_id}@school.test",
            name=f"Teacher {user_id[-8:].title()}",
            role="teacher",
        )

    def create_admin_user(self) -> AuthTestUser:
        """Create a test admin user."""
        user_id = f"admin_{uuid.uuid4().hex[:8]}"
        return self.create_test_user(
            user_id=user_id,
            email=f"{user_id}@huledu.admin",
            name=f"Admin {user_id[-8:].title()}",
            role="admin",
        )

    def create_student_user(self) -> AuthTestUser:
        """Create a test student user (for future student-facing features)."""
        user_id = f"student_{uuid.uuid4().hex[:8]}"
        return self.create_test_user(
            user_id=user_id,
            email=f"{user_id}@student.test",
            name=f"Student {user_id[-8:].title()}",
            role="student",
        )

    def cleanup_test_users(self) -> None:
        """Clean up all test users except default."""
        default_user_id = self._default_user.user_id if self._default_user else None

        # Keep only the default user
        self._test_users = {
            uid: user for uid, user in self._test_users.items() if uid == default_user_id
        }

        logger.info("Cleaned up test users (kept default user)")


# Global instance for convenience
test_auth_manager = AuthTestManager()


# Convenience functions
def get_default_auth_headers() -> Dict[str, str]:
    """Get authentication headers for the default test user."""
    return test_auth_manager.get_auth_headers()


def get_auth_headers_for_user(user_id: str) -> Dict[str, str]:
    """Get authentication headers for a specific test user."""
    user = test_auth_manager.get_test_user(user_id)
    if user is None:
        raise ValueError(f"Test user {user_id} not found")
    return test_auth_manager.get_auth_headers(user)


def create_test_teacher() -> AuthTestUser:
    """Create a new test teacher user."""
    return test_auth_manager.create_teacher_user()


def create_test_admin() -> AuthTestUser:
    """Create a new test admin user."""
    return test_auth_manager.create_admin_user()
