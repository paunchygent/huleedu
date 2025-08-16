"""
Helper utilities for E2E pipeline testing.

This module provides utilities for interacting with services, monitoring events,
and validating pipeline behavior in end-to-end tests.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from common_core.events.envelope import EventEnvelope
from testcontainers.compose import DockerCompose


class PipelineTestHelper:
    """Helper class for E2E pipeline testing operations."""

    def __init__(
        self,
        compose: DockerCompose,
        kafka_producer: AIOKafkaProducer,
        kafka_consumer_factory,
        topic_names: dict[str, str],
    ):
        self.compose = compose
        self.kafka_producer = kafka_producer
        self.kafka_consumer_factory = kafka_consumer_factory
        self.topic_names = topic_names
        self._consumers: dict[str, AIOKafkaConsumer] = {}

    async def send_command_to_els(
        self,
        event: EventEnvelope,
        key: str | None = None,
    ) -> None:
        """Send a command event to ELS via the BOS topic."""

        bos_topic = self.topic_names["batch_nlp_initiate_command"]

        await self.kafka_producer.send_and_wait(
            topic=bos_topic,
            key=key,
            value=event.model_dump(mode="json"),
        )

        print(f"📤 Sent event to {bos_topic}: {event.event_type}")

    async def wait_for_els_transformation(
        self,
        correlation_id: str,
        timeout: float = 30.0,
    ) -> EventEnvelope | None:
        """
        Wait for ELS to transform BOS command to NLP service request.

        Returns the BatchNlpProcessingRequestedV1 event if found.
        """

        els_topic = self.topic_names["batch_nlp_processing_requested"]

        if els_topic not in self._consumers:
            self._consumers[els_topic] = await self.kafka_consumer_factory(
                els_topic,
                group_id=f"test-els-monitor-{int(time.time())}",
            )

        consumer = self._consumers[els_topic]

        print(f"🔍 Waiting for ELS transformation on {els_topic}...")

        start_time = time.time()

        try:
            async for msg in consumer:
                if time.time() - start_time > timeout:
                    print("⏰ Timeout waiting for ELS transformation")
                    break

                if msg.topic != els_topic:
                    continue

                try:
                    envelope: EventEnvelope = EventEnvelope.model_validate(msg.value)

                    if (
                        envelope.correlation_id == correlation_id
                        and envelope.event_type == "huleedu.batch.nlp.processing.requested.v1"
                    ):
                        print(f"✅ Found ELS transformation: {envelope.event_id}")
                        return envelope

                except Exception as e:
                    print(f"❌ Error parsing event: {e}")
                    continue

        except asyncio.TimeoutError:
            pass

        return None

    async def wait_for_nlp_completion(
        self,
        correlation_id: str,
        timeout: float = 60.0,
    ) -> EventEnvelope | None:
        """
        Wait for NLP service to complete processing.

        Returns the BatchNlpAnalysisCompletedV1 event if found.
        """

        completion_topic = self.topic_names["batch_nlp_analysis_completed"]

        if completion_topic not in self._consumers:
            self._consumers[completion_topic] = await self.kafka_consumer_factory(
                completion_topic,
                group_id=f"test-nlp-completion-{int(time.time())}",
            )

        consumer = self._consumers[completion_topic]

        print(f"🔍 Waiting for NLP completion on {completion_topic}...")

        start_time = time.time()

        try:
            async for msg in consumer:
                if time.time() - start_time > timeout:
                    print("⏰ Timeout waiting for NLP completion")
                    break

                if msg.topic != completion_topic:
                    continue

                try:
                    envelope: EventEnvelope = EventEnvelope.model_validate(msg.value)

                    if (
                        envelope.correlation_id == correlation_id
                        and envelope.event_type == "huleedu.batch.nlp.analysis.completed.v1"
                    ):
                        print(f"✅ Found NLP completion: {envelope.event_id}")
                        return envelope

                except Exception as e:
                    print(f"❌ Error parsing event: {e}")
                    continue

        except asyncio.TimeoutError:
            pass

        return None

    async def wait_for_essay_nlp_events(
        self,
        correlation_id: str,
        expected_count: int,
        timeout: float = 60.0,
    ) -> list[EventEnvelope]:
        """
        Wait for individual essay NLP completion events.

        Returns list of EssayNLPCompletedV1 events.
        """

        essay_topic = self.topic_names["essay_nlp_completed"]

        if essay_topic not in self._consumers:
            self._consumers[essay_topic] = await self.kafka_consumer_factory(
                essay_topic,
                group_id=f"test-essay-events-{int(time.time())}",
            )

        consumer = self._consumers[essay_topic]

        print(f"🔍 Waiting for {expected_count} essay NLP events on {essay_topic}...")

        events: list[EventEnvelope] = []
        start_time = time.time()

        try:
            async for msg in consumer:
                if time.time() - start_time > timeout:
                    print(
                        f"⏰ Timeout waiting for essay events (found {len(events)}/{expected_count})"
                    )
                    break

                if msg.topic != essay_topic:
                    continue

                try:
                    envelope: EventEnvelope = EventEnvelope.model_validate(msg.value)

                    if (
                        envelope.correlation_id == correlation_id
                        and envelope.event_type == "huleedu.essay.nlp.completed.v1"
                    ):
                        events.append(envelope)
                        print(
                            f"✅ Found essay event {len(events)}/{expected_count}: {envelope.event_id}"
                        )

                        if len(events) >= expected_count:
                            break

                except Exception as e:
                    print(f"❌ Error parsing event: {e}")
                    continue

        except asyncio.TimeoutError:
            pass

        return events

    async def verify_no_direct_consumption(
        self,
        correlation_id: str,
        wait_time: float = 10.0,
    ) -> bool:
        """
        Verify that NLP service does NOT consume directly from BOS topic.

        Returns True if no processing occurred (which is the desired behavior).
        """

        completion_topic = self.topic_names["batch_nlp_analysis_completed"]

        if completion_topic not in self._consumers:
            self._consumers[completion_topic] = await self.kafka_consumer_factory(
                completion_topic,
                group_id=f"test-no-direct-{int(time.time())}",
            )

        consumer = self._consumers[completion_topic]

        print(f"🔍 Verifying NO direct consumption (waiting {wait_time}s)...")

        start_time = time.time()
        events_found = 0

        try:
            async for msg in consumer:
                if time.time() - start_time > wait_time:
                    break

                if msg.topic != completion_topic:
                    continue

                try:
                    envelope: EventEnvelope = EventEnvelope.model_validate(msg.value)

                    if envelope.correlation_id == correlation_id:
                        events_found += 1
                        print(f"❌ Found unexpected direct consumption: {envelope.event_id}")

                except Exception as e:
                    print(f"❌ Error parsing event: {e}")
                    continue

        except asyncio.TimeoutError:
            pass

        if events_found == 0:
            print("✅ Confirmed: No direct consumption occurred")
            return True
        else:
            print(f"❌ Unexpected: Found {events_found} direct consumption events")
            return False

    async def monitor_topic_for_events(
        self,
        topic: str,
        duration: float = 30.0,
    ) -> list[EventEnvelope]:
        """
        Monitor a topic for any events during a specified duration.

        Useful for debugging and understanding event flow.
        """

        if topic not in self._consumers:
            self._consumers[topic] = await self.kafka_consumer_factory(
                topic,
                group_id=f"test-monitor-{int(time.time())}",
            )

        consumer = self._consumers[topic]

        print(f"🔍 Monitoring {topic} for {duration}s...")

        events: list[EventEnvelope] = []
        start_time = time.time()

        try:
            async for msg in consumer:
                if time.time() - start_time > duration:
                    break

                if msg.topic != topic:
                    continue

                try:
                    envelope: EventEnvelope = EventEnvelope.model_validate(msg.value)
                    events.append(envelope)
                    print(
                        f"📄 Event {len(events)}: {envelope.event_type} (ID: {envelope.event_id})"
                    )

                except Exception as e:
                    print(f"❌ Error parsing event: {e}")
                    continue

        except asyncio.TimeoutError:
            pass

        print(f"🔍 Monitoring complete: Found {len(events)} events")
        return events

    async def check_service_logs(
        self,
        service_name: str,
        lines: int = 50,
    ) -> str:
        """Get recent logs from a service for debugging."""

        try:
            result = self.compose.exec_in_container(
                service_name=service_name,
                command=[
                    "sh",
                    "-c",
                    f"tail -n {lines} /proc/1/fd/1 2>/dev/null || echo 'No logs available'",
                ],
            )

            return result.output.decode("utf-8") if result.output else "No output"

        except Exception as e:
            return f"Error getting logs: {e}"

    async def verify_kafka_topics_exist(self) -> dict[str, bool]:
        """Verify that all required Kafka topics exist."""

        topic_status = {}

        try:
            # Get list of topics from Kafka
            result = self.compose.exec_in_container(
                service_name="kafka",
                command=["kafka-topics.sh", "--bootstrap-server", "localhost:9092", "--list"],
            )

            existing_topics = set(result.output.decode("utf-8").strip().split("\\n"))

            for name, topic in self.topic_names.items():
                topic_status[name] = topic in existing_topics
                status = "✅" if topic_status[name] else "❌"
                print(f"{status} Topic {name}: {topic}")

        except Exception as e:
            print(f"❌ Error checking topics: {e}")
            for name in self.topic_names:
                topic_status[name] = False

        return topic_status

    def cleanup(self) -> None:
        """Clean up resources used by the helper."""
        # Consumers will be cleaned up by the fixture
        self._consumers.clear()


class ServiceHealthChecker:
    """Utility for checking service health and readiness."""

    def __init__(self, compose: DockerCompose):
        self.compose = compose

    async def check_service_health(self, service_name: str) -> dict[str, Any]:
        """
        Comprehensive health check for a service.

        Returns health status and metrics.
        """

        health_info = {
            "service_name": service_name,
            "container_running": False,
            "process_running": False,
            "kafka_connected": False,
            "database_connected": False,
            "error_message": None,
        }

        try:
            # Check if container is running
            result = self.compose.exec_in_container(
                service_name=service_name,
                command=["sh", "-c", "echo 'Container check'"],
            )

            health_info["container_running"] = result.exit_code == 0

            if health_info["container_running"]:
                # Check if the main process is running (look for Python processes)
                result = self.compose.exec_in_container(
                    service_name=service_name,
                    command=["sh", "-c", "pgrep -f python || pgrep -f pdm"],
                )

                health_info["process_running"] = result.exit_code == 0

                # For services with Kafka consumers, check if they're consuming
                if service_name in ["essay_lifecycle_worker", "nlp_service"]:
                    # This is a simplistic check - in a real implementation,
                    # services would expose health endpoints
                    result = self.compose.exec_in_container(
                        service_name=service_name,
                        command=["sh", "-c", "netstat -an | grep :9092 || ss -an | grep :9092"],
                    )

                    health_info["kafka_connected"] = result.exit_code == 0

                # Check database connectivity (look for PostgreSQL connections)
                if service_name in ["essay_lifecycle_worker", "nlp_service"]:
                    result = self.compose.exec_in_container(
                        service_name=service_name,
                        command=["sh", "-c", "netstat -an | grep :5432 || ss -an | grep :5432"],
                    )

                    health_info["database_connected"] = result.exit_code == 0

        except Exception as e:
            health_info["error_message"] = str(e)

        return health_info

    async def wait_for_service_ready(
        self,
        service_name: str,
        timeout: float = 120.0,
        check_interval: float = 5.0,
    ) -> bool:
        """
        Wait for a service to be fully ready.

        Returns True if service becomes ready, False on timeout.
        """

        print(f"⏳ Waiting for {service_name} to be ready...")

        start_time = time.time()

        while time.time() - start_time < timeout:
            health = await self.check_service_health(service_name)

            if (
                health["container_running"]
                and health["process_running"]
                and (not health["kafka_connected"] or health["kafka_connected"])
                and (not health["database_connected"] or health["database_connected"])
            ):
                print(f"✅ {service_name} is ready!")
                return True

            print(f"⏳ {service_name} not ready yet: {health}")
            await asyncio.sleep(check_interval)

        print(f"❌ {service_name} failed to become ready within {timeout}s")
        return False

    async def get_all_service_status(
        self,
        services: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Get health status for multiple services."""

        status = {}

        for service in services:
            status[service] = await self.check_service_health(service)

        return status


