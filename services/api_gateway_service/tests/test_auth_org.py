"""
Focused tests for org_id extraction from JWT in API Gateway Service.

Keeps scope limited to AuthProvider.provide_org_id behavior.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import jwt
import pytest
from fastapi import Request

from services.api_gateway_service.app.auth_provider import AuthProvider
from services.api_gateway_service.config import settings
from services.api_gateway_service.tests.test_auth import TestJWTAuthentication


class TestJWTOrgIdExtraction:
    """Test suite for org_id extraction from JWT via AuthProvider.provide_org_id."""

    def _create_mock_request(self, authorization_header: str | None = None) -> Mock:
        mock_request = Mock(spec=Request)
        headers = {}
        if authorization_header:
            headers["Authorization"] = authorization_header
        mock_request.headers = headers
        mock_request.state.correlation_id = uuid4()
        return mock_request

    @pytest.mark.asyncio
    async def test_extract_org_id_from_org_id_claim(self):
        auth = TestJWTAuthentication()
        token = auth.create_token_with_claims("user-1", {"org_id": "org-123"})
        mock_request = self._create_mock_request(f"Bearer {token}")

        provider = AuthProvider()
        bearer_token = provider.extract_bearer_token(mock_request)
        result = provider.provide_org_id(bearer_token, settings, mock_request)
        assert result == "org-123"

    @pytest.mark.asyncio
    async def test_extract_org_id_from_org_alias_claim(self):
        auth = TestJWTAuthentication()
        token = auth.create_token_with_claims("user-1", {"org": "ORG-ALIAS"})
        mock_request = self._create_mock_request(f"Bearer {token}")

        provider = AuthProvider()
        bearer_token = provider.extract_bearer_token(mock_request)
        result = provider.provide_org_id(bearer_token, settings, mock_request)
        assert result == "ORG-ALIAS"

    @pytest.mark.asyncio
    async def test_extract_org_id_from_organization_id_claim(self):
        auth = TestJWTAuthentication()
        token = auth.create_token_with_claims("user-1", {"organization_id": "org-xyz"})
        mock_request = self._create_mock_request(f"Bearer {token}")

        provider = AuthProvider()
        bearer_token = provider.extract_bearer_token(mock_request)
        result = provider.provide_org_id(bearer_token, settings, mock_request)
        assert result == "org-xyz"

    @pytest.mark.asyncio
    async def test_no_org_claims_returns_none(self):
        auth = TestJWTAuthentication()
        token = auth.create_test_token("user-1")
        mock_request = self._create_mock_request(f"Bearer {token}")

        provider = AuthProvider()
        bearer_token = provider.extract_bearer_token(mock_request)
        result = provider.provide_org_id(bearer_token, settings, mock_request)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_org_id_is_ignored(self):
        auth = TestJWTAuthentication()
        token = auth.create_token_with_claims("user-1", {"org_id": "   "})
        mock_request = self._create_mock_request(f"Bearer {token}")

        provider = AuthProvider()
        bearer_token = provider.extract_bearer_token(mock_request)
        result = provider.provide_org_id(bearer_token, settings, mock_request)
        assert result is None

    @pytest.mark.asyncio
    async def test_non_string_org_id_is_ignored(self):
        auth = TestJWTAuthentication()
        token = auth.create_token_with_claims("user-1", {"org_id": 12345})
        mock_request = self._create_mock_request(f"Bearer {token}")

        provider = AuthProvider()
        bearer_token = provider.extract_bearer_token(mock_request)
        result = provider.provide_org_id(bearer_token, settings, mock_request)
        assert result is None

    @pytest.mark.asyncio
    async def test_org_id_provider_expired_token(self):
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        auth = TestJWTAuthentication()
        token = auth.create_token_with_claims(
            "user-1", {"org_id": "org-1"}, exp_delta=timedelta(hours=-1)
        )
        mock_request = self._create_mock_request(f"Bearer {token}")

        provider = AuthProvider()
        bearer_token = provider.extract_bearer_token(mock_request)
        with pytest.raises(HuleEduError):
            provider.provide_org_id(bearer_token, settings, mock_request)

    @pytest.mark.asyncio
    async def test_org_id_provider_missing_exp_claim(self):
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        # Build token without exp
        payload = {"sub": "user-1", "org_id": "org-1"}
        token = jwt.encode(
            payload, settings.JWT_SECRET_KEY.get_secret_value(), algorithm=settings.JWT_ALGORITHM
        )
        mock_request = self._create_mock_request(f"Bearer {token}")

        provider = AuthProvider()
        bearer_token = provider.extract_bearer_token(mock_request)
        with pytest.raises(HuleEduError):
            provider.provide_org_id(bearer_token, settings, mock_request)
