"""Contract tests for Identity Service API response schemas.

These tests ensure that the API response schemas remain backward compatible
and conform to the expected contracts that API consumers depend on.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from common_core.error_enums import ErrorCode, IdentityErrorCode
from common_core.models.error_models import ErrorDetail
from huleedu_service_libs.error_handling import HuleEduError
from pydantic import ValidationError

from services.identity_service.api.schemas import (
    LoginRequest,
    MeResponse,
    ProfileResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    RegisterResponse,
    TokenPair,
)


class TestTokenPairContract:
    """Test TokenPair schema contract."""

    def test_valid_token_pair_schema(self) -> None:
        """Test that a valid TokenPair passes validation."""
        valid_data = {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test",
            "refresh_token": "refresh_token_string",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        token_pair = TokenPair(**valid_data)

        assert token_pair.access_token == valid_data["access_token"]
        assert token_pair.refresh_token == valid_data["refresh_token"]
        assert token_pair.token_type == "Bearer"
        assert token_pair.expires_in == 3600

    def test_token_type_defaults_to_bearer(self) -> None:
        """Test that token_type defaults to Bearer if not provided."""
        data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
        }

        token_pair = TokenPair(**data)
        assert token_pair.token_type == "Bearer"

    def test_missing_required_fields_fails(self) -> None:
        """Test that missing required fields cause validation failure."""
        invalid_data = {
            "access_token": "test_token",
            # Missing refresh_token
            "expires_in": 3600,
        }

        with pytest.raises(ValidationError) as exc_info:
            TokenPair(**invalid_data)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("refresh_token",) for error in errors)


class TestMeResponseContract:
    """Test MeResponse schema contract."""

    def test_valid_me_response(self) -> None:
        """Test that a valid MeResponse passes validation."""
        valid_data = {
            "user_id": str(uuid4()),
            "email": "test@example.com",
            "org_id": "org_123",
            "roles": ["user", "admin"],
            "email_verified": True,
        }

        response = MeResponse(**valid_data)

        assert response.user_id == valid_data["user_id"]
        assert response.email == valid_data["email"]
        assert response.org_id == valid_data["org_id"]
        assert response.roles == ["user", "admin"]
        assert response.email_verified is True

    def test_me_response_with_defaults(self) -> None:
        """Test that MeResponse uses correct defaults."""
        minimal_data = {
            "user_id": str(uuid4()),
            "email": "test@example.com",
        }

        response = MeResponse(**minimal_data)

        assert response.org_id is None
        assert response.roles == []
        assert response.email_verified is False


class TestRegisterResponseContract:
    """Test RegisterResponse schema contract."""

    def test_valid_register_response(self) -> None:
        """Test that a valid RegisterResponse passes validation."""
        valid_data = {
            "user_id": str(uuid4()),
            "org_id": "org_123",
            "email": "test@example.com",
            "email_verification_required": True,
        }

        response = RegisterResponse(**valid_data)

        assert response.user_id == valid_data["user_id"]
        assert response.email == valid_data["email"]
        assert response.email_verification_required is True

    def test_invalid_email_format_fails(self) -> None:
        """Test that invalid email format causes validation failure."""
        invalid_data = {
            "user_id": str(uuid4()),
            "org_id": "org_123",
            "email": "not-an-email",
            "email_verification_required": True,
        }

        with pytest.raises(ValidationError) as exc_info:
            RegisterResponse(**invalid_data)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("email",) for error in errors)


class TestProfileResponseContract:
    """Test ProfileResponse schema contract."""

    def test_valid_profile_response_with_person_name(self) -> None:
        """Test that ProfileResponse with PersonNameSchema passes validation."""
        valid_data = {
            "person_name": {
                "first_name": "John",
                "last_name": "Doe",
                "legal_full_name": "John Michael Doe",
            },
            "display_name": "Johnny",
            "locale": "en-US",
        }

        response = ProfileResponse(**valid_data)

        assert response.person_name
        assert response.person_name.first_name == "John"
        assert response.person_name.last_name == "Doe"
        assert response.person_name.legal_full_name == "John Michael Doe"
        assert response.display_name == "Johnny"
        assert response.locale == "en-US"

    def test_optional_fields_can_be_null(self) -> None:
        """Test that optional fields can be null."""
        valid_data = {
            "person_name": {
                "first_name": "Jane",
                "last_name": "Smith",
                "legal_full_name": "Jane Smith",
            },
        }

        response = ProfileResponse(**valid_data)
        assert response.display_name is None
        assert response.locale is None

    def test_swedish_characters_in_name(self) -> None:
        """Test that Swedish characters are properly handled in names."""
        valid_data = {
            "person_name": {
                "first_name": "Åsa",
                "last_name": "Öström",
                "legal_full_name": "Åsa Öström",
            },
            "display_name": "Åsa",
        }

        response = ProfileResponse(**valid_data)
        assert response.person_name.first_name == "Åsa"
        assert response.person_name.last_name == "Öström"


class TestRefreshTokenResponseContract:
    """Test RefreshTokenResponse schema contract."""

    def test_valid_refresh_response(self) -> None:
        """Test that a valid RefreshTokenResponse passes validation."""
        valid_data = {
            "access_token": "new_access_token",
            "token_type": "Bearer",
            "expires_in": 900,
        }

        response = RefreshTokenResponse(**valid_data)

        assert response.access_token == "new_access_token"
        assert response.token_type == "Bearer"
        assert response.expires_in == 900


class TestRequestSchemaContracts:
    """Test request schema contracts."""

    def test_login_request_schema(self) -> None:
        """Test LoginRequest schema validation."""
        valid_data = {
            "email": "test@example.com",
            "password": "SecurePassword123!",
        }

        request = LoginRequest(**valid_data)

        assert request.email == valid_data["email"]
        assert request.password == valid_data["password"]

    def test_register_request_schema(self) -> None:
        """Test RegisterRequest schema validation."""
        valid_data = {
            "email": "test@example.com",
            "password": "SecurePassword123!",
            "person_name": {
                "first_name": "Test",
                "last_name": "User",
                "legal_full_name": "Test User",
            },
            "organization_name": "Test Organization",
            "org_id": "org_123",
        }

        request = RegisterRequest(**valid_data)

        assert request.email == valid_data["email"]
        assert request.password == valid_data["password"]
        assert request.person_name.first_name == "Test"
        assert request.person_name.last_name == "User"
        assert request.person_name.legal_full_name == "Test User"
        assert request.organization_name == "Test Organization"
        assert request.org_id == valid_data["org_id"]

    def test_refresh_token_request_schema(self) -> None:
        """Test RefreshTokenRequest schema validation."""
        valid_data = {"refresh_token": "valid_refresh_token_string"}

        request = RefreshTokenRequest(**valid_data)

        assert request.refresh_token == valid_data["refresh_token"]

    def test_password_field_validation(self) -> None:
        """Test that password field validation works."""
        request = LoginRequest(
            email="test@example.com",
            password="SecurePassword123!",
        )

        # Password is a plain string field
        assert request.password == "SecurePassword123!"

        # Test that passwords are strings (not SecretStr)
        assert isinstance(request.password, str)


class TestErrorResponseContract:
    """Test error response schema contract."""

    def test_huleedu_error_structure(self) -> None:
        """Test that HuleEduError follows expected structure."""
        error_detail = ErrorDetail(
            error_code=IdentityErrorCode.INVALID_CREDENTIALS,
            message="Invalid credentials",
            correlation_id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            service="identity_service",
            operation="login",
            details={"field": "email"},
        )
        error = HuleEduError(error_detail)

        assert error.error_code == "IDENTITY_INVALID_CREDENTIALS"
        # HuleEduError includes error code in string representation
        assert "Invalid credentials" in str(error)
        assert error.error_detail.details["field"] == "email"

    def test_error_serialization(self) -> None:
        """Test that errors can be serialized to JSON."""
        error_detail = ErrorDetail(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Email format invalid",
            correlation_id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            service="identity_service",
            operation="register",
            details={"email": "not-an-email"},
        )
        error = HuleEduError(error_detail)

        # ErrorDetail can be serialized to dict
        error_dict = error.error_detail.model_dump()
        assert error_dict["error_code"] == "VALIDATION_ERROR"
        assert error_dict["message"] == "Email format invalid"
        assert error_dict["details"]["email"] == "not-an-email"
