"""Unit tests for PolicyLoaderImpl YAML policy loading and Redis caching implementation.

Tests focus on behavioral validation of policy loading, caching operations, cost calculations,
validation logic, and cache refresh mechanisms with Swedish character support.
Following Rule 075 methodology with AsyncMock(spec=Protocol) patterns.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.entitlements_service.implementations.policy_loader_impl import PolicyLoaderImpl
from services.entitlements_service.protocols import PolicyConfig


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Create mock Redis client following AtomicRedisClientProtocol."""
    return AsyncMock(spec=AtomicRedisClientProtocol)


@pytest.fixture
def valid_policy_data() -> dict:
    """Valid policy configuration with Swedish metric names."""
    return {
        "costs": {
            "grammatik_kontroll": 10,
            "språk_bedömning": 15,
            "rätt_stavning": 5,
            "basic_spell_check": 2,
            "advanced_analysis": 25,
        },
        "rate_limits": {
            "grammatik_kontroll": "100/hour",
            "språk_bedömning": "50/day",
            "rätt_stavning": "unlimited",
            "essay_analysis": "10/hour",
        },
        "signup_bonuses": {
            "student": 100,
            "teacher": 500,
            "school": 1000,
            "universitet_göteborg": 2000,
        },
        "cache_ttl": 600,
    }


