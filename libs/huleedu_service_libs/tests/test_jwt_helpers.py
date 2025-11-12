"""Unit tests for JWT test helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from pydantic import SecretStr

from huleedu_service_libs.auth.jwt_settings import JWTValidationSettings
from huleedu_service_libs.testing.jwt_helpers import build_jwt_headers, create_jwt


class MockJWTSettings(JWTValidationSettings):
    """Mock settings for testing JWT helpers."""

    JWT_SECRET_KEY: SecretStr | None = SecretStr("test-secret-key-12345")
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "huleedu-test-service"
    JWT_AUDIENCE: str = "huleedu-test-platform"


class TestBuildJwtHeaders:
    """Tests for build_jwt_headers function."""

    def test_build_jwt_headers_returns_authorization_and_correlation_headers(self):
        """Test that build_jwt_headers returns both Authorization and X-Correlation-ID headers."""
        settings = MockJWTSettings()

        headers = build_jwt_headers(settings)

        assert "Authorization" in headers
        assert "X-Correlation-ID" in headers
        assert headers["Authorization"].startswith("Bearer ")

    def test_build_jwt_headers_with_default_subject(self):
        """Test JWT creation with default subject claim."""
        settings = MockJWTSettings()

        headers = build_jwt_headers(settings)
        token = headers["Authorization"].replace("Bearer ", "")

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),  # type: ignore
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
        )

        assert payload["sub"] == "test-user"
        assert payload["iss"] == settings.JWT_ISSUER
        assert payload["aud"] == settings.JWT_AUDIENCE

    def test_build_jwt_headers_with_custom_subject(self):
        """Test JWT creation with custom subject claim."""
        settings = MockJWTSettings()

        headers = build_jwt_headers(settings, subject="user-123")
        token = headers["Authorization"].replace("Bearer ", "")

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),  # type: ignore
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
        )

        assert payload["sub"] == "user-123"

    def test_build_jwt_headers_with_roles(self):
        """Test JWT creation with roles claim."""
        settings = MockJWTSettings()

        headers = build_jwt_headers(settings, roles=["admin", "teacher"])
        token = headers["Authorization"].replace("Bearer ", "")

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),  # type: ignore
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
        )

        assert payload["roles"] == ["admin", "teacher"]

    def test_build_jwt_headers_with_org_id(self):
        """Test JWT creation with org_id claim."""
        settings = MockJWTSettings()

        headers = build_jwt_headers(settings, org_id="org-456")
        token = headers["Authorization"].replace("Bearer ", "")

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),  # type: ignore
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
        )

        assert payload["org_id"] == "org-456"

    def test_build_jwt_headers_with_custom_correlation_id(self):
        """Test JWT headers with custom correlation ID."""
        settings = MockJWTSettings()
        custom_correlation_id = "test-correlation-123"

        headers = build_jwt_headers(settings, correlation_id=custom_correlation_id)

        assert headers["X-Correlation-ID"] == custom_correlation_id

    def test_build_jwt_headers_auto_generates_correlation_id(self):
        """Test that correlation ID is auto-generated if not provided."""
        settings = MockJWTSettings()

        headers1 = build_jwt_headers(settings)
        headers2 = build_jwt_headers(settings)

        # Auto-generated correlation IDs should be different
        assert headers1["X-Correlation-ID"] != headers2["X-Correlation-ID"]

    def test_build_jwt_headers_with_positive_expires_in(self):
        """Test JWT creation with future expiration."""
        settings = MockJWTSettings()

        headers = build_jwt_headers(settings, expires_in=timedelta(hours=2))
        token = headers["Authorization"].replace("Bearer ", "")

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),  # type: ignore
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
        )

        # Token should expire approximately 2 hours from now
        exp_time = datetime.fromtimestamp(payload["exp"], tz=UTC)
        expected_exp = datetime.now(UTC) + timedelta(hours=2)
        time_diff = abs((exp_time - expected_exp).total_seconds())

        assert time_diff < 5  # Allow 5 second tolerance

    def test_build_jwt_headers_with_negative_expires_in_creates_expired_token(self):
        """Test JWT creation with past expiration (for expired token testing)."""
        settings = MockJWTSettings()

        headers = build_jwt_headers(settings, expires_in=timedelta(hours=-1))
        token = headers["Authorization"].replace("Bearer ", "")

        # Token should be expired, so decoding with verify should fail
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(
                token,
                settings.JWT_SECRET_KEY.get_secret_value(),  # type: ignore
                algorithms=[settings.JWT_ALGORITHM],
                audience=settings.JWT_AUDIENCE,
            )

    def test_build_jwt_headers_with_omit_claims_removes_exp(self):
        """Test JWT creation with exp claim omitted."""
        settings = MockJWTSettings()

        headers = build_jwt_headers(settings, omit_claims=["exp"])
        token = headers["Authorization"].replace("Bearer ", "")

        # Decode without verification to inspect payload
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),  # type: ignore
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            options={"verify_exp": False},
        )

        assert "exp" not in payload
        assert "sub" in payload  # Other claims should remain

    def test_build_jwt_headers_with_omit_claims_removes_sub(self):
        """Test JWT creation with sub claim omitted."""
        settings = MockJWTSettings()

        headers = build_jwt_headers(settings, omit_claims=["sub"])
        token = headers["Authorization"].replace("Bearer ", "")

        # Decode without verification
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),  # type: ignore
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            options={"verify_signature": False},
        )

        assert "sub" not in payload
        assert "exp" in payload  # Other claims should remain

    def test_build_jwt_headers_with_omit_claims_removes_multiple_claims(self):
        """Test JWT creation with multiple claims omitted."""
        settings = MockJWTSettings()

        headers = build_jwt_headers(settings, omit_claims=["exp", "sub", "iat"])
        token = headers["Authorization"].replace("Bearer ", "")

        # Decode without verification
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),  # type: ignore
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            options={"verify_signature": False},
        )

        assert "exp" not in payload
        assert "sub" not in payload
        assert "iat" not in payload
        assert "iss" in payload  # Should keep non-omitted claims

    def test_build_jwt_headers_with_extra_claims(self):
        """Test JWT creation with extra custom claims."""
        settings = MockJWTSettings()

        headers = build_jwt_headers(
            settings,
            extra_claims={
                "organization_id": "org-789",
                "custom_field": "custom_value",
                "email": "test@example.com",
            },
        )
        token = headers["Authorization"].replace("Bearer ", "")

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),  # type: ignore
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
        )

        assert payload["organization_id"] == "org-789"
        assert payload["custom_field"] == "custom_value"
        assert payload["email"] == "test@example.com"

    def test_build_jwt_headers_extra_claims_override_defaults(self):
        """Test that extra_claims can override default claims."""
        settings = MockJWTSettings()

        headers = build_jwt_headers(
            settings,
            subject="original-user",
            extra_claims={"sub": "overridden-user"},
        )
        token = headers["Authorization"].replace("Bearer ", "")

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),  # type: ignore
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
        )

        # extra_claims should override the subject parameter
        assert payload["sub"] == "overridden-user"

    def test_build_jwt_headers_with_all_parameters(self):
        """Test JWT creation with all parameters combined."""
        settings = MockJWTSettings()

        headers = build_jwt_headers(
            settings,
            subject="admin-user",
            roles=["admin", "superuser"],
            org_id="org-999",
            correlation_id="custom-correlation",
            expires_in=timedelta(hours=3),
            extra_claims={"email": "admin@example.com"},
        )

        token = headers["Authorization"].replace("Bearer ", "")
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),  # type: ignore
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
        )

        assert payload["sub"] == "admin-user"
        assert payload["roles"] == ["admin", "superuser"]
        assert payload["org_id"] == "org-999"
        assert payload["email"] == "admin@example.com"
        assert headers["X-Correlation-ID"] == "custom-correlation"

    def test_build_jwt_headers_raises_error_when_secret_not_configured(self):
        """Test that build_jwt_headers raises error when JWT_SECRET_KEY is None."""

        class SettingsWithoutSecret(JWTValidationSettings):
            JWT_SECRET_KEY: SecretStr | None = None
            JWT_ALGORITHM: str = "HS256"

        settings = SettingsWithoutSecret()

        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be configured"):
            build_jwt_headers(settings)


class TestCreateJwt:
    """Tests for create_jwt function."""

    def test_create_jwt_with_minimal_payload(self):
        """Test JWT creation with minimal payload."""
        secret = "test-secret"
        payload: dict[str, Any] = {"sub": "user-123"}

        token = create_jwt(secret, payload)

        decoded = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_signature": False})
        assert decoded["sub"] == "user-123"

    def test_create_jwt_with_custom_algorithm(self):
        """Test JWT creation with custom algorithm."""
        secret = "test-secret"
        payload: dict[str, Any] = {"sub": "user-123", "data": "test"}

        token = create_jwt(secret, payload, algorithm="HS512")

        # Should decode successfully with HS512
        decoded = jwt.decode(token, secret, algorithms=["HS512"])
        assert decoded["sub"] == "user-123"

    def test_create_jwt_with_complex_payload(self):
        """Test JWT creation with complex nested payload."""
        secret = "test-secret"
        payload: dict[str, Any] = {
            "sub": "user-123",
            "nested": {"key": "value", "list": [1, 2, 3]},
            "array": ["a", "b", "c"],
        }

        token = create_jwt(secret, payload)

        decoded = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_signature": False})
        assert decoded["nested"]["key"] == "value"
        assert decoded["array"] == ["a", "b", "c"]

    def test_create_jwt_is_verifiable(self):
        """Test that created JWT can be verified with the same secret."""
        secret = "test-secret"
        payload: dict[str, Any] = {
            "sub": "user-123",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        }

        token = create_jwt(secret, payload)

        # Should verify successfully
        decoded = jwt.decode(token, secret, algorithms=["HS256"])
        assert decoded["sub"] == "user-123"

    def test_create_jwt_fails_verification_with_wrong_secret(self):
        """Test that JWT verification fails with incorrect secret."""
        secret = "correct-secret"
        wrong_secret = "wrong-secret"
        payload: dict[str, Any] = {"sub": "user-123"}

        token = create_jwt(secret, payload)

        # Should fail verification with wrong secret
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, wrong_secret, algorithms=["HS256"])
