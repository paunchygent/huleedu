"""
Test environment-based repository selection and configuration.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from services.batch_conductor_service.config import Settings
from services.batch_conductor_service.di import EventDrivenServicesProvider
from services.batch_conductor_service.implementations.batch_state_repository_impl import (
    RedisCachedBatchStateRepositoryImpl,
)
from services.batch_conductor_service.implementations.mock_batch_state_repository import (
    MockBatchStateRepositoryImpl,
)


class TestRepositorySelection:
    """Test repository selection based on environment configuration."""

    @pytest.mark.asyncio
    async def test_development_mode_selection(self) -> None:
        """Test that development mode uses mock repository."""
        # Mock settings for development with USE_MOCK_REPOSITORY=True
        with patch("services.batch_conductor_service.config.Settings") as mock_settings:
            mock_settings_instance = mock_settings.return_value
            mock_settings_instance.ENVIRONMENT = "development"
            mock_settings_instance.USE_MOCK_REPOSITORY = True

            provider = EventDrivenServicesProvider()

            # Call the provider method (would need mock redis client)
            with patch(
                "services.batch_conductor_service.di.AtomicRedisClientProtocol"
            ) as mock_redis:
                repository = provider.provide_batch_state_repository(
                    redis_client=mock_redis, settings=mock_settings_instance
                )

                # Should return MockBatchStateRepositoryImpl
                assert isinstance(repository, MockBatchStateRepositoryImpl)

    @pytest.mark.asyncio
    async def test_production_mode_selection(self) -> None:
        """Test that production mode uses Redis repository."""
        # Mock settings for production with USE_MOCK_REPOSITORY=False
        with patch("services.batch_conductor_service.config.Settings") as mock_settings:
            mock_settings_instance = mock_settings.return_value
            mock_settings_instance.ENVIRONMENT = "production"
            mock_settings_instance.USE_MOCK_REPOSITORY = False
            mock_settings_instance.database_url = "postgresql+asyncpg://test:test@localhost/test"

            provider = EventDrivenServicesProvider()

            # Call the provider method with mock redis client
            with patch(
                "services.batch_conductor_service.di.AtomicRedisClientProtocol"
            ) as mock_redis:
                repository = provider.provide_batch_state_repository(
                    redis_client=mock_redis, settings=mock_settings_instance
                )

                # Should return RedisCachedBatchStateRepositoryImpl
                assert isinstance(repository, RedisCachedBatchStateRepositoryImpl)

    @pytest.mark.asyncio
    async def test_testing_environment_override(self) -> None:
        """Test that testing environment uses mock repository regardless of USE_MOCK_REPOSITORY."""
        # Mock settings for testing environment (should always use mock)
        with patch("services.batch_conductor_service.config.Settings") as mock_settings:
            mock_settings_instance = mock_settings.return_value
            mock_settings_instance.ENVIRONMENT = "testing"
            mock_settings_instance.USE_MOCK_REPOSITORY = False  # This should be ignored

            provider = EventDrivenServicesProvider()

            # Call the provider method
            with patch(
                "services.batch_conductor_service.di.AtomicRedisClientProtocol"
            ) as mock_redis:
                repository = provider.provide_batch_state_repository(
                    redis_client=mock_redis, settings=mock_settings_instance
                )

                # Should return MockBatchStateRepositoryImpl even with USE_MOCK_REPOSITORY=False
                assert isinstance(repository, MockBatchStateRepositoryImpl)

    def test_configuration_pattern_matches_bos_els(self) -> None:
        """Test that configuration pattern matches BOS/ELS exactly."""
        # Test that Settings has the USE_MOCK_REPOSITORY field
        settings = Settings()
        assert hasattr(settings, "USE_MOCK_REPOSITORY")
        assert hasattr(settings, "ENVIRONMENT")

        # Test default values
        assert settings.USE_MOCK_REPOSITORY is False
        assert settings.ENVIRONMENT == "development"

    @pytest.mark.asyncio
    async def test_configuration_override_flag(self) -> None:
        """Test USE_MOCK_REPOSITORY flag override functionality."""
        # Test production environment but with USE_MOCK_REPOSITORY=True
        with patch("services.batch_conductor_service.config.Settings") as mock_settings:
            mock_settings_instance = mock_settings.return_value
            mock_settings_instance.ENVIRONMENT = "production"
            mock_settings_instance.USE_MOCK_REPOSITORY = True  # Override production setting

            provider = EventDrivenServicesProvider()

            with patch(
                "services.batch_conductor_service.di.AtomicRedisClientProtocol"
            ) as mock_redis:
                repository = provider.provide_batch_state_repository(
                    redis_client=mock_redis, settings=mock_settings_instance
                )

                # Should return MockBatchStateRepositoryImpl due to USE_MOCK_REPOSITORY=True
                assert isinstance(repository, MockBatchStateRepositoryImpl)
