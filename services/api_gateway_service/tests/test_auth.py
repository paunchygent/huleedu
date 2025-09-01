"""
Tests for authentication module in API Gateway Service.

Tests JWT token validation, expiry checks, error handling, and security scenarios.
Uses simplified approach to test AuthProvider methods directly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import jwt
import pytest
from fastapi import Request

from services.api_gateway_service.app.auth_provider import AuthProvider
from services.api_gateway_service.config import settings


class TestJWTAuthentication:
    """Test suite for JWT authentication with comprehensive coverage."""

    def create_test_token(self, user_id: str, exp_delta: timedelta | None = None) -> str:
        """Helper method to create test JWT tokens."""
        payload = {"sub": user_id, "exp": datetime.now(UTC) + (exp_delta or timedelta(hours=1))}
        return jwt.encode(
            payload, settings.JWT_SECRET_KEY.get_secret_value(), algorithm=settings.JWT_ALGORITHM
        )

    def create_token_with_claims(
        self, user_id: str, extra_claims: dict, exp_delta: timedelta | None = None
    ) -> str:
        """Helper to create JWT with additional claims for org_id testing."""
        payload = {"sub": user_id, "exp": datetime.now(UTC) + (exp_delta or timedelta(hours=1))}
        payload.update(extra_claims)
        return jwt.encode(
            payload, settings.JWT_SECRET_KEY.get_secret_value(), algorithm=settings.JWT_ALGORITHM
        )

    def create_token_without_exp(self, user_id: str) -> str:
        """Helper method to create JWT token without expiration claim."""
        payload = {"sub": user_id}
        return jwt.encode(
            payload, settings.JWT_SECRET_KEY.get_secret_value(), algorithm=settings.JWT_ALGORITHM
        )

    def create_token_without_sub(self, exp_delta: timedelta | None = None) -> str:
        """Helper method to create JWT token without subject claim."""
        payload = {"exp": datetime.now(UTC) + (exp_delta or timedelta(hours=1))}
        return jwt.encode(
            payload, settings.JWT_SECRET_KEY.get_secret_value(), algorithm=settings.JWT_ALGORITHM
        )

    def _create_mock_request(self, authorization_header: str | None = None) -> Mock:
        """Create a mock request with the given authorization header."""
        mock_request = Mock(spec=Request)
        headers = {}
        if authorization_header:
            headers["Authorization"] = authorization_header
        mock_request.headers = headers
        mock_request.state.correlation_id = uuid4()
        return mock_request

    async def _test_auth_through_container(self, mock_request: Mock) -> str:
        """Test authentication following proper error handling patterns.

        This method directly calls AuthProvider methods and lets any exceptions
        (including HuleEduError) bubble up to the caller for proper testing.
        """
        # Test AuthProvider directly - no container needed for this unit test
        auth_provider = AuthProvider()

        # Let exceptions bubble up naturally - the calling test will handle pytest.raises()
        bearer_token = auth_provider.extract_bearer_token(mock_request)
        user_id: str = auth_provider.provide_user_id(bearer_token, settings, mock_request)
        return user_id

    @pytest.mark.asyncio
    async def test_valid_token_successful_authentication(self):
        """Test successful authentication with valid JWT token."""
        user_id = "test_user_123"
        token = self.create_test_token(user_id)
        mock_request = self._create_mock_request(f"Bearer {token}")

        result = await self._test_auth_through_container(mock_request)
        assert result == user_id

    @pytest.mark.asyncio
    async def test_expired_token_rejection(self):
        """Test rejection of expired JWT token."""
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        user_id = "test_user_123"
        # Create token that expired 1 hour ago
        token = self.create_test_token(user_id, exp_delta=timedelta(hours=-1))
        mock_request = self._create_mock_request(f"Bearer {token}")

        with pytest.raises(HuleEduError) as exc_info:
            await self._test_auth_through_container(mock_request)

        # Verify the error contains expected information
        assert "expired" in exc_info.value.error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_token_without_expiration_claim(self):
        """Test rejection of token missing expiration claim."""
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        user_id = "test_user_123"
        token = self.create_token_without_exp(user_id)
        mock_request = self._create_mock_request(f"Bearer {token}")

        with pytest.raises(HuleEduError) as exc_info:
            await self._test_auth_through_container(mock_request)

        assert "missing expiration claim" in exc_info.value.error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_token_without_subject_claim(self):
        """Test rejection of token missing subject claim."""
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        token = self.create_token_without_sub()
        mock_request = self._create_mock_request(f"Bearer {token}")

        with pytest.raises(HuleEduError) as exc_info:
            await self._test_auth_through_container(mock_request)

        assert "missing subject" in exc_info.value.error_detail.message.lower()

    ## Org ID extraction tests are defined in a separate class at the end of this file.

    @pytest.mark.asyncio
    async def test_invalid_token_signature(self):
        """Test rejection of token with invalid signature."""
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        user_id = "test_user_123"
        # Create token with wrong secret key
        payload = {"sub": user_id, "exp": datetime.now(UTC) + timedelta(hours=1)}
        invalid_token = jwt.encode(payload, "wrong_secret_key", algorithm=settings.JWT_ALGORITHM)
        mock_request = self._create_mock_request(f"Bearer {invalid_token}")

        with pytest.raises(HuleEduError) as exc_info:
            await self._test_auth_through_container(mock_request)

        assert "could not validate credentials" in exc_info.value.error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_malformed_token(self):
        """Test rejection of malformed JWT token."""
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        malformed_token = "not.a.valid.jwt.token"
        mock_request = self._create_mock_request(f"Bearer {malformed_token}")

        with pytest.raises(HuleEduError) as exc_info:
            await self._test_auth_through_container(mock_request)

        assert "could not validate credentials" in exc_info.value.error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_missing_authorization_header(self):
        """Test rejection when Authorization header is missing."""
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        mock_request = self._create_mock_request()

        with pytest.raises(HuleEduError) as exc_info:
            await self._test_auth_through_container(mock_request)

        assert "not authenticated" in exc_info.value.error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_invalid_authorization_format(self):
        """Test rejection of invalid authorization format."""
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        mock_request = self._create_mock_request("InvalidFormat token123")

        with pytest.raises(HuleEduError) as exc_info:
            await self._test_auth_through_container(mock_request)

        assert "invalid authentication format" in exc_info.value.error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_token_with_wrong_algorithm(self):
        """Test rejection of token created with wrong algorithm."""
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        user_id = "test_user_123"
        payload = {"sub": user_id, "exp": datetime.now(UTC) + timedelta(hours=1)}
        # Create token with different algorithm
        wrong_algorithm_token = jwt.encode(
            payload, settings.JWT_SECRET_KEY.get_secret_value(), algorithm="HS512"
        )
        mock_request = self._create_mock_request(f"Bearer {wrong_algorithm_token}")

        with pytest.raises(HuleEduError) as exc_info:
            await self._test_auth_through_container(mock_request)

        assert "could not validate credentials" in exc_info.value.error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_user_id_extraction_from_subject_claim(self):
        """Test proper extraction of user ID from JWT subject claim."""
        test_cases = [
            "simple_user",
            "user_with_123_numbers",
            "user@domain.com",
            "user-with-dashes",
            "user_with_underscores",
            "123456789",  # Numeric user ID
        ]

        for user_id in test_cases:
            token = self.create_test_token(user_id)
            mock_request = self._create_mock_request(f"Bearer {token}")
            result = await self._test_auth_through_container(mock_request)
            assert result == user_id

    @pytest.mark.asyncio
    async def test_token_with_additional_claims(self):
        """Test token validation with additional claims beyond required ones."""
        user_id = "test_user_123"
        payload = {
            "sub": user_id,
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "iat": datetime.now(UTC),
            "role": "admin",
            "permissions": ["read", "write"],
        }
        token = jwt.encode(
            payload, settings.JWT_SECRET_KEY.get_secret_value(), algorithm=settings.JWT_ALGORITHM
        )
        mock_request = self._create_mock_request(f"Bearer {token}")

        result = await self._test_auth_through_container(mock_request)
        assert result == user_id

    @pytest.mark.asyncio
    async def test_null_subject_claim_handling(self):
        """Test handling of null subject claim in JWT payload."""
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        payload = {"sub": None, "exp": datetime.now(UTC) + timedelta(hours=1)}
        token = jwt.encode(
            payload, settings.JWT_SECRET_KEY.get_secret_value(), algorithm=settings.JWT_ALGORITHM
        )
        mock_request = self._create_mock_request(f"Bearer {token}")

        with pytest.raises(HuleEduError) as exc_info:
            await self._test_auth_through_container(mock_request)

        assert "subject must be a string" in exc_info.value.error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_empty_subject_claim_handling(self):
        """Test handling of empty string subject claim in JWT payload."""
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        payload = {"sub": "", "exp": datetime.now(UTC) + timedelta(hours=1)}
        token = jwt.encode(
            payload, settings.JWT_SECRET_KEY.get_secret_value(), algorithm=settings.JWT_ALGORITHM
        )
        mock_request = self._create_mock_request(f"Bearer {token}")

        with pytest.raises(HuleEduError) as exc_info:
            await self._test_auth_through_container(mock_request)

        assert "missing subject" in exc_info.value.error_detail.message.lower()
