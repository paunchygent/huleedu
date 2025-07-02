"""Unit tests for cache manager implementation."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.cache_manager_impl import RedisCacheManagerImpl


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Mock Redis client for testing."""
    redis_client = AsyncMock()
    redis_client.get = AsyncMock(return_value=None)
    redis_client.setex = AsyncMock()
    redis_client.delete_key = AsyncMock()
    return redis_client


@pytest.fixture
def mock_settings() -> MagicMock:
    """Mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.SERVICE_NAME = "llm-provider-service"
    settings.CACHE_KEY_PREFIX = "llm_test"
    settings.CACHE_TTL = 3600
    settings.CACHE_COMPRESSION_ENABLED = False
    settings.LLM_CACHE_ENABLED = True
    return settings


@pytest.fixture
def cache_manager(mock_redis_client: AsyncMock, mock_settings: MagicMock) -> RedisCacheManagerImpl:
    """Create cache manager with mocked dependencies."""
    return RedisCacheManagerImpl(redis_client=mock_redis_client, settings=mock_settings)


@pytest.mark.asyncio
async def test_cache_manager_get_miss(
    cache_manager: RedisCacheManagerImpl, mock_redis_client: AsyncMock
) -> None:
    """Test cache manager handles cache miss."""
    # Arrange
    cache_key = "test_key"
    mock_redis_client.get.return_value = None

    # Act
    result = await cache_manager.get_cached_response(cache_key)

    # Assert
    assert result is None
    mock_redis_client.get.assert_called_once_with(f"llm-provider-service:cache:{cache_key}")


@pytest.mark.asyncio
async def test_cache_manager_get_hit(
    cache_manager: RedisCacheManagerImpl, mock_redis_client: AsyncMock
) -> None:
    """Test cache manager returns cached data."""
    # Arrange
    cache_key = "test_key"
    cached_data = {
        "choice": "A",
        "reasoning": "Cached reasoning",
        "confidence": 0.9,
        "model": "test-model",
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    mock_redis_client.get.return_value = json.dumps(cached_data)

    # Act
    result = await cache_manager.get_cached_response(cache_key)

    # Assert
    assert result == cached_data
    mock_redis_client.get.assert_called_once_with(f"llm-provider-service:cache:{cache_key}")


@pytest.mark.asyncio
async def test_cache_manager_get_invalid_json(
    cache_manager: RedisCacheManagerImpl, mock_redis_client: AsyncMock
) -> None:
    """Test cache manager handles invalid JSON gracefully."""
    # Arrange
    cache_key = "test_key"
    mock_redis_client.get.return_value = "invalid json"

    # Act
    result = await cache_manager.get_cached_response(cache_key)

    # Assert
    assert result is None


@pytest.mark.asyncio
async def test_cache_manager_cache_response(
    cache_manager: RedisCacheManagerImpl, mock_redis_client: AsyncMock
) -> None:
    """Test cache manager stores response data."""
    # Arrange
    cache_key = "test_key"
    response_data = {
        "choice": "B",
        "reasoning": "New reasoning",
        "confidence": 0.8,
    }

    # Act
    await cache_manager.cache_response(cache_key, response_data, ttl=1800)

    # Assert
    mock_redis_client.setex.assert_called_once()
    call_args = mock_redis_client.setex.call_args
    assert call_args[0][0] == f"llm-provider-service:cache:{cache_key}"
    assert call_args[0][1] == 1800

    # The cache manager adds metadata
    cached_data = json.loads(call_args[0][2])
    assert cached_data["choice"] == response_data["choice"]
    assert cached_data["reasoning"] == response_data["reasoning"]
    assert cached_data["confidence"] == response_data["confidence"]
    assert "_cached_at" in cached_data  # Metadata field
    assert cached_data["_cache_ttl"] == 1800  # Metadata field


@pytest.mark.asyncio
async def test_cache_manager_generate_cache_key(cache_manager: RedisCacheManagerImpl) -> None:
    """Test cache key generation is consistent."""
    # Arrange
    provider = "openai"
    user_prompt = "Compare these essays"
    essay_a = "Essay A content"
    essay_b = "Essay B content"

    # Act
    key1 = cache_manager.generate_cache_key(provider, user_prompt, essay_a, essay_b)
    key2 = cache_manager.generate_cache_key(provider, user_prompt, essay_a, essay_b)

    # Assert
    assert key1 == key2
    assert key1.startswith("llm:openai:")
    assert len(key1.split(":")[-1]) == 16  # Last part is 16 chars of hash


@pytest.mark.asyncio
async def test_cache_manager_generate_cache_key_with_params(
    cache_manager: RedisCacheManagerImpl,
) -> None:
    """Test cache key includes additional parameters."""
    # Arrange
    provider = "openai"
    user_prompt = "Compare"
    essay_a = "A"
    essay_b = "B"

    # Act
    key1 = cache_manager.generate_cache_key(provider, user_prompt, essay_a, essay_b)
    key2 = cache_manager.generate_cache_key(
        provider, user_prompt, essay_a, essay_b, temperature=0.5
    )
    key3 = cache_manager.generate_cache_key(
        provider, user_prompt, essay_a, essay_b, temperature=0.7
    )

    # Assert
    assert key1 != key2  # Different parameters should produce different keys
    assert key2 != key3  # Different parameter values should produce different keys


@pytest.mark.asyncio
async def test_cache_manager_error_handling(
    cache_manager: RedisCacheManagerImpl, mock_redis_client: AsyncMock
) -> None:
    """Test cache manager handles Redis errors by raising CacheConnectionError."""
    # Arrange
    cache_key = "test_key"
    mock_redis_client.get.side_effect = Exception("Redis connection error")

    # Act & Assert
    from services.llm_provider_service.exceptions import CacheConnectionError

    with pytest.raises(CacheConnectionError, match="Failed to retrieve from cache"):
        await cache_manager.get_cached_response(cache_key)
