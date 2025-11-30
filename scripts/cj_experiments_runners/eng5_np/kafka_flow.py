"""Kafka publishing and callback capture for ENG5 NP runner."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import typer
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import (
    AssessmentResultV1,
    CJAssessmentCompletedV1,
    ELS_CJAssessmentRequestV1,
)
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.logging_utils import create_service_logger, log_event_processing

from scripts.cj_experiments_runners.eng5_np.events import write_completion_event
from scripts.cj_experiments_runners.eng5_np.hydrator import AssessmentRunHydrator
from scripts.cj_experiments_runners.eng5_np.settings import RunnerSettings

_LOGGER = create_service_logger("eng5_np_kafka_flow")


async def publish_envelope_to_kafka(
    *,
    envelope: EventEnvelope[ELS_CJAssessmentRequestV1],
    settings: RunnerSettings,
) -> None:
    """Publish the CJ request envelope to Kafka using ``KafkaBus``."""

    logger = _LOGGER.bind(
        batch_id=settings.batch_id,
        batch_uuid=str(settings.batch_uuid),
        kafka_client_id=settings.kafka_client_id,
        kafka_bootstrap=settings.kafka_bootstrap,
        runner_mode=settings.mode.value,
        correlation_id=str(settings.correlation_id),
    )

    kafka_bus = KafkaBus(
        client_id=settings.kafka_client_id,
        bootstrap_servers=settings.kafka_bootstrap,
    )
    await kafka_bus.start()
    try:
        logger.debug(
            "kafka_publish_started",
            topic=topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED),
            request_correlation=str(envelope.correlation_id),
        )
        await kafka_bus.publish(
            topic=topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED),
            envelope=envelope,
            key=str(settings.batch_uuid),
        )
        logger.info(
            "kafka_publish_success",
            topic=topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED),
            request_correlation=str(envelope.correlation_id),
        )
    finally:
        await kafka_bus.stop()


async def run_publish_and_capture(
    *,
    envelope: EventEnvelope[ELS_CJAssessmentRequestV1],
    settings: RunnerSettings,
    hydrator: AssessmentRunHydrator | None,
) -> None:
    collector: AssessmentEventCollector | None = None
    collector_task: asyncio.Task[None] | None = None

    logger = _LOGGER.bind(
        batch_id=settings.batch_id,
        batch_uuid=str(settings.batch_uuid),
        kafka_client_id=settings.kafka_client_id,
        kafka_bootstrap=settings.kafka_bootstrap,
        await_completion=settings.await_completion,
        runner_mode=settings.mode.value,
        correlation_id=str(settings.correlation_id),
    )

    if hydrator and settings.use_kafka and settings.await_completion:
        collector = AssessmentEventCollector(settings=settings, hydrator=hydrator)
        collector_task = asyncio.create_task(collector.consume())
        await collector.wait_until_ready()

    try:
        if settings.use_kafka:
            await publish_envelope_to_kafka(envelope=envelope, settings=settings)
            typer.echo(
                "Kafka publish succeeded -> topic "
                f"{topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)}"
            )
            logger.info(
                "runner_kafka_publish_completed",
                await_completion=settings.await_completion,
            )
        else:
            typer.echo("--no-kafka supplied; skipping publish and event capture.")
            logger.info("runner_publish_skipped", reason="no_kafka")

        if collector:
            await collector.wait_for_completion()
            logger.info(
                "collector_completed",
                event_counts=collector.observed_counts,
            )

    finally:
        if collector:
            collector.request_stop()
        if collector_task:
            with contextlib.suppress(Exception):
                await collector_task


class AssessmentEventCollector:
    """Async Kafka consumer that captures callbacks for a single ENG5 batch."""

    def __init__(self, settings: RunnerSettings, hydrator: AssessmentRunHydrator) -> None:
        self.settings = settings
        self.hydrator = hydrator
        self._ready = asyncio.Event()
        self._done = asyncio.Event()
        self._stop = asyncio.Event()
        self._rich_observed = False
        self._completion_observed = False
        self._error: Exception | None = None
        self._started_at: float | None = None
        self._logger = _LOGGER.bind(
            batch_id=settings.batch_id,
            batch_uuid=str(settings.batch_uuid),
            kafka_group=f"{settings.kafka_client_id}-eng5np-{settings.batch_uuid}",
            kafka_client_id=settings.kafka_client_id,
            kafka_bootstrap=settings.kafka_bootstrap,
            runner_mode=settings.mode.value,
            correlation_id=str(settings.correlation_id),
        )
        self._observed_counts = {
            "llm_comparisons": 0,
            "assessment_results": 0,
            "completions": 0,
        }

    async def consume(self) -> None:
        from aiokafka import AIOKafkaConsumer

        topics = (
            topic_name(ProcessingEvent.LLM_COMPARISON_RESULT),
            topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
            topic_name(ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED),
        )

        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self.settings.kafka_bootstrap,
            group_id=f"{self.settings.kafka_client_id}-eng5np-{self.settings.batch_uuid}",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            session_timeout_ms=45000,
            max_poll_records=50,
        )

        await consumer.start()
        loop = asyncio.get_event_loop()
        self._started_at = loop.time()
        self._ready.set()
        deadline = loop.time() + self.settings.completion_timeout
        self._logger.info(
            "collector_started",
            topics=topics,
            completion_timeout=self.settings.completion_timeout,
        )

        try:
            while not self._stop.is_set():
                if self._rich_observed:
                    break
                remaining = deadline - loop.time()
                if remaining <= 0:
                    typer.echo(
                        "Timed out waiting for CJ assessment results; captured partial data.",
                        err=True,
                    )
                    self._logger.warning(
                        "collector_timeout",
                        elapsed=self._elapsed_time(),
                        event_counts=self._observed_counts,
                    )
                    elapsed = self._elapsed_time()
                    if elapsed is not None:
                        self.hydrator.mark_timeout(elapsed)
                    break

                batches = await consumer.getmany(timeout_ms=1000, max_records=50)
                if not batches:
                    continue

                commit_needed = False
                for records in batches.values():
                    for record in records:
                        handled = await self._handle_record(record)
                        commit_needed = commit_needed or handled

                if commit_needed:
                    await consumer.commit()

        except Exception as exc:  # pragma: no cover - defensive guard
            self._error = exc
            self._logger.exception(
                "collector_error",
                error_type=exc.__class__.__name__,
            )
            raise
        finally:
            await consumer.stop()
            self._done.set()
            self._logger.info(
                "collector_stopped",
                event_counts=self._observed_counts,
            )

    async def _handle_record(self, record: Any) -> bool:
        from aiokafka.structs import ConsumerRecord

        if not isinstance(record, ConsumerRecord):
            return False

        try:
            payload = record.value.decode("utf-8") if record.value else "{}"
        except Exception:
            return False

        topic = record.topic
        target_batch = str(self.settings.batch_uuid)

        if topic == topic_name(ProcessingEvent.LLM_COMPARISON_RESULT):
            try:
                envelope = EventEnvelope[LLMComparisonResultV1].model_validate_json(payload)
                result_data = LLMComparisonResultV1.model_validate(envelope.data)
            except Exception as exc:  # pragma: no cover - defensive guard
                self._logger.warning(
                    "collector_llm_comparison_deserialization_failed",
                    error_type=exc.__class__.__name__,
                )
                return True

            envelope.data = result_data  # Update envelope with validated model
            metadata = result_data.request_metadata or {}
            batch_hint = metadata.get("batch_id") or metadata.get("bos_batch_id")
            if not batch_hint or batch_hint != target_batch:
                self._logger.debug(
                    "comparison_event_skipped",
                    request_id=result_data.request_id,
                    comparison_batch=batch_hint,
                )
                return True

            self.hydrator.apply_llm_comparison(envelope)
            self._observed_counts["llm_comparisons"] += 1
            log_event_processing(
                logger=self._logger,
                message="collector_llm_comparison_applied",
                envelope=envelope,
                event_count=self._observed_counts["llm_comparisons"],
            )
            return True

        if topic == topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED):
            try:
                envelope = EventEnvelope[CJAssessmentCompletedV1].model_validate_json(payload)
                completion_data = CJAssessmentCompletedV1.model_validate(envelope.data)
            except Exception as exc:  # pragma: no cover - defensive guard
                self._logger.warning(
                    "collector_completion_deserialization_failed",
                    error_type=exc.__class__.__name__,
                )
                return True

            envelope.data = completion_data  # Update envelope with validated model
            if completion_data.entity_id != target_batch:
                self._logger.debug(
                    "completion_event_skipped",
                    event_batch=completion_data.entity_id,
                )
                return True

            write_completion_event(envelope=envelope, output_dir=self.settings.output_dir)
            self._completion_observed = True
            self.hydrator.record_completion_seen()
            self._observed_counts["completions"] += 1
            log_event_processing(
                logger=self._logger,
                message="collector_completion_applied",
                envelope=envelope,
                event_count=self._observed_counts["completions"],
            )
            return True

        if topic == topic_name(ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED):
            try:
                envelope = EventEnvelope[AssessmentResultV1].model_validate_json(payload)
                result_data = AssessmentResultV1.model_validate(envelope.data)
            except Exception as exc:  # pragma: no cover - defensive guard
                self._logger.warning(
                    "collector_assessment_result_deserialization_failed",
                    error_type=exc.__class__.__name__,
                )
                return True

            envelope.data = result_data  # Update envelope with validated model
            if result_data.batch_id != target_batch:
                self._logger.debug(
                    "assessment_result_skipped",
                    event_batch=result_data.batch_id,
                )
                return True

            self.hydrator.apply_assessment_result(envelope)
            self._rich_observed = True
            self._observed_counts["assessment_results"] += 1
            log_event_processing(
                logger=self._logger,
                message="collector_assessment_result_applied",
                envelope=envelope,
                event_count=self._observed_counts["assessment_results"],
            )
            return True

        return False

    def _elapsed_time(self) -> float | None:
        if self._started_at is None:
            return None
        return asyncio.get_event_loop().time() - self._started_at

    async def wait_until_ready(self) -> None:
        await self._ready.wait()

    async def wait_for_completion(self) -> None:
        await self._done.wait()
        if self._error:
            raise self._error

    def request_stop(self) -> None:
        self._stop.set()

    @property
    def observed_counts(self) -> dict[str, int]:
        """Return a snapshot of observed event counters."""

        return dict(self._observed_counts)
