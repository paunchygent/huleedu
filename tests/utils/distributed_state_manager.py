"""
Distributed State Management for Testing

Utilities for managing Redis and Kafka state between test runs to prevent
idempotency collisions and ensure clean test environments.
"""

import asyncio
import subprocess
import time
from typing import Any, Dict

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

    async def _atomic_redis_cleanup(self) -> int:
        """
        Perform complete Redis cleanup using FLUSHALL to ensure test isolation.

        For tests, we need absolute certainty that no stale data remains,
        so we use FLUSHALL rather than pattern matching which can miss keys.

        Returns number of keys cleared (from DBSIZE before flush).
        """
        try:
            # First, count existing keys for reporting
            count_cmd = [
                "docker",
                "exec", 
                self.redis_container,
                "redis-cli",
                "DBSIZE"
            ]
            
            count_result = subprocess.run(count_cmd, capture_output=True, text=True, check=True)
            key_count_before = int(count_result.stdout.strip())

            # Perform complete flush
            flush_cmd = [
                "docker",
                "exec",
                self.redis_container, 
                "redis-cli",
                "FLUSHALL"
            ]

            flush_result = subprocess.run(flush_cmd, capture_output=True, text=True, check=True)
            
            if "OK" not in flush_result.stdout:
                raise RuntimeError(f"FLUSHALL command failed: {flush_result.stdout}")

            # Verify cleanup was successful
            verify_result = subprocess.run(count_cmd, capture_output=True, text=True, check=True)
            key_count_after = int(verify_result.stdout.strip())
            
            if key_count_after != 0:
                logger.warning(f"⚠️ Redis cleanup incomplete: {key_count_after} keys remain")
                return key_count_before
            
            if key_count_before > 0:
                logger.info(
                    f"🗑️ Completely flushed Redis: {key_count_before} keys cleared "
                    f"(idempotency, outbox, and all test state)"
                )
            else:
                logger.info("✅ Redis was already clean (0 keys)")

            return key_count_before

        except subprocess.CalledProcessError as e:
            logger.warning(f"⚠️ Failed Redis FLUSHALL cleanup: {e.stderr}")
            raise
        except Exception as e:
            logger.warning(f"⚠️ Unexpected error in Redis cleanup: {e}")
            raise

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
        Validate that distributed system state is completely clean.

        Since we use FLUSHALL for cleanup, we simply verify that Redis is empty
        and provide sample keys if any remain for debugging.

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
            count_cmd = [
                "docker",
                "exec",
                self.redis_container,
                "redis-cli",
                "DBSIZE"
            ]
            count_result = subprocess.run(count_cmd, capture_output=True, text=True, check=True)
            key_count = int(count_result.stdout.strip())
            validation["redis_total_keys"] = key_count

            if key_count > 0:
                validation["clean"] = False
                
                # Get sample keys for debugging
                keys_cmd = [
                    "docker",
                    "exec", 
                    self.redis_container,
                    "redis-cli",
                    "KEYS", "*"
                ]
                keys_result = subprocess.run(keys_cmd, capture_output=True, text=True, check=True)
                
                if keys_result.stdout.strip():
                    all_keys = keys_result.stdout.strip().split('\n')
                    validation["redis_sample_keys"] = all_keys[:5]  # First 5 keys for debugging
                    
                    logger.warning(
                        f"⚠️ Redis not clean: {key_count} keys found. "
                        f"Sample keys: {validation['redis_sample_keys']}"
                    )
                    
                    # Specifically check for idempotency keys that cause the test issue
                    idempotency_keys = [k for k in all_keys if "idempotency" in k]
                    if idempotency_keys:
                        logger.warning(
                            f"🚨 Found {len(idempotency_keys)} idempotency keys that will cause test failures!"
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
        idempotency_warning = f" ({len(idempotency_samples)} idempotency keys found!)" if idempotency_samples else ""
        
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
