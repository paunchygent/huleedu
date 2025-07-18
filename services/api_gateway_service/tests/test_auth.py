"""
Tests for authentication module in API Gateway Service.

Tests JWT token validation, expiry checks, error handling, and security scenarios.
Follows Rule 070.1 (Protocol-based mocking) and comprehensive error handling validation.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
import pytest
from fastapi import HTTPException, status

from services.api_gateway_service.auth import get_current_user_id
from services.api_gateway_service.config import settings


class TestJWTAuthentication:
    """Test suite for JWT authentication with comprehensive coverage."""

    def create_test_token(self, user_id: str, exp_delta: timedelta | None = None) -> str:
        """Helper method to create test JWT tokens."""
        payload = {"sub": user_id, "exp": datetime.now(UTC) + (exp_delta or timedelta(hours=1))}
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    def create_token_without_exp(self, user_id: str) -> str:
        """Helper method to create JWT token without expiration claim."""
        payload = {"sub": user_id}
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    def create_token_without_sub(self, exp_delta: timedelta | None = None) -> str:
        """Helper method to create JWT token without subject claim."""
        payload = {"exp": datetime.now(UTC) + (exp_delta or timedelta(hours=1))}
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    @pytest.mark.asyncio
    async def test_valid_token_successful_authentication(self):
        """Test successful authentication with valid JWT token."""
        user_id = "test_user_123"
        token = self.create_test_token(user_id)

        result = await get_current_user_id(token)

        assert result == user_id

    @pytest.mark.asyncio
    async def test_expired_token_rejection(self):
        """Test rejection of expired JWT token."""
        user_id = "test_user_123"
        # Create token that expired 1 hour ago
        token = self.create_test_token(user_id, exp_delta=timedelta(hours=-1))

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_token_without_expiration_claim(self):
        """Test rejection of token missing expiration claim."""
        user_id = "test_user_123"
        token = self.create_token_without_exp(user_id)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "missing expiration claim" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_token_without_subject_claim(self):
        """Test rejection of token missing subject claim."""
        token = self.create_token_without_sub()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "missing subject" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invalid_token_signature(self):
        """Test rejection of token with invalid signature."""
        user_id = "test_user_123"
        # Create token with wrong secret key
        payload = {"sub": user_id, "exp": datetime.now(UTC) + timedelta(hours=1)}
        invalid_token = jwt.encode(payload, "wrong_secret_key", algorithm=settings.JWT_ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(invalid_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "could not validate credentials" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_malformed_token(self):
        """Test rejection of malformed JWT token."""
        malformed_token = "not.a.valid.jwt.token"

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(malformed_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "could not validate credentials" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_empty_token(self):
        """Test rejection of empty token."""
        empty_token = ""

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(empty_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "could not validate credentials" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_token_with_wrong_algorithm(self):
        """Test rejection of token created with wrong algorithm."""
        user_id = "test_user_123"
        payload = {"sub": user_id, "exp": datetime.now(UTC) + timedelta(hours=1)}
        # Create token with different algorithm
        wrong_algorithm_token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS512")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(wrong_algorithm_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "could not validate credentials" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_token_expiry_boundary_conditions(self):
        """Test token expiry validation at boundary conditions."""
        user_id = "test_user_123"

        # Test token that expires in 1 second
        token = self.create_test_token(user_id, exp_delta=timedelta(seconds=1))
        result = await get_current_user_id(token)
        assert result == user_id

        # Test token that just expired (1 second ago)
        expired_token = self.create_test_token(user_id, exp_delta=timedelta(seconds=-1))
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(expired_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_token_expiry_validation_with_manual_check(self):
        """Test manual expiry validation logic separate from JWT library."""
        user_id = "test_user_123"

        # Create token with expiry timestamp
        exp_timestamp = int(time.time()) + 3600  # 1 hour from now
        payload = {"sub": user_id, "exp": exp_timestamp}
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        result = await get_current_user_id(token)
        assert result == user_id

        # Test with expired timestamp
        expired_timestamp = int(time.time()) - 3600  # 1 hour ago
        expired_payload = {"sub": user_id, "exp": expired_timestamp}
        expired_token = jwt.encode(
            expired_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(expired_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in exc_info.value.detail.lower()

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
            result = await get_current_user_id(token)
            assert result == user_id

    @pytest.mark.asyncio
    async def test_jwt_library_expired_signature_error(self):
        """Test handling of PyJWT ExpiredSignatureError specifically."""
        user_id = "test_user_123"

        # Create token with past expiry that will trigger PyJWT ExpiredSignatureError
        past_exp = datetime.now(UTC) - timedelta(hours=2)
        payload = {"sub": user_id, "exp": past_exp}
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_unexpected_exception_handling(self):
        """Test handling of unexpected exceptions during JWT validation."""
        user_id = "test_user_123"
        token = self.create_test_token(user_id)

        # Mock jwt.decode to raise unexpected exception
        with patch("services.api_gateway_service.auth.jwt.decode") as mock_decode:
            mock_decode.side_effect = ValueError("Unexpected error")

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user_id(token)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert exc_info.value.detail == "Authentication failed"

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
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        result = await get_current_user_id(token)
        assert result == user_id

    @pytest.mark.asyncio
    async def test_null_subject_claim_handling(self):
        """Test handling of null subject claim in JWT payload."""
        payload = {"sub": None, "exp": datetime.now(UTC) + timedelta(hours=1)}
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "missing subject" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_empty_subject_claim_handling(self):
        """Test handling of empty string subject claim in JWT payload."""
        payload = {"sub": "", "exp": datetime.now(UTC) + timedelta(hours=1)}
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "missing subject" in exc_info.value.detail.lower()