@pytest.fixture
def temp_policy_file(valid_policy_data: dict) -> Path:
    """Create temporary policy file with valid YAML content."""
    temp_dir = Path(tempfile.mkdtemp())
    policy_file = temp_dir / "test_policy.yaml"

    with open(policy_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(valid_policy_data, f, allow_unicode=True)

    return policy_file


@pytest.fixture
def policy_loader(mock_redis_client: AsyncMock, temp_policy_file: Path) -> PolicyLoaderImpl:
    """Create policy loader with mocked Redis and temporary file."""
    return PolicyLoaderImpl(
        redis_client=mock_redis_client,
        config_path=str(temp_policy_file),
        cache_ttl=300,
    )


class TestPolicyLoading:
    """Test policy loading behavior from YAML files."""

    async def test_load_policies_successful_load_and_cache(
        self,
        policy_loader: PolicyLoaderImpl,
        mock_redis_client: AsyncMock,
        valid_policy_data: dict,
    ) -> None:
        """Test successful policy loading stores correct data in cache."""
        result = await policy_loader.load_policies()

        # Verify policy structure matches expectations
        assert result.costs == valid_policy_data["costs"]
        assert result.rate_limits == valid_policy_data["rate_limits"]
        assert result.signup_bonuses == valid_policy_data["signup_bonuses"]
        assert result.cache_ttl == valid_policy_data["cache_ttl"]

        # Verify Redis caching behavior
        mock_redis_client.setex.assert_called_once()
        call_args = mock_redis_client.setex.call_args[0]
        assert call_args[0] == "entitlements:policies:v1"  # cache key
        assert call_args[1] == 300  # TTL
        cached_data = json.loads(call_args[2])
        assert cached_data["costs"]["grammatik_kontroll"] == 10
        assert cached_data["costs"]["språk_bedömning"] == 15

    async def test_load_policies_nonexistent_file_raises_error(
        self,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test loading from nonexistent file raises FileNotFoundError."""
        loader = PolicyLoaderImpl(
            redis_client=mock_redis_client, config_path="/nonexistent/path.yaml"
        )

        with pytest.raises(FileNotFoundError, match="Policy file not found"):
            await loader.load_policies()

        # Verify no caching attempt was made
        mock_redis_client.setex.assert_not_called()

    @pytest.mark.parametrize(
        "file_content",
        [
            "",  # Empty file
            "   ",  # Whitespace only
            "null",  # Null content
        ],
    )
    async def test_load_policies_empty_file_raises_error(
        self,
        mock_redis_client: AsyncMock,
        file_content: str,
    ) -> None:
        """Test loading empty or null policy files raises ValueError."""
        temp_dir = Path(tempfile.mkdtemp())
        policy_file = temp_dir / "empty_policy.yaml"

        with open(policy_file, "w", encoding="utf-8") as f:
            f.write(file_content)

        loader = PolicyLoaderImpl(redis_client=mock_redis_client, config_path=str(policy_file))

        with pytest.raises(ValueError, match="Policy file is empty or invalid"):
            await loader.load_policies()

    async def test_load_policies_malformed_yaml_raises_error(
        self,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test loading malformed YAML raises yaml.YAMLError."""
        temp_dir = Path(tempfile.mkdtemp())
        policy_file = temp_dir / "malformed_policy.yaml"

        with open(policy_file, "w", encoding="utf-8") as f:
            f.write("costs:\n  invalid: [unclosed list")

        loader = PolicyLoaderImpl(redis_client=mock_redis_client, config_path=str(policy_file))

        with pytest.raises(yaml.YAMLError):
            await loader.load_policies()

    async def test_load_policies_redis_cache_failure_continues_operation(
        self,
        policy_loader: PolicyLoaderImpl,
        mock_redis_client: AsyncMock,
        valid_policy_data: dict,
    ) -> None:
        """Test policy loading continues even when Redis caching fails."""
        mock_redis_client.setex.side_effect = Exception("Redis connection failed")

        result = await policy_loader.load_policies()

        # Policy should still be loaded correctly
        assert result.costs == valid_policy_data["costs"]
        assert result.rate_limits == valid_policy_data["rate_limits"]

        # Verify caching was attempted
        mock_redis_client.setex.assert_called_once()


class TestPolicyValidation:
    """Test policy structure validation behavior."""

    @pytest.mark.parametrize("missing_section", ["costs", "rate_limits", "signup_bonuses"])
    async def test_load_policies_missing_required_sections_raises_error(
        self,
        mock_redis_client: AsyncMock,
        valid_policy_data: dict,
        missing_section: str,
    ) -> None:
        """Test validation fails when required policy sections are missing."""
        # Remove the required section
        invalid_data = valid_policy_data.copy()
        del invalid_data[missing_section]

        temp_dir = Path(tempfile.mkdtemp())
        policy_file = temp_dir / "invalid_policy.yaml"

        with open(policy_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(invalid_data, f)

        loader = PolicyLoaderImpl(redis_client=mock_redis_client, config_path=str(policy_file))

        with pytest.raises(ValueError, match=f"Missing required policy section: {missing_section}"):
            await loader.load_policies()

    @pytest.mark.parametrize(
        "section,invalid_value",
        [
            ("costs", "not_a_dict"),
            ("rate_limits", ["list", "instead", "of", "dict"]),
            ("signup_bonuses", 12345),
        ],
    )
    async def test_load_policies_invalid_section_types_raises_error(
        self,
        mock_redis_client: AsyncMock,
        valid_policy_data: dict,
        section: str,
        invalid_value: object,
    ) -> None:
        """Test validation fails when policy sections have wrong types."""
        invalid_data = valid_policy_data.copy()
        invalid_data[section] = invalid_value

        temp_dir = Path(tempfile.mkdtemp())
        policy_file = temp_dir / "invalid_policy.yaml"

        with open(policy_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(invalid_data, f)

        loader = PolicyLoaderImpl(redis_client=mock_redis_client, config_path=str(policy_file))

        with pytest.raises(ValueError, match=f"Policy section '{section}' must be a dictionary"):
            await loader.load_policies()

    @pytest.mark.parametrize(
        "metric,cost",
        [
            ("negative_cost", -5),
            ("float_cost", 12.5),
            ("string_cost", "ten"),
        ],
    )
    async def test_load_policies_invalid_costs_raises_error(
        self,
        mock_redis_client: AsyncMock,
        valid_policy_data: dict,
        metric: str,
        cost: object,
    ) -> None:
        """Test validation fails for invalid cost values."""
        invalid_data = valid_policy_data.copy()
        invalid_data["costs"][metric] = cost

        temp_dir = Path(tempfile.mkdtemp())
        policy_file = temp_dir / "invalid_policy.yaml"

        with open(policy_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(invalid_data, f)

        loader = PolicyLoaderImpl(redis_client=mock_redis_client, config_path=str(policy_file))

        with pytest.raises(
            ValueError, match=f"Invalid cost for {metric}: must be non-negative integer"
        ):
            await loader.load_policies()


class TestRedisCachingBehavior:
    """Test Redis caching behavior patterns."""

    async def test_get_cached_policies_cache_hit_returns_cached_data(
        self,
        policy_loader: PolicyLoaderImpl,
        mock_redis_client: AsyncMock,
        valid_policy_data: dict,
    ) -> None:
        """Test cache hit returns properly deserialized cached policy data."""
        # Mock Redis returning cached data
        cached_policy = PolicyConfig(**valid_policy_data)
        mock_redis_client.get.return_value = json.dumps(cached_policy.model_dump())

        result = await policy_loader._get_cached_policies()

        # Verify correct cache key usage
        mock_redis_client.get.assert_called_once_with("entitlements:policies:v1")

        # Verify returned data matches cached policy
        assert result.costs == valid_policy_data["costs"]
        assert result.rate_limits == valid_policy_data["rate_limits"]
        assert result.signup_bonuses == valid_policy_data["signup_bonuses"]

    async def test_get_cached_policies_cache_miss_loads_from_file(
        self,
        policy_loader: PolicyLoaderImpl,
        mock_redis_client: AsyncMock,
        valid_policy_data: dict,
    ) -> None:
        """Test cache miss triggers file loading and caches result."""
        # Mock Redis cache miss
        mock_redis_client.get.return_value = None

        result = await policy_loader._get_cached_policies()

        # Verify cache lookup was attempted
        mock_redis_client.get.assert_called_once_with("entitlements:policies:v1")

        # Verify new policy was cached
        mock_redis_client.setex.assert_called_once()

        # Verify loaded data is correct
        assert result.costs["grammatik_kontroll"] == 10
        assert result.costs["språk_bedömning"] == 15

    async def test_get_cached_policies_redis_error_fallback_to_file(
        self,
        policy_loader: PolicyLoaderImpl,
        mock_redis_client: AsyncMock,
        valid_policy_data: dict,
    ) -> None:
        """Test Redis errors gracefully fallback to file loading."""
        # Mock Redis get operation failure
        mock_redis_client.get.side_effect = Exception("Redis connection failed")

        result = await policy_loader._get_cached_policies()

        # Verify fallback behavior loaded from file
        assert result.costs == valid_policy_data["costs"]
        assert result.rate_limits == valid_policy_data["rate_limits"]

    async def test_reload_policies_clears_cache_and_reloads(
        self,
        policy_loader: PolicyLoaderImpl,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test reload operation clears cache before loading fresh data."""
        await policy_loader.reload_policies()

        # Verify cache was cleared
        mock_redis_client.delete.assert_called_once_with("entitlements:policies:v1")

        # Verify new data was cached
        mock_redis_client.setex.assert_called_once()

    async def test_reload_policies_continues_despite_cache_clear_failure(
        self,
        policy_loader: PolicyLoaderImpl,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test reload continues operation even if cache clearing fails."""
        mock_redis_client.delete.side_effect = Exception("Redis delete failed")

        await policy_loader.reload_policies()

        # Verify delete was attempted
        mock_redis_client.delete.assert_called_once()

        # Verify new policy was still cached despite clear failure
        mock_redis_client.setex.assert_called_once()


class TestCostCalculations:
    """Test cost calculation behavior with Swedish metric names."""

    @pytest.mark.parametrize(
        "metric,expected_cost",
        [
            ("grammatik_kontroll", 10),
            ("språk_bedömning", 15),
            ("rätt_stavning", 5),
            ("basic_spell_check", 2),
            ("advanced_analysis", 25),
            ("nonexistent_metric", 0),  # Default for unknown metrics
        ],
    )
    async def test_get_cost_returns_correct_values(
        self,
        policy_loader: PolicyLoaderImpl,
        mock_redis_client: AsyncMock,
        valid_policy_data: dict,
        metric: str,
        expected_cost: int,
    ) -> None:
        """Test cost retrieval returns correct values for various metrics."""
        # Mock cached policy data
        cached_policy = PolicyConfig(**valid_policy_data)
        mock_redis_client.get.return_value = json.dumps(cached_policy.model_dump())

        result = await policy_loader.get_cost(metric)

        assert result == expected_cost

    async def test_get_cost_with_cache_miss_loads_from_file(
        self,
        policy_loader: PolicyLoaderImpl,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test cost calculation triggers policy loading on cache miss."""
        # Mock cache miss
        mock_redis_client.get.return_value = None

        result = await policy_loader.get_cost("grammatik_kontroll")

        # Verify cache lookup and file loading
        mock_redis_client.get.assert_called_once()
        mock_redis_client.setex.assert_called_once()

        # Verify correct cost returned
        assert result == 10


class TestRateLimitParsing:
    """Test rate limit configuration parsing behavior."""

    @pytest.mark.parametrize(
        "limit_str,expected_result",
        [
            ("100/hour", (100, 3600)),
            ("50/day", (50, 86400)),
            ("10/week", (10, 604800)),
            ("5/month", (5, 2592000)),
            ("unlimited", (0, 0)),
        ],
    )
    async def test_get_rate_limit_parses_valid_formats(
        self,
        policy_loader: PolicyLoaderImpl,
        mock_redis_client: AsyncMock,
        valid_policy_data: dict,
        limit_str: str,
        expected_result: tuple[int, int],
    ) -> None:
        """Test rate limit parsing handles all valid format variations."""
        # Update test data with specific rate limit
        test_data = valid_policy_data.copy()
        test_data["rate_limits"]["test_metric"] = limit_str

        cached_policy = PolicyConfig(**test_data)
        mock_redis_client.get.return_value = json.dumps(cached_policy.model_dump())

        result = await policy_loader.get_rate_limit("test_metric")

        assert result == expected_result

    @pytest.mark.parametrize(
        "invalid_limit",
        [
            "100",  # Missing slash
            "100/",  # Missing period
            "/hour",  # Missing count
            "abc/hour",  # Non-numeric count
            "100/invalid_period",  # Invalid time period
        ],
    )
    async def test_get_rate_limit_invalid_formats_raise_error(
        self,
        policy_loader: PolicyLoaderImpl,
        mock_redis_client: AsyncMock,
        valid_policy_data: dict,
        invalid_limit: str,
    ) -> None:
        """Test invalid rate limit formats raise ValueError with descriptive message."""
        # Update test data with invalid rate limit
        test_data = valid_policy_data.copy()
        test_data["rate_limits"]["test_metric"] = invalid_limit

        cached_policy = PolicyConfig(**test_data)
        mock_redis_client.get.return_value = json.dumps(cached_policy.model_dump())

        with pytest.raises(ValueError, match="Invalid rate limit format for test_metric"):
            await policy_loader.get_rate_limit("test_metric")

    async def test_get_rate_limit_missing_metric_returns_unlimited(
        self,
        policy_loader: PolicyLoaderImpl,
        mock_redis_client: AsyncMock,
        valid_policy_data: dict,
    ) -> None:
        """Test missing metrics default to unlimited rate limiting."""
        cached_policy = PolicyConfig(**valid_policy_data)
        mock_redis_client.get.return_value = json.dumps(cached_policy.model_dump())

        result = await policy_loader.get_rate_limit("nonexistent_metric")

        assert result == (0, 0)  # Unlimited
