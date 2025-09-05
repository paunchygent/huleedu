"""
Distributed State Management for Testing

Utilities for managing Redis and Kafka state between test runs to prevent
idempotency collisions and ensure clean test environments.
"""

import asyncio
import subprocess
import time
from typing import Any, Dict, List, Optional

import aiohttp
from huleedu_service_libs.logging_utils import create_service_logger

from .service_discovery import ServiceDiscovery

logger = create_service_logger("test.distributed_state")


class DistributedStateManager:
    """Manages Redis and Kafka state for clean test execution."""

    def __init__(self) -> None:
        self.redis_container = "huleedu_redis"
        self.kafka_container = "huleedu_kafka"
        self._discovery = ServiceDiscovery()
        self._endpoints: Dict[str, str] = {}

    async def _wait_for_services_idle(self, timeout_seconds: int = 10) -> bool:
        """
        Wait for all services to be in idle state (not actively processing events).

        Uses dynamically discovered service endpoints to check processing status.
        Returns True if all services are idle, False if timeout.
        """
        # Discover endpoints if not already done
        if not self._endpoints:
            self._endpoints = self._discovery.discover_endpoints()
            logger.info(f"Discovered {len(self._endpoints)} service endpoints")

        start_time = time.time()

        while (time.time() - start_time) < timeout_seconds:
            idle_services = []

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                for service_name, health_url in self._endpoints.items():
                    try:
                        async with session.get(health_url) as response:
                            if response.status == 200:
                                health_data = await response.json()

                                # Check if service reports being idle
                                # Most services report active processing in health endpoint
                                processing_active = health_data.get("processing_active", False)
                                active_consumers = health_data.get("active_consumers", 0)

                                if not processing_active and active_consumers == 0:
                                    idle_services.append(service_name)
                                else:
                                    logger.debug(
                                        f"Service {service_name} still active: "
                                        f"processing={processing_active}, "
                                        f"consumers={active_consumers}"
                                    )
                            else:
                                logger.debug(
                                    f"Service {service_name} health check failed: {response.status}"
                                )

                    except Exception as e:
                        logger.debug(f"Could not check {service_name} health: {e}")
                        # Assume service is idle if we can't reach it (might be stopped)
                        idle_services.append(service_name)

            if len(idle_services) == len(self._endpoints):
                logger.info("✅ All services are idle, proceeding with cleanup")
                return True

            # Brief delay before rechecking (much shorter than sleep anti-pattern)
            await asyncio.sleep(0.1)

        active_services = set(self._endpoints.keys()) - set(idle_services)
        logger.warning(f"⚠️ Timeout waiting for services to be idle. Active: {active_services}")
        return False

    async def _smart_redis_cleanup(self) -> int:
        """
        Perform targeted Redis cleanup using TTL and pattern-based deletion.

        Instead of FLUSHALL, this targets specific test-related key patterns:
        - Idempotency keys: huleedu:idempotency:v2:*
        - Outbox keys: outbox:*
        - Batch tracking: batch:*
        - Test keys: test:*

        Returns number of keys cleared.
        """
        try:
            total_keys_cleared = 0

            # Define key patterns that need cleanup for test isolation
            cleanup_patterns = [
                "huleedu:idempotency:v2:*",  # Event idempotency keys
                "outbox:*",                  # Outbox relay keys
                "batch:*",                   # Batch tracking keys
                "test:*",                    # Explicit test keys
                "correlation:*",             # Correlation tracking
                "pipeline:*",                # Pipeline state keys
                "essay:*",                   # Essay processing keys
                "bcs:essay_state:*",         # BCS essay state tracking keys
            ]

            for pattern in cleanup_patterns:
                keys_cleared = await self._delete_keys_by_pattern(pattern)
                total_keys_cleared += keys_cleared
                if keys_cleared > 0:
                    logger.info(f"🗑️ Cleared {keys_cleared} keys matching pattern: {pattern}")

            if total_keys_cleared > 0:
                logger.info(f"✅ Smart Redis cleanup completed: {total_keys_cleared} keys cleared")
            else:
                logger.info("✅ Redis was already clean (no test keys found)")

            return total_keys_cleared

        except Exception as e:
            logger.warning(f"⚠️ Smart Redis cleanup failed, falling back to FLUSHALL: {e}")
            # Fallback to original FLUSHALL if smart cleanup fails
            return await self._atomic_redis_flushall()

    async def _delete_keys_by_pattern(self, pattern: str) -> int:
        """Delete all keys matching a specific pattern."""
        try:
            # Get keys matching pattern
            keys_cmd = ["docker", "exec", self.redis_container, "redis-cli", "KEYS", pattern]
            keys_result = subprocess.run(keys_cmd, capture_output=True, text=True, check=True)

            if not keys_result.stdout.strip():
                return 0

            keys = keys_result.stdout.strip().split("\n")
            keys = [k for k in keys if k]  # Filter out empty strings

            if not keys:
                return 0

            # Delete keys in batches to avoid command line length limits
            batch_size = 100
            keys_deleted = 0

            for i in range(0, len(keys), batch_size):
                batch = keys[i:i + batch_size]
                del_cmd = ["docker", "exec", self.redis_container, "redis-cli", "DEL"] + batch

                del_result = subprocess.run(del_cmd, capture_output=True, text=True, check=True)
                keys_deleted += int(del_result.stdout.strip())

            return keys_deleted

        except subprocess.CalledProcessError as e:
            logger.warning(f"⚠️ Failed to delete keys for pattern {pattern}: {e.stderr}")
            return 0
        except Exception as e:
            logger.warning(f"⚠️ Unexpected error deleting keys for pattern {pattern}: {e}")
            return 0

    async def _atomic_redis_flushall(self) -> int:
        """
        Fallback: Perform complete Redis cleanup using FLUSHALL.

        Only used when smart cleanup fails.
        """
        try:
            # First, count existing keys for reporting
            count_cmd = ["docker", "exec", self.redis_container, "redis-cli", "DBSIZE"]
            count_result = subprocess.run(count_cmd, capture_output=True, text=True, check=True)
            key_count_before = int(count_result.stdout.strip())

            # Perform complete flush
            flush_cmd = ["docker", "exec", self.redis_container, "redis-cli", "FLUSHALL"]
            flush_result = subprocess.run(flush_cmd, capture_output=True, text=True, check=True)

            if "OK" not in flush_result.stdout:
                raise RuntimeError(f"FLUSHALL command failed: {flush_result.stdout}")

            logger.warning(f"⚠️ Used FLUSHALL fallback: {key_count_before} keys cleared")
            return key_count_before

        except subprocess.CalledProcessError as e:
            logger.warning(f"⚠️ Failed Redis FLUSHALL cleanup: {e.stderr}")
            raise
        except Exception as e:
            logger.warning(f"⚠️ Unexpected error in Redis cleanup: {e}")
            raise

    async def quick_redis_cleanup(self, patterns: Optional[List[str]] = None) -> int:
        """
        Quick Redis cleanup without service checks or retry logic.

        Performs direct pattern-based cleanup in <1 second for fast test execution.

        Args:
            patterns: Optional list of Redis key patterns to clean.
                     If None, uses default cleanup patterns.

        Returns:
            Number of keys cleared
        """
        try:
            if patterns is None:
                # Use the same patterns as _smart_redis_cleanup but without service coordination
                patterns = [
                    "huleedu:idempotency:v2:*",  # Event idempotency keys
                    "outbox:*",                  # Outbox relay keys
                    "batch:*",                   # Batch tracking keys
                    "test:*",                    # Explicit test keys
                    "correlation:*",             # Correlation tracking
                    "pipeline:*",                # Pipeline state keys
                    "essay:*",                   # Essay processing keys
                    "bcs:essay_state:*",         # BCS essay state tracking keys
                ]

            total_keys_cleared = 0

            for pattern in patterns:
                keys_cleared = await self._delete_keys_by_pattern(pattern)
                total_keys_cleared += keys_cleared
                if keys_cleared > 0:
                    logger.info(f"🗑️ Quick cleanup: {keys_cleared} keys matching {pattern}")

            if total_keys_cleared > 0:
                logger.info(f"✅ Quick Redis cleanup completed: {total_keys_cleared} keys cleared")

            return total_keys_cleared

        except Exception as e:
            logger.warning(f"⚠️ Quick Redis cleanup failed: {e}")
            raise

    async def cleanup_for_test(
        self,
        test_name: str,
        patterns: Optional[List[str]] = None,
        consumer_groups: Optional[List[str]] = None
    ) -> dict[str, Any]:
        """
        Targeted cleanup for specific test needs without over-engineering.

        Args:
            test_name: Name of the test for logging
            patterns: Specific Redis patterns to clean (defaults to all)
            consumer_groups: Specific Kafka consumer groups to reset (defaults to none)

        Returns:
            Cleanup results with counts and timing
        """
        logger.info(f"🧹 Targeted cleanup for test: {test_name}")
        start_time = time.time()

        # Redis cleanup
        redis_keys_cleared = await self.quick_redis_cleanup(patterns)

        # Kafka cleanup (only if specified)
        kafka_groups_reset = 0
        if consumer_groups:
            for group in consumer_groups:
                try:
                    reset_cmd = [
                        "docker", "exec", self.kafka_container,
                        "kafka-consumer-groups.sh", "--bootstrap-server", "localhost:9092",
                        "--group", group, "--reset-offsets", "--to-latest",
                        "--all-topics", "--execute"
                    ]
                    result = subprocess.run(reset_cmd, capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        kafka_groups_reset += 1
                        logger.info(f"🔄 Reset Kafka consumer group: {group}")
                except Exception as e:
                    logger.debug(f"Consumer group {group} reset failed: {e}")

        execution_time = time.time() - start_time

        results = {
            "test_name": test_name,
            "redis_keys_cleared": redis_keys_cleared,
            "kafka_groups_reset": kafka_groups_reset,
            "execution_time_seconds": execution_time,
            "clean": redis_keys_cleared >= 0  # Success if no errors
        }

        logger.info(
            f"✅ Targeted cleanup complete for {test_name}: "
            f"{redis_keys_cleared} keys, {kafka_groups_reset} groups in {execution_time:.2f}s"
        )

        return results

    async def minimal_cleanup(self) -> int:
        """
        Minimal cleanup for tests with proper isolation.
        Only clears idempotency keys that could cause test interference.

        Returns:
            Number of idempotency keys cleared
        """
        idempotency_patterns = ["huleedu:idempotency:v2:*"]
        return await self.quick_redis_cleanup(idempotency_patterns)

    async def ensure_clean_test_environment(
        self, test_name: str, clear_redis: bool = True, reset_kafka_offsets: bool = True
    ) -> None:
        """
        Ensure clean distributed system state using proper coordination.

        Uses dynamically discovered service endpoints to coordinate cleanup.

        Args:
            test_name: Name of the test for logging
            clear_redis: Whether to clear Redis idempotency keys
            reset_kafka_offsets: Whether to reset Kafka consumer offsets
        """
        logger.info(f"🧹 Coordinated cleanup starting for test: {test_name}")

        # Discover endpoints if not already done
        if not self._endpoints:
            self._endpoints = self._discovery.discover_endpoints()
            logger.info(f"Discovered {len(self._endpoints)} service endpoints")

        if clear_redis:
            # Step 1: Wait for services to be idle (no sleep anti-pattern)
            services_idle = await self._wait_for_services_idle(timeout_seconds=15)
            if not services_idle:
                logger.warning("⚠️ Proceeding with cleanup despite active services")

            # Step 2: Smart Redis cleanup (pattern-based, no race conditions)
            await self._smart_redis_cleanup()

        if reset_kafka_offsets:
            await self._reset_kafka_consumer_offsets()

        logger.info(f"✅ Coordinated cleanup completed for test: {test_name}")

    async def _reset_kafka_consumer_offsets(self) -> None:
        """Reset Kafka consumer offsets to skip old events from previous test runs.

        CRITICAL: We reset to 'latest' not 'earliest' because:
        - Old events in Kafka have event_ids from previous test runs
        - With proper idempotency (including event_id in hash), these would be rejected
        - Tests should only process NEW events generated during the current test run
        """
        try:
            # List of consumer groups to reset - ALL services
            consumer_groups = [
                "essay-lifecycle-service-group-v1.0",
                "result-aggregator-service-group-v1.0",
                "spellchecker-service-group-v1.1",
                "cj-assessment-service-group-v1.0",
                "batch-orchestrator-service-group-v1.0",
                "nlp-service-group-v1.0",
                "class-management-service-group-v1.0",
                "batch-conductor-service-group-v1.0",
                "file-service-group-v1.0",
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
        Validate that distributed system state is clean of test-related keys.

        Since we use smart pattern-based cleanup, we check for remaining keys
        and specifically flag test-critical patterns like idempotency keys.

        Returns:
            Dict with validation results for debugging
        """
        validation = {
            "redis_total_keys": 0,
            "redis_sample_keys": [],
            "kafka_consumer_groups": [],
            "clean": True,
            "verification_timestamp": time.time(),
        }

        try:
            # Check total Redis key count
            count_cmd = ["docker", "exec", self.redis_container, "redis-cli", "DBSIZE"]
            count_result = subprocess.run(count_cmd, capture_output=True, text=True, check=True)
            key_count = int(count_result.stdout.strip())
            validation["redis_total_keys"] = key_count

            if key_count > 0:
                validation["clean"] = False

                # Get sample keys for debugging
                keys_cmd = ["docker", "exec", self.redis_container, "redis-cli", "KEYS", "*"]
                keys_result = subprocess.run(keys_cmd, capture_output=True, text=True, check=True)

                if keys_result.stdout.strip():
                    all_keys = keys_result.stdout.strip().split("\n")
                    validation["redis_sample_keys"] = all_keys[:5]  # First 5 keys for debugging

                    logger.warning(
                        f"⚠️ Redis not clean: {key_count} keys found. "
                        f"Sample keys: {validation['redis_sample_keys']}"
                    )

                    # Specifically check for idempotency keys that cause the test issue
                    idempotency_keys = [k for k in all_keys if "idempotency" in k]
                    if idempotency_keys:
                        logger.warning(
                            f"🚨 Found {len(idempotency_keys)} idempotency keys that will "
                            f"cause test failures!"
                        )
                else:
                    logger.info("✅ Redis is clean (0 keys)")

        except Exception as e:
            logger.warning(f"⚠️ Could not validate Redis state: {e}")
            validation["clean"] = False

        return validation

    async def ensure_verified_clean_state(self, test_name: str) -> dict[str, Any]:
        """
        Ensure clean state with proper service coordination and verification.

        Eliminates sleep() anti-patterns by using deterministic service coordination.

        Returns:
            Validation results after ensuring clean state
        """
        max_attempts = 3  # Reduced attempts - proper coordination should work on first try

        for attempt in range(max_attempts):
            logger.info(
                f"🧹 Coordinated cleanup attempt {attempt + 1}/{max_attempts} for test: {test_name}"
            )

            # Step 1: Ensure services are idle before cleanup
            services_idle = await self._wait_for_services_idle(timeout_seconds=20)
            if not services_idle:
                logger.warning("⚠️ Services not idle, proceeding with cleanup anyway")

            # Step 2: Perform atomic cleanup with proper coordination
            await self.ensure_clean_test_environment(test_name)

            # Step 3: Immediate verification (no artificial delays)
            validation = await self.validate_clean_state()

            if validation["clean"]:
                logger.info(
                    f"✅ Verified clean state achieved for test: {test_name} "
                    f"(attempt {attempt + 1}) - coordinated cleanup successful"
                )
                return validation
            else:
                key_count = validation.get("redis_total_keys", 0)
                sample_keys = validation.get("redis_sample_keys", [])
                logger.warning(
                    f"⚠️ State not clean after coordinated attempt {attempt + 1}: "
                    f"found {key_count} Redis keys, samples: {sample_keys[:3]}"
                )

                # If cleanup failed, wait for services to settle before retry
                if attempt < max_attempts - 1:
                    logger.info("🔄 Waiting for services to settle before retry...")
                    await self._wait_for_services_idle(timeout_seconds=10)

        # Final attempt failed - provide detailed error info
        key_count = validation.get("redis_total_keys", 0)
        sample_keys = validation.get("redis_sample_keys", [])

        # Check specifically for idempotency keys that cause test failures
        idempotency_samples = [k for k in sample_keys if "idempotency" in k]
        idempotency_warning = (
            f" ({len(idempotency_samples)} idempotency keys found!)" if idempotency_samples else ""
        )

        raise RuntimeError(
            f"Failed to achieve clean state after {max_attempts} coordinated attempts: "
            f"found {key_count} Redis keys remaining{idempotency_warning}. "
            f"Sample keys: {sample_keys[:5]}. "
            f"This suggests services are continuously creating state keys "
            f"even when reporting idle status, or Docker services are not running properly. "
            f"Try manually running: docker exec huleedu_redis redis-cli FLUSHALL"
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