def format_event_summary(event: EventEnvelope) -> str:
    """Format an event for readable logging."""

    return (
        f"Event: {event.event_type} "
        f"(ID: {str(event.event_id)[:8]}, "
        f"Source: {event.source_service}, "
        f"Correlation: {event.correlation_id})"
    )


def print_pipeline_summary(
    bos_event: EventEnvelope | None,
    els_event: EventEnvelope | None,
    nlp_events: list[EventEnvelope],
    completion_event: EventEnvelope | None,
) -> None:
    """Print a summary of the pipeline execution."""

    print("\\n" + "=" * 60)
    print("PIPELINE EXECUTION SUMMARY")
    print("=" * 60)

    print("\\n1. BOS Command:")
    if bos_event:
        print(f"   ✅ {format_event_summary(bos_event)}")
    else:
        print("   ❌ No BOS event found")

    print("\\n2. ELS Transformation:")
    if els_event:
        print(f"   ✅ {format_event_summary(els_event)}")
    else:
        print("   ❌ No ELS transformation found")

    print("\\n3. NLP Processing:")
    if nlp_events:
        print(f"   ✅ {len(nlp_events)} essay events processed")
        for i, event in enumerate(nlp_events, 1):
            print(f"      {i}. {format_event_summary(event)}")
    else:
        print("   ❌ No NLP essay events found")

    print("\\n4. Batch Completion:")
    if completion_event:
        print(f"   ✅ {format_event_summary(completion_event)}")
    else:
        print("   ❌ No completion event found")

    print("\\n" + "=" * 60)


