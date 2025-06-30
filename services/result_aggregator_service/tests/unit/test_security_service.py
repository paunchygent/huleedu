"""Unit tests for SecurityServiceImpl."""

from __future__ import annotations

from typing import List
from unittest.mock import AsyncMock, patch

import pytest

from services.result_aggregator_service.implementations.security_impl import (
    SecurityServiceImpl,
)


@pytest.fixture
def security_service() -> SecurityServiceImpl:
    """Create a security service instance."""
    return SecurityServiceImpl(
        internal_api_key="test-api-key-123",
        allowed_service_ids=["batch_orchestrator", "essay_lifecycle", "api_gateway"],
    )


class TestSecurityServiceImpl:
    """Test cases for SecurityServiceImpl."""

    async def test_validate_service_credentials_valid_key_and_service(
        self,
        security_service: SecurityServiceImpl,
    ) -> None:
        """Test successful validation with correct API key and allowed service."""
        # Act
        result: bool = await security_service.validate_service_credentials(
            api_key="test-api-key-123",
            service_id="batch_orchestrator",
        )

        # Assert
        assert result is True

    async def test_validate_service_credentials_invalid_key(
        self,
        security_service: SecurityServiceImpl,
    ) -> None:
        """Test validation failure with incorrect API key."""
        # Act
        result: bool = await security_service.validate_service_credentials(
            api_key="wrong-api-key",
            service_id="batch_orchestrator",
        )

        # Assert
        assert result is False

    async def test_validate_service_credentials_valid_key_invalid_service(
        self,
        security_service: SecurityServiceImpl,
    ) -> None:
        """Test validation failure with correct API key but unauthorized service."""
        # Act
        result: bool = await security_service.validate_service_credentials(
            api_key="test-api-key-123",
            service_id="unauthorized_service",
        )

        # Assert
        assert result is False

    async def test_validate_service_credentials_empty_key(
        self,
        security_service: SecurityServiceImpl,
    ) -> None:
        """Test validation failure with empty API key."""
        # Act
        result: bool = await security_service.validate_service_credentials(
            api_key="",
            service_id="batch_orchestrator",
        )

        # Assert
        assert result is False

    async def test_validate_service_credentials_empty_service_id(
        self,
        security_service: SecurityServiceImpl,
    ) -> None:
        """Test validation failure with empty service ID."""
        # Act
        result: bool = await security_service.validate_service_credentials(
            api_key="test-api-key-123",
            service_id="",
        )

        # Assert
        assert result is False

    async def test_validate_service_credentials_both_invalid(
        self,
        security_service: SecurityServiceImpl,
    ) -> None:
        """Test validation failure with both invalid API key and service."""
        # Act
        result: bool = await security_service.validate_service_credentials(
            api_key="wrong-key",
            service_id="wrong-service",
        )

        # Assert
        assert result is False

    async def test_validate_service_credentials_all_allowed_services(
        self,
        security_service: SecurityServiceImpl,
    ) -> None:
        """Test that all configured allowed services can authenticate."""
        allowed_services: List[str] = ["batch_orchestrator", "essay_lifecycle", "api_gateway"]

        # Act & Assert
        for service_id in allowed_services:
            result: bool = await security_service.validate_service_credentials(
                api_key="test-api-key-123",
                service_id=service_id,
            )
            assert result is True, f"Expected {service_id} to be allowed"

    async def test_validate_service_credentials_case_sensitivity(
        self,
        security_service: SecurityServiceImpl,
    ) -> None:
        """Test that API key and service ID validation is case-sensitive."""
        # Test API key case sensitivity
        result_upper_key: bool = await security_service.validate_service_credentials(
            api_key="TEST-API-KEY-123",
            service_id="batch_orchestrator",
        )
        assert result_upper_key is False

        # Test service ID case sensitivity
        result_upper_service: bool = await security_service.validate_service_credentials(
            api_key="test-api-key-123",
            service_id="BATCH_ORCHESTRATOR",
        )
        assert result_upper_service is False

    async def test_security_service_initialization(
        self,
    ) -> None:
        """Test that security service initializes correctly."""
        # Arrange
        api_key: str = "custom-key-456"
        allowed_services: List[str] = ["service1", "service2", "service3"]

        # Act
        service: SecurityServiceImpl = SecurityServiceImpl(
            internal_api_key=api_key,
            allowed_service_ids=allowed_services,
        )

        # Assert
        assert service.internal_api_key == api_key
        assert isinstance(service.allowed_service_ids, set)
        assert len(service.allowed_service_ids) == 3
        assert "service1" in service.allowed_service_ids
        assert "service2" in service.allowed_service_ids
        assert "service3" in service.allowed_service_ids

    @patch("services.result_aggregator_service.implementations.security_impl.logger")
    async def test_validate_service_credentials_logs_invalid_api_key(
        self,
        mock_logger: AsyncMock,
        security_service: SecurityServiceImpl,
    ) -> None:
        """Test that invalid API key is logged."""
        # Act
        result: bool = await security_service.validate_service_credentials(
            api_key="wrong-key",
            service_id="batch_orchestrator",
        )

        # Assert
        assert result is False
        mock_logger.warning.assert_called_once_with(
            "Invalid API key provided",
            service_id="batch_orchestrator",
        )

    @patch("services.result_aggregator_service.implementations.security_impl.logger")
    async def test_validate_service_credentials_logs_unauthorized_service(
        self,
        mock_logger: AsyncMock,
        security_service: SecurityServiceImpl,
    ) -> None:
        """Test that unauthorized service is logged."""
        # Act
        result: bool = await security_service.validate_service_credentials(
            api_key="test-api-key-123",
            service_id="unauthorized_service",
        )

        # Assert
        assert result is False
        mock_logger.warning.assert_called_once()

        # Get the actual call arguments
        call_args = mock_logger.warning.call_args
        assert call_args[0][0] == "Service not allowed"
        assert call_args[1]["service_id"] == "unauthorized_service"
        # Check that allowed_services contains the expected values (order doesn't matter)
        assert set(call_args[1]["allowed_services"]) == {
            "api_gateway",
            "batch_orchestrator",
            "essay_lifecycle",
        }

    @patch("services.result_aggregator_service.implementations.security_impl.logger")
    async def test_validate_service_credentials_logs_successful_auth(
        self,
        mock_logger: AsyncMock,
        security_service: SecurityServiceImpl,
    ) -> None:
        """Test that successful authentication is logged."""
        # Act
        result: bool = await security_service.validate_service_credentials(
            api_key="test-api-key-123",
            service_id="batch_orchestrator",
        )

        # Assert
        assert result is True
        mock_logger.debug.assert_called_once_with(
            "Service authenticated successfully",
            service_id="batch_orchestrator",
        )
