"""
Distributed State Management for Testing

Utilities for managing Redis and Kafka state between test runs to prevent
idempotency collisions and ensure clean test environments.
"""

import asyncio
import subprocess
import time
from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("test.distributed_state")


class DistributedStateManager:
    """Manages Redis and Kafka state for clean test execution."""

    def __init__(self) -> None:
        self.redis_container = "huleedu_redis"
        self.kafka_container = "huleedu_kafka"

    async def ensure_clean_test_environment(
        self, test_name: str, clear_redis: bool = True, reset_kafka_offsets: bool = True
    ) -> None:
        """
        Ensure clean distributed system state before test execution.

        This prevents idempotency collisions and state pollution between test runs.

        Args:
            test_name: Name of the test for logging
            clear_redis: Whether to clear Redis idempotency keys
            reset_kafka_offsets: Whether to reset Kafka consumer offsets
        """
        logger.info(f"🧹 Cleaning distributed state for test: {test_name}")

        if clear_redis:
            await self._clear_redis_idempotency_keys()

        if reset_kafka_offsets:
            await self._reset_kafka_consumer_offsets()

        logger.info(f"✅ Clean state established for test: {test_name}")

    async def _clear_redis_idempotency_keys(self) -> None:
        """Clear all Redis idempotency keys that could cause event skipping."""
        try:
            # Get count of existing keys
            count_cmd = [
                "docker",
                "exec",
                self.redis_container,
                "redis-cli",
                "EVAL",
                "return #redis.call('keys', 'huleedu:events:seen:*')",
                "0",
            ]
            result = subprocess.run(count_cmd, capture_output=True, text=True, check=True)
            key_count = int(result.stdout.strip())

            if key_count > 0:
                # Clear all idempotency keys
                clear_cmd = [
                    "docker",
                    "exec",
                    self.redis_container,
                    "redis-cli",
                    "EVAL",
                    (
                        "local keys = redis.call('keys', 'huleedu:events:seen:*') "
                        "for i=1,#keys do redis.call('del', keys[i]) end return #keys"
                    ),
                    "0",
                ]
                result = subprocess.run(clear_cmd, capture_output=True, text=True, check=True)
                cleared_count = int(result.stdout.strip())
                logger.info(f"🗑️ Cleared {cleared_count} Redis idempotency keys")
            else:
                logger.info("✅ No Redis idempotency keys to clear")

        except subprocess.CalledProcessError as e:
            logger.warning(f"⚠️ Failed to clear Redis keys: {e.stderr}")
        except Exception as e:
            logger.warning(f"⚠️ Unexpected error clearing Redis: {e}")

    async def _reset_kafka_consumer_offsets(self) -> None:
        """Reset Kafka consumer offsets to skip old events from previous test runs.

        CRITICAL: We reset to 'latest' not 'earliest' because:
        - Old events in Kafka have event_ids from previous test runs
        - With proper idempotency (including event_id in hash), these would be rejected
        - Tests should only process NEW events generated during the current test run
        """
        try:
            # List of consumer groups to reset
            consumer_groups = [
                "essay-lifecycle-service-group-v1.0",
                "result-aggregator-service-group-v1.0",
                "spellchecker-service-group-v1.1",
                "cj-assessment-service-group-v1.0",
            ]

            for group in consumer_groups:
                try:
                    # Reset to latest (skip old messages from previous runs)
                    reset_cmd = [
                        "docker",
                        "exec",
                        self.kafka_container,
                        "kafka-consumer-groups.sh",
                        "--bootstrap-server",
                        "localhost:9092",
                        "--group",
                        group,
                        "--reset-offsets",
                        "--to-latest",
                        "--all-topics",
                        "--execute",
                    ]

                    result = subprocess.run(reset_cmd, capture_output=True, text=True, timeout=10)

                    if result.returncode == 0:
                        logger.info(f"🔄 Reset Kafka consumer group: {group}")
                    else:
                        # Group might not exist yet - this is OK
                        logger.debug(f"🔄 Consumer group {group} reset skipped (may not exist yet)")

                except subprocess.TimeoutExpired:
                    logger.warning(f"⚠️ Timeout resetting consumer group: {group}")
                except Exception as e:
                    logger.debug(f"🔄 Consumer group {group} reset failed: {e}")

        except Exception as e:
            logger.warning(f"⚠️ Unexpected error resetting Kafka offsets: {e}")

    async def validate_clean_state(self) -> dict[str, Any]:
        """
        Validate that distributed system state is clean with comprehensive verification.

        Returns:
            Dict with validation results for debugging
        """
        validation = {
            "redis_idempotency_keys": 0,
            "redis_sample_keys": [],
            "kafka_consumer_groups": [],
            "clean": True,
            "verification_timestamp": time.time(),
        }

        try:
            # Comprehensive Redis validation using SCAN for reliability
            verification_script = """
            local pattern = 'huleedu:events:seen:*'
            local cursor = 0
            local total_count = 0
            local sample_keys = {}
            local max_samples = 5

            repeat
                local result = redis.call('SCAN', cursor, 'MATCH', pattern, 'COUNT', 100)
                cursor = tonumber(result[1])
                local keys = result[2]
                total_count = total_count + #keys

                -- Collect sample keys for debugging
                for i = 1, math.min(#keys, max_samples - #sample_keys) do
                    table.insert(sample_keys, keys[i])
                    if #sample_keys >= max_samples then break end
                end
            until cursor == 0 or #sample_keys >= max_samples

            return {total_count, sample_keys}
            """

            count_cmd = [
                "docker",
                "exec",
                self.redis_container,
                "redis-cli",
                "EVAL",
                verification_script,
                "0",
            ]
            result = subprocess.run(count_cmd, capture_output=True, text=True, check=True)

            # Parse Redis response
            output_lines = result.stdout.strip().split("\n")
            if len(output_lines) >= 1:
                validation["redis_idempotency_keys"] = int(output_lines[0])
                # Collect sample keys if present
                if len(output_lines) > 1:
                    validation["redis_sample_keys"] = output_lines[1:]

            key_count = validation["redis_idempotency_keys"]
            if isinstance(key_count, int) and key_count > 0:
                validation["clean"] = False
                sample_keys_raw = validation.get("redis_sample_keys", [])
                if isinstance(sample_keys_raw, list):
                    sample_keys = sample_keys_raw[:3]
                    sample_info = f" (samples: {sample_keys})" if sample_keys else ""
                else:
                    sample_info = ""
                logger.warning(f"⚠️ Found {key_count} Redis idempotency keys{sample_info}")

        except Exception as e:
            logger.warning(f"⚠️ Could not validate Redis state: {e}")
            validation["clean"] = False

        return validation

    async def ensure_verified_clean_state(self, test_name: str) -> dict[str, Any]:
        """
        Ensure clean state with post-cleaning verification and retry logic.

        Returns:
            Validation results after ensuring clean state
        """
        max_attempts = 3

        for attempt in range(max_attempts):
            # Clean the state
            await self.ensure_clean_test_environment(test_name)

            # Wait for propagation
            await asyncio.sleep(0.5)

            # Verify state is actually clean
            validation = await self.validate_clean_state()

            if validation["clean"]:
                logger.info(
                    f"✅ Verified clean state achieved for test: {test_name} "
                    f"(attempt {attempt + 1})"
                )
                return validation
            else:
                logger.warning(f"⚠️ State not clean after attempt {attempt + 1}: {validation}")
                if attempt < max_attempts - 1:
                    logger.info("🔄 Retrying state cleanup...")
                    await asyncio.sleep(1.0)

        # Final attempt failed
        raise RuntimeError(
            f"Failed to achieve clean state after {max_attempts} attempts: {validation}"
        )


# Global instance for test use
distributed_state_manager = DistributedStateManager()


async def ensure_clean_test_environment(test_name: str) -> None:
    """
    Convenience function for cleaning distributed state before tests.

    Usage in test functions:
        await ensure_clean_test_environment("test_comprehensive_pipeline")
    """
    await distributed_state_manager.ensure_clean_test_environment(test_name)


async def validate_clean_state() -> dict[str, Any]:
    """
    Convenience function for validating clean state.

    Returns:
        Validation results for debugging
    """
    return await distributed_state_manager.validate_clean_state()
