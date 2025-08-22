"""
Unit tests for API schemas validation behavior.

Tests focus on Pydantic schema validation patterns including Swedish character
support and field validation rules following established testing patterns.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.identity_service.api.schemas import (
    LoginRequest,
    MeResponse,
    PersonNameSchema,
    ProfileRequest,
    ProfileResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    RegisterResponse,
    RequestEmailVerificationResponse,
    RequestPasswordResetRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TokenPair,
    VerifyEmailRequest,
    VerifyEmailResponse,
)


class TestRequestSchemas:
    """Tests for request schema validation behavior."""

    class TestRegisterRequest:
        """Tests for RegisterRequest schema validation."""

        @pytest.mark.parametrize(
            "email, password, org_id, should_pass",
            [
                # Valid cases
                ("test@example.com", "password123", None, True),
                ("user@domain.com", "securePass456", "org_123", True),
                ("åsa.öberg@skolan.se", "testPass789", "swedish_org", True),
                # Invalid email formats
                ("invalid_email", "password123", None, False),
                ("@domain.com", "password123", None, False),
                ("user@", "password123", None, False),
            ],
        )
        def test_register_request_validation(
            self, email: str, password: str, org_id: str | None, should_pass: bool
        ) -> None:
            """Test RegisterRequest field validation including Swedish emails."""
            if should_pass:
                request = RegisterRequest(
                    email=email,
                    password=password,
                    person_name=PersonNameSchema(
                        first_name="Test",
                        last_name="User",
                        legal_full_name="Test User",
                    ),
                    organization_name="Test Organization",
                    org_id=org_id
                )
                assert request.email == email
                assert request.password == password
                assert request.person_name.first_name == "Test"
                assert request.organization_name == "Test Organization"
                assert request.org_id == org_id
            else:
                with pytest.raises(ValidationError):
                    RegisterRequest(
                        email=email,
                        password=password,
                        person_name=PersonNameSchema(
                            first_name="Test",
                            last_name="User",
                            legal_full_name="Test User",
                        ),
                        organization_name="Test Organization",
                        org_id=org_id
                    )

    class TestLoginRequest:
        """Tests for LoginRequest schema validation."""

        @pytest.mark.parametrize(
            "email, password, should_pass",
            [
                # Valid Swedish emails
                ("märta.ängström@skola.se", "password123", True),
                ("björn.öberg@universitet.se", "securePass456", True),
                ("åsa.åkerström@gymnasium.se", "testPass789", True),
                # Standard valid emails
                ("teacher@school.edu", "myPassword", True),
                ("student@college.org", "studentPass", True),
                # Invalid formats
                ("not_an_email", "password", False),
                ("missing@.com", "password", False),
            ],
        )
        def test_login_request_validation(
            self, email: str, password: str, should_pass: bool
        ) -> None:
            """Test LoginRequest validation with Swedish and standard email formats."""
            if should_pass:
                request = LoginRequest(email=email, password=password)
                assert request.email == email
                assert request.password == password
            else:
                with pytest.raises(ValidationError):
                    LoginRequest(email=email, password=password)

        def test_login_request_required_fields(self) -> None:
            """Test that email and password are required fields."""
            with pytest.raises(ValidationError) as exc_info:
                LoginRequest()  # type: ignore

            errors = exc_info.value.errors()
            error_fields = {error["loc"][0] for error in errors}
            assert "email" in error_fields
            assert "password" in error_fields

    class TestPasswordResetRequest:
        """Tests for password reset request schemas."""

        def test_request_password_reset_request_with_swedish_email(self) -> None:
            """Test RequestPasswordResetRequest with Swedish email address."""
            swedish_email = "åsa.lindström@skolan.se"
            request = RequestPasswordResetRequest(email=swedish_email)
            assert request.email == swedish_email

        def test_reset_password_request_validation(self) -> None:
            """Test ResetPasswordRequest field validation."""
            token = "reset_token_abc123"
            new_password = "newSecurePassword456"

            request = ResetPasswordRequest(token=token, new_password=new_password)
            assert request.token == token
            assert request.new_password == new_password

        def test_reset_password_request_required_fields(self) -> None:
            """Test that both token and new_password are required."""
            with pytest.raises(ValidationError):
                ResetPasswordRequest(token="test_token")  # type: ignore

            with pytest.raises(ValidationError):
                ResetPasswordRequest(new_password="password")  # type: ignore

    class TestTokenRequest:
        """Tests for token-related request schemas."""

        def test_refresh_token_request_validation(self) -> None:
            """Test RefreshTokenRequest validation."""
            token = "refresh_token_xyz789"
            request = RefreshTokenRequest(refresh_token=token)
            assert request.refresh_token == token

        def test_verify_email_request_validation(self) -> None:
            """Test VerifyEmailRequest validation."""
            token = "email_verification_token_123"
            request = VerifyEmailRequest(token=token)
            assert request.token == token


class TestResponseSchemas:
    """Tests for response schema serialization behavior."""

    class TestTokenPair:
        """Tests for TokenPair response schema."""

        def test_token_pair_creation_with_defaults(self) -> None:
            """Test TokenPair with default token_type value."""
            access_token = "access_token_123"
            refresh_token = "refresh_token_456"
            expires_in = 3600

            token_pair = TokenPair(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
            )

            assert token_pair.access_token == access_token
            assert token_pair.refresh_token == refresh_token
            assert token_pair.token_type == "Bearer"  # Default value
            assert token_pair.expires_in == expires_in

        def test_token_pair_custom_token_type(self) -> None:
            """Test TokenPair with custom token_type."""
            token_pair = TokenPair(
                access_token="access_123",
                refresh_token="refresh_456",
                expires_in=7200,
                token_type="Custom",
            )
            assert token_pair.token_type == "Custom"

    class TestUserResponse:
        """Tests for user-related response schemas."""

        def test_me_response_with_swedish_email(self) -> None:
            """Test MeResponse with Swedish email and optional fields."""
            user_id = "user_123"
            swedish_email = "gunnar.åström@skolan.se"
            org_id = "org_456"
            roles = ["teacher", "admin"]

            response = MeResponse(
                user_id=user_id,
                email=swedish_email,
                org_id=org_id,
                roles=roles,
                email_verified=True,
            )

            assert response.user_id == user_id
            assert response.email == swedish_email
            assert response.org_id == org_id
            assert response.roles == roles
            assert response.email_verified is True

        def test_me_response_with_defaults(self) -> None:
            """Test MeResponse with default values for optional fields."""
            response = MeResponse(
                user_id="user_789",
                email="test@example.com",
            )

            assert response.org_id is None
            assert response.roles == []
            assert response.email_verified is False

        def test_register_response_validation(self) -> None:
            """Test RegisterResponse field handling."""
            user_id = "user_abc"
            email = "new.user@domain.com"
            org_id = "organization_123"

            response = RegisterResponse(
                user_id=user_id,
                email=email,
                org_id=org_id,
                email_verification_required=False,
            )

            assert response.user_id == user_id
            assert response.email == email
            assert response.org_id == org_id
            assert response.email_verification_required is False

    class TestProfileSchemas:
        """Tests for profile-related schemas with Swedish names."""

        def test_person_name_schema_with_swedish_characters(self) -> None:
            """Test PersonNameSchema with Swedish character names."""
            first_name = "Åsa"
            last_name = "Öberg-Ström"
            legal_full_name = "Åsa Margareta Öberg-Ström"

            person_name = PersonNameSchema(
                first_name=first_name,
                last_name=last_name,
                legal_full_name=legal_full_name,
            )

            assert person_name.first_name == first_name
            assert person_name.last_name == last_name
            assert person_name.legal_full_name == legal_full_name

        def test_profile_request_with_swedish_names(self) -> None:
            """Test ProfileRequest with Swedish names and optional fields."""
            first_name = "Erik"
            last_name = "Lindström"
            display_name = "Erik L."
            locale = "sv_SE"

            request = ProfileRequest(
                first_name=first_name,
                last_name=last_name,
                display_name=display_name,
                locale=locale,
            )

            assert request.first_name == first_name
            assert request.last_name == last_name
            assert request.display_name == display_name
            assert request.locale == locale

        def test_profile_response_serialization(self) -> None:
            """Test ProfileResponse with nested PersonNameSchema."""
            person_name = PersonNameSchema(
                first_name="Anna",
                last_name="Andersson",
                legal_full_name="Anna Margareta Andersson",
            )

            response = ProfileResponse(
                person_name=person_name,
                display_name="Anna A.",
                locale="sv_SE",
            )

            assert response.person_name.first_name == "Anna"
            assert response.person_name.last_name == "Andersson"
            assert response.display_name == "Anna A."
            assert response.locale == "sv_SE"


class TestFieldValidation:
    """Tests for specific field validation rules."""

    class TestEmailValidation:
        """Tests for email field validation across schemas."""

        @pytest.mark.parametrize(
            "email, should_be_valid",
            [
                # Valid Swedish email formats
                ("åsa.öberg@skolan.se", True),
                ("märta@universitet.se", True),
                ("björn.ångström@gymnasium.se", True),
                ("erik_lindström@school.edu", True),
                # Valid international formats
                ("user@domain.com", True),
                ("test.email@subdomain.example.org", True),
                ("user+tag@domain.co.uk", True),
                # Invalid formats
                ("plainaddress", False),
                ("@domain.com", False),
                ("user@", False),
                ("user..double.dot@domain.com", False),
                ("user@.com", False),
            ],
        )
        def test_email_validation_patterns(self, email: str, should_be_valid: bool) -> None:
            """Test email validation patterns including Swedish characters."""
            if should_be_valid:
                # Test with RegisterRequest
                request = RegisterRequest(
                    email=email,
                    password="testpass",
                    person_name=PersonNameSchema(
                        first_name="Test",
                        last_name="User",
                        legal_full_name="Test User",
                    ),
                    organization_name="Test Organization"
                )
                assert request.email == email

                # Test with LoginRequest
                login = LoginRequest(email=email, password="testpass")
                assert login.email == email
            else:
                with pytest.raises(ValidationError):
                    RegisterRequest(
                        email=email,
                        password="testpass",
                        person_name=PersonNameSchema(
                            first_name="Test",
                            last_name="User",
                            legal_full_name="Test User",
                        ),
                        organization_name="Test Organization"
                    )
                with pytest.raises(ValidationError):
                    LoginRequest(email=email, password="testpass")

    class TestStringFieldValidation:
        """Tests for string field constraints and handling."""

        def test_empty_string_handling(self) -> None:
            """Test handling of empty strings in required fields."""
            # Empty email should fail validation (EmailStr type)
            with pytest.raises(ValidationError):
                LoginRequest(email="", password="password")

            # Empty password is allowed by Pydantic (str type)
            request = LoginRequest(email="test@domain.com", password="")
            assert request.password == ""

        def test_token_field_validation(self) -> None:
            """Test token string field validation."""
            # Valid token strings
            token_values = [
                "simple_token",
                "token_with_123_numbers",
                "jwt.token.with.dots",
                "very-long-token-string-with-hyphens-and-underscores_123",
            ]

            for token in token_values:
                request = VerifyEmailRequest(token=token)
                assert request.token == token

                refresh_request = RefreshTokenRequest(refresh_token=token)
                assert refresh_request.refresh_token == token

    class TestResponseFieldSerialization:
        """Tests for response field serialization behavior."""

        def test_message_response_serialization(self) -> None:
            """Test message and correlation_id field serialization."""
            message = "Email verification sent successfully"
            correlation_id = "corr_123_abc"

            response = RequestEmailVerificationResponse(
                message=message,
                correlation_id=correlation_id,
            )

            # Test dict serialization
            response_dict = response.model_dump()
            assert response_dict["message"] == message
            assert response_dict["correlation_id"] == correlation_id

        def test_password_reset_response_serialization(self) -> None:
            """Test password reset response field handling."""
            reset_response = ResetPasswordResponse(message="Password reset successfully")

            verify_response = VerifyEmailResponse(message="Email verified successfully")

            # Test serialization
            assert reset_response.model_dump()["message"] == "Password reset successfully"
            assert verify_response.model_dump()["message"] == "Email verified successfully"

        def test_refresh_token_response_defaults(self) -> None:
            """Test RefreshTokenResponse default values."""
            access_token = "new_access_token_123"
            expires_in = 1800

            response = RefreshTokenResponse(
                access_token=access_token,
                expires_in=expires_in,
            )

            assert response.access_token == access_token
            assert response.token_type == "Bearer"  # Default value
            assert response.expires_in == expires_in

            # Test serialization includes defaults
            response_dict = response.model_dump()
            assert response_dict["token_type"] == "Bearer"
