"""
Unit tests for well-known routes in Identity Service.

Tests the GET /.well-known/jwks.json endpoint following the established
Quart+Dishka testing patterns with proper DI mocking for OpenID Connect compliance.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import Mock

import pytest
from common_core.identity_models import JwksPublicKeyV1, JwksResponseV1
from dishka import Provider, Scope, make_async_container, provide
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.identity_service.app import app
from services.identity_service.implementations.jwks_store import JwksStore


class TestWellKnownRoutes:
    """Test well-known OpenID Connect endpoints using proper Quart+Dishka patterns."""

    @pytest.fixture
    def mock_jwks_store(self) -> Mock:
        """Create mock JWKS store."""
        return Mock(spec=JwksStore)

    @pytest.fixture
    async def app_client(
        self,
        mock_jwks_store: Mock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """
        Return a Quart test client configured with mocked dependencies using Dishka.
        This fixture overrides production providers with test providers that supply our mocks.
        """

        # 1. Define a test-specific provider that provides our mocks
        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_jwks_store(self) -> JwksStore:
                return mock_jwks_store

        # 2. Create a new container with our test provider
        container = make_async_container(TestProvider())

        # 3. Apply the container to the app instance for the test
        app.config.update({"TESTING": True})
        QuartDishka(app=app, container=container)

        async with app.test_client() as client:
            yield client

        # 4. Clean up the container after the test
        await container.close()

    async def test_jwks_endpoint_success(
        self,
        app_client: QuartTestClient,
        mock_jwks_store: Mock,
    ) -> None:
        """Test successful JWKS endpoint with single key."""
        # Arrange
        test_key = JwksPublicKeyV1(
            kid="test-key-id-123",
            kty="RSA",
            n="test-modulus-value",
            e="AQAB",
            alg="RS256",
            use="sig",
        )
        jwks_response = JwksResponseV1(keys=[test_key])
        mock_jwks_store.get_jwks.return_value = jwks_response

        # Act
        response = await app_client.get("/.well-known/jwks.json")

        # Assert
        assert response.status_code == 200
        data = await response.get_json()

        # Verify JWKS structure compliance
        assert "keys" in data
        assert len(data["keys"]) == 1

        # Verify key structure
        key = data["keys"][0]
        assert key["kid"] == "test-key-id-123"
        assert key["kty"] == "RSA"
        assert key["n"] == "test-modulus-value"
        assert key["e"] == "AQAB"
        assert key["alg"] == "RS256"
        assert key["use"] == "sig"

        # Verify method call
        mock_jwks_store.get_jwks.assert_called_once()

    async def test_jwks_endpoint_content_type(
        self,
        app_client: QuartTestClient,
        mock_jwks_store: Mock,
    ) -> None:
        """Test JWKS endpoint returns proper Content-Type header."""
        # Arrange
        jwks_response = JwksResponseV1(keys=[])
        mock_jwks_store.get_jwks.return_value = jwks_response

        # Act
        response = await app_client.get("/.well-known/jwks.json")

        # Assert
        assert response.status_code == 200
        assert response.content_type == "application/json"

    async def test_jwks_endpoint_multiple_keys(
        self,
        app_client: QuartTestClient,
        mock_jwks_store: Mock,
    ) -> None:
        """Test JWKS endpoint with multiple keys for rotation support."""
        # Arrange
        key1 = JwksPublicKeyV1(
            kid="key-1",
            kty="RSA",
            n="modulus-1",
            e="AQAB",
            alg="RS256",
            use="sig",
        )
        key2 = JwksPublicKeyV1(
            kid="key-2-åäö",  # Swedish characters in key ID
            kty="RSA",
            n="modulus-2",
            e="AQAB",
            alg="RS256",
            use="sig",
        )
        jwks_response = JwksResponseV1(keys=[key1, key2])
        mock_jwks_store.get_jwks.return_value = jwks_response

        # Act
        response = await app_client.get("/.well-known/jwks.json")

        # Assert
        assert response.status_code == 200
        data = await response.get_json()

        # Verify multiple keys
        assert len(data["keys"]) == 2
        assert data["keys"][0]["kid"] == "key-1"
        assert data["keys"][1]["kid"] == "key-2-åäö"  # Swedish characters preserved

        mock_jwks_store.get_jwks.assert_called_once()

    async def test_jwks_endpoint_empty_keys(
        self,
        app_client: QuartTestClient,
        mock_jwks_store: Mock,
    ) -> None:
        """Test JWKS endpoint with empty keys array."""
        # Arrange
        jwks_response = JwksResponseV1(keys=[])
        mock_jwks_store.get_jwks.return_value = jwks_response

        # Act
        response = await app_client.get("/.well-known/jwks.json")

        # Assert
        assert response.status_code == 200
        data = await response.get_json()

        # Verify empty keys array is valid
        assert "keys" in data
        assert data["keys"] == []

        mock_jwks_store.get_jwks.assert_called_once()

    async def test_jwks_endpoint_pydantic_serialization(
        self,
        app_client: QuartTestClient,
        mock_jwks_store: Mock,
    ) -> None:
        """Test JWKS endpoint uses proper Pydantic V2 serialization."""
        # Arrange
        test_key = JwksPublicKeyV1(
            kid="serialization-test",
            kty="RSA",
            n="test-n-value",
            e="AQAB",
        )
        jwks_response = JwksResponseV1(keys=[test_key])
        mock_jwks_store.get_jwks.return_value = jwks_response

        # Act
        response = await app_client.get("/.well-known/jwks.json")

        # Assert
        assert response.status_code == 200
        data = await response.get_json()

        # Verify Pydantic defaults are included
        key = data["keys"][0]
        assert key["alg"] == "RS256"  # Default from Pydantic model
        assert key["use"] == "sig"  # Default from Pydantic model

        # Verify model_dump(mode="json") behavior
        mock_jwks_store.get_jwks.assert_called_once()

        # The response should be JSON-serializable (no raw objects)
        assert isinstance(data, dict)
        assert isinstance(data["keys"], list)