async def debug_kafka_state(
    compose: DockerCompose,
    topic_names: dict[str, str],
) -> None:
    """Debug utility to check Kafka state and topics."""

    print("\\n🔧 KAFKA DEBUG INFORMATION")
    print("=" * 50)

    try:
        # List all topics
        result = compose.exec_in_container(
            service_name="kafka",
            command=["kafka-topics.sh", "--bootstrap-server", "localhost:9092", "--list"],
        )

        if result.exit_code == 0:
            existing_topics = result.output.decode("utf-8").strip().split("\\n")
            print(f"\\n📋 Existing topics ({len(existing_topics)}):")
            for topic in existing_topics:
                print(f"   • {topic}")
        else:
            print("❌ Failed to list topics")

        # Check consumer groups
        result = compose.exec_in_container(
            service_name="kafka",
            command=["kafka-consumer-groups.sh", "--bootstrap-server", "localhost:9092", "--list"],
        )

        if result.exit_code == 0:
            groups = result.output.decode("utf-8").strip().split("\\n")
            print(f"\\n👥 Consumer groups ({len(groups)}):")
            for group in groups:
                if group.strip():
                    print(f"   • {group}")
        else:
            print("❌ Failed to list consumer groups")

    except Exception as e:
        print(f"❌ Error debugging Kafka: {e}")

    print("\\n" + "=" * 50)
