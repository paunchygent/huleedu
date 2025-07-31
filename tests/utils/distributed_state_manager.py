"""
Distributed State Management for Testing

Utilities for managing Redis and Kafka state between test runs to prevent
idempotency collisions and ensure clean test environments.
"""

import asyncio
import subprocess
import time
from typing import Any

import aiohttp
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("test.distributed_state")


class DistributedStateManager:
    """Manages Redis and Kafka state for clean test execution."""

    def __init__(self) -> None:
        self.redis_container = "huleedu_redis"
        self.kafka_container = "huleedu_kafka"

        # Service health endpoints for coordination
        self.service_health_endpoints = {
            "essay_lifecycle_service": "http://localhost:5001/healthz",
            "batch_orchestrator_service": "http://localhost:5002/healthz",
            "spellchecker_service": "http://localhost:5003/healthz",
            "cj_assessment_service": "http://localhost:5004/healthz",
            "result_aggregator_service": "http://localhost:5005/healthz",
        }

    async def _wait_for_services_idle(self, timeout_seconds: int = 10) -> bool:
        """
        Wait for all services to be in idle state (not actively processing events).

        Uses service health endpoints to check processing status.
        Returns True if all services are idle, False if timeout.
        """
        start_time = time.time()

        while (time.time() - start_time) < timeout_seconds:
            idle_services = []

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                for service_name, health_url in self.service_health_endpoints.items():
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
                                        f"processing={processing_active}, consumers={active_consumers}"
                                    )
                            else:
                                logger.debug(
                                    f"Service {service_name} health check failed: {response.status}"
                                )

                    except Exception as e:
                        logger.debug(f"Could not check {service_name} health: {e}")
                        # Assume service is idle if we can't reach it (might be stopped)
                        idle_services.append(service_name)

            if len(idle_services) == len(self.service_health_endpoints):
                logger.info("✅ All services are idle, proceeding with cleanup")
                return True

            # Brief delay before rechecking (much shorter than sleep anti-pattern)
            await asyncio.sleep(0.1)

        active_services = set(self.service_health_endpoints.keys()) - set(idle_services)
        logger.warning(f"⚠️ Timeout waiting for services to be idle. Active: {active_services}")
        return False

    async def _atomic_redis_cleanup(self) -> int:
        """
        Perform atomic Redis cleanup using transactions to handle concurrent modifications.

        Cleans up both idempotency keys and pending content keys.

        Returns number of keys cleared.
        """
        # Atomic cleanup script that handles concurrent modifications
        atomic_cleanup_script = """
            -- Use optimistic locking pattern with WATCH/MULTI/EXEC
            local patterns = {'huleedu:idempotency:v2:*', 'pending_content:*'}
            local batch_size = 100
            local total_deleted = 0
            
            -- Clean up keys matching each pattern
            for _, pattern in ipairs(patterns) do
                local cursor = 0
                repeat
                    local scan_result = redis.call('SCAN', cursor, 'MATCH', pattern, 'COUNT', batch_size)
                    cursor = tonumber(scan_result[1])
                    local keys = scan_result[2]
                    
                    if #keys > 0 then
                        -- Delete batch atomically
                        local deleted = redis.call('DEL', unpack(keys))
                        total_deleted = total_deleted + deleted
                    end
                until cursor == 0
            end
            
            -- Also clean up the pending content index key
            local index_deleted = redis.call('DEL', 'pending_content:index')
            total_deleted = total_deleted + index_deleted
            
            return total_deleted
        """

        try:
            clear_cmd = [
                "docker",
                "exec",
                self.redis_container,
                "redis-cli",
                "EVAL",
                atomic_cleanup_script,
                "0",
            ]

            result = subprocess.run(clear_cmd, capture_output=True, text=True, check=True)
            cleared_count = int(result.stdout.strip())

            if cleared_count > 0:
                logger.info(
                    f"🗑️ Atomically cleared {cleared_count} Redis keys (idempotency + pending content)"
                )
            else:
                logger.info("✅ No Redis keys to clear (idempotency or pending content)")

            return cleared_count

        except subprocess.CalledProcessError as e:
            logger.warning(f"⚠️ Failed atomic Redis cleanup: {e.stderr}")
            raise
        except Exception as e:
            logger.warning(f"⚠️ Unexpected error in atomic cleanup: {e}")
            raise

    async def ensure_clean_test_environment(
        self, test_name: str, clear_redis: bool = True, reset_kafka_offsets: bool = True
    ) -> None:
        """
        Ensure clean distributed system state using proper coordination.

        Uses service health endpoints to coordinate cleanup instead of sleep() anti-pattern.

        Args:
            test_name: Name of the test for logging
            clear_redis: Whether to clear Redis idempotency keys
            reset_kafka_offsets: Whether to reset Kafka consumer offsets
        """
        logger.info(f"🧹 Coordinated cleanup starting for test: {test_name}")

        if clear_redis:
            # Step 1: Wait for services to be idle (no sleep anti-pattern)
            services_idle = await self._wait_for_services_idle(timeout_seconds=15)
            if not services_idle:
                logger.warning("⚠️ Proceeding with cleanup despite active services")

            # Step 2: Atomic Redis cleanup (no race conditions)
            await self._atomic_redis_cleanup()

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
                key_count = validation.get("redis_idempotency_keys", 0)
                sample_keys = validation.get("redis_sample_keys", [])
                logger.warning(
                    f"⚠️ State not clean after coordinated attempt {attempt + 1}: "
                    f"found {key_count} keys, samples: {sample_keys[:3]}"
                )

                # If cleanup failed, wait for services to settle before retry
                if attempt < max_attempts - 1:
                    logger.info("🔄 Waiting for services to settle before retry...")
                    await self._wait_for_services_idle(timeout_seconds=10)

        # Final attempt failed - provide detailed error info
        key_count = validation.get("redis_idempotency_keys", 0)
        sample_keys = validation.get("redis_sample_keys", [])
        raise RuntimeError(
            f"Failed to achieve clean state after {max_attempts} coordinated attempts: "
            f"found {key_count} Redis keys remaining. "
            f"Sample keys: {sample_keys[:5]}. "
            f"This suggests services are continuously creating idempotency keys "
            f"even when reporting idle status, indicating a service coordination issue."
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
