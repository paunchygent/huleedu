"""
Pipeline Test Harness

Reusable test harness for comprehensive pipeline testing with student matching support.
Enables sequential pipeline execution with phase pruning validation.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from common_core.domain_enums import CourseCode
from structlog import get_logger

from tests.functional.client_pipeline_test_utils import publish_client_pipeline_request
from tests.functional.comprehensive_pipeline_utils import PIPELINE_TOPICS
from tests.utils.auth_manager import AuthTestManager
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager

logger = get_logger(__name__)


# All student names from essay files (properly capitalized)
TEST_STUDENT_NAMES = [
    "Alva Lemos",
    "Amanda Frantz",
    "Arve Bergström",
    "Axel Karlsson",
    "Cornelia Kardborn",
    "Ebba Noren Bergsröm",
    "Ebba Saviluoto",
    "Edgar Gezelius",
    "Elin Bogren",
    "Ellie Rankin",
    "Elvira Johansson",
    "Emil Pihlman",
    "Emil Zäll Jernberg",
    "Emma Wüst",
    "Erik Arvman",
    "Figg Eriksson",
    "Jagoda Struzik",
    "Jonathan Hedqvist",
    "Leon Gustavsson",
    "Manuel Gren",
    "Melek Özturk",
    "Nelli Moilanen",
    "Sam Höglund Öman",
    "Stella Sellström",
    "Vera Karlberg",
    "Simon Pub",
    "Tindra Cruz",
]


@dataclass
class PipelineExecutionResult:
    """Results from a single pipeline execution."""

    pipeline_name: str
    all_steps_completed: bool
    executed_steps: list[str] = field(default_factory=list)
    pruned_phases: list[str] = field(default_factory=list)
    reused_storage_ids: dict[str, str] = field(default_factory=dict)
    completion_event: Optional[dict[str, Any]] = None
    student_matches_found: int = 0
    execution_time_seconds: float = 0.0


@dataclass
class PipelineExecutionTracker:
    """Tracks events during pipeline execution."""

    initiated_phases: set[str] = field(default_factory=set)
    completed_phases: set[str] = field(default_factory=set)
    storage_ids: dict[str, str] = field(default_factory=dict)
    pruned_phases: list[str] = field(default_factory=list)
    reused_storage_ids: dict[str, str] = field(default_factory=dict)


class PipelineTestHarness:
    """Reusable harness for comprehensive pipeline testing with student matching."""

    def __init__(
        self,
        service_manager: ServiceTestManager,
        kafka_manager: KafkaTestManager,
        auth_manager: AuthTestManager,
    ):
        self.service_manager = service_manager
        self.kafka_manager = kafka_manager
        self.auth_manager = auth_manager
        self.batch_id: Optional[str] = None
        self.correlation_id: Optional[str] = None
        self.class_id: Optional[str] = None
        self.consumer: Optional[Any] = None
        self.consumer_context: Optional[Any] = None  # Store context manager
        self.teacher_user: Optional[Any] = None
        self.completed_phases: set[str] = set()
        self.storage_ids: dict[str, str] = {}

    async def start_consumer(self) -> None:
        """Start the Kafka consumer for monitoring events."""
        if self.consumer:
            return  # Already started

        # Setup Kafka consumer for monitoring
        phase2_topics = [
            "huleedu.batch.student.matching.initiate.command.v1",
            "huleedu.batch.student.matching.requested.v1",
            "huleedu.batch.author.matches.suggested.v1",
            "huleedu.class.student.associations.confirmed.v1",
            "huleedu.els.batch.essays.ready.v1",
        ]
        all_topics = list(PIPELINE_TOPICS.values()) + phase2_topics

        # Create consumer context
        self.consumer_context = self.kafka_manager.consumer("pipeline_test_harness", all_topics)
        self.consumer = await self.consumer_context.__aenter__()
        await self.consumer.seek_to_end()  # Start from latest
        logger.info("📡 Kafka consumer started for pipeline monitoring")

    async def setup_test_class_with_roster(self) -> str:
        """Create the test class with all students from essay files."""
        logger.info(f"🏫 Setting up test class with {len(TEST_STUDENT_NAMES)} students")

        # Create teacher user if not exists
        if not self.teacher_user:
            self.teacher_user = self.auth_manager.create_test_user(role="teacher")

        # Create the class
        class_data = {
            "name": "Book Report ES24B Test Class",
            "course_codes": ["ENG5"],  # Must match CourseCode enum
        }

        # Create the class
        try:
            response = await self.service_manager.make_request(
                "POST",
                "class_management_service",
                "/v1/classes/",
                json=class_data,
                user=self.teacher_user,
            )
            created_class_id = str(response["id"])
            logger.info(f"✅ Created class with ID: {created_class_id}")
        except Exception as e:
            raise RuntimeError(f"Failed to create test class: {e}")

        # Create all students and associate them with the class
        for student_name in TEST_STUDENT_NAMES:
            parts = student_name.rsplit(" ", 1)
            if len(parts) == 2:
                first_name, last_name = parts
            else:
                first_name = student_name
                last_name = ""

            student_data = {
                "person_name": {"first_name": first_name, "last_name": last_name},
                "email": f"{first_name.lower().replace(' ', '.')}.{last_name.lower()}@test.edu"
                if last_name
                else f"{first_name.lower()}@test.edu",
                "class_ids": [created_class_id],
            }

            try:
                await self.service_manager.make_request(
                    "POST",
                    "class_management_service",
                    "/v1/classes/students",
                    json=student_data,
                    user=self.teacher_user,
                )
                logger.debug(f"✅ Created student: {student_name}")
            except Exception as e:
                logger.warning(f"Failed to create student {student_name}: {e}")

        logger.info(f"✅ Test class setup complete with {len(TEST_STUDENT_NAMES)} students")
        self.class_id = created_class_id
        return created_class_id

    async def setup_regular_batch_with_student_matching(
        self,
        essay_files: list[Path],
        class_id: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Setup Phase 1: Create batch, upload essays, complete student matching.

        Returns:
            tuple[str, str]: (batch_id, correlation_id)
        """
        # Setup class if needed
        if class_id:
            self.class_id = class_id
        elif not self.class_id:
            self.class_id = await self.setup_test_class_with_roster()

        # Start Kafka consumer if not already started
        await self.start_consumer()

        # Generate correlation ID
        self.correlation_id = str(uuid.uuid4())
        logger.info(f"🔍 Test correlation ID: {self.correlation_id}")

        # Register batch WITH class_id (triggers REGULAR flow)
        logger.info(f"📝 Registering REGULAR batch with class_id: {self.class_id}")
        self.batch_id, actual_correlation_id = await self.service_manager.create_batch(
            expected_essay_count=len(essay_files),
            course_code=CourseCode.ENG5,
            user=self.teacher_user,
            correlation_id=self.correlation_id,
            enable_cj_assessment=True,
            class_id=self.class_id,  # This triggers REGULAR flow!
        )

        # Update correlation ID to match service
        self.correlation_id = actual_correlation_id

        logger.info(f"✅ REGULAR batch registered: {self.batch_id}")
        logger.info(f"🔗 Monitoring events with correlation ID: {self.correlation_id}")

        # Upload real student essays
        logger.info("🚀 Uploading real student essays...")
        files_data = []
        for essay_file in essay_files:
            essay_content = essay_file.read_bytes()
            files_data.append({"name": essay_file.name, "content": essay_content})

        upload_result = await self.service_manager.upload_files(
            batch_id=self.batch_id,
            files=files_data,
            user=self.teacher_user,
            correlation_id=self.correlation_id,
        )
        logger.info(f"✅ File upload successful: {upload_result}")

        # Wait for content provisioning to complete
        logger.info("⏳ Waiting for content provisioning...")
        await asyncio.sleep(3)

        # Wait for student matching events
        logger.info("⏳ Waiting for student matching to begin...")
        matching_event = await self._wait_for_student_matching_events(timeout_seconds=60)

        if not matching_event:
            raise RuntimeError("Student matching events not received within timeout")

        # Give NLP service time to process and Class Management to store
        await asyncio.sleep(2)

        # Teacher confirms associations
        logger.info("👨‍🏫 Teacher reviewing and confirming student associations...")
        await self._confirm_student_associations()

        # Wait for BatchEssaysReady
        logger.info("⏳ Waiting for BatchEssaysReady after association confirmation...")
        ready_received = await self._wait_for_batch_essays_ready()

        if not ready_received:
            raise RuntimeError("BatchEssaysReady not received after association confirmation")

        logger.info("✅ Batch ready for pipeline execution")
        return self.batch_id, self.correlation_id

    async def setup_guest_batch(
        self,
        essay_files: list[Path],
        user: Optional[Any] = None,
    ) -> tuple[str, str]:
        """
        Setup a GUEST batch (no student matching) for pipeline testing.

        Args:
            essay_files: List of essay files to upload
            user: Optional user for batch creation (creates guest user if not provided)

        Returns:
            Tuple of (batch_id, correlation_id)
        """
        # Create guest user if not provided
        if not user:
            user = self.auth_manager.create_test_user(role="guest")

        # Start Kafka consumer if not already started
        await self.start_consumer()

        # Generate correlation ID
        self.correlation_id = str(uuid.uuid4())
        logger.info(f"🔍 Test correlation ID: {self.correlation_id}")

        # Register GUEST batch (NO class_id)
        logger.info("📝 Registering GUEST batch (no class_id)")
        from common_core.domain_enums import CourseCode

        self.batch_id, actual_correlation_id = await self.service_manager.create_batch(
            expected_essay_count=len(essay_files),
            course_code=CourseCode.ENG5,
            user=user,
            correlation_id=self.correlation_id,
            enable_cj_assessment=True,
            # NO class_id - this triggers GUEST flow!
        )

        # Update correlation ID to match service
        self.correlation_id = actual_correlation_id

        logger.info(f"✅ GUEST batch registered: {self.batch_id}")

        # Upload essays
        logger.info("🚀 Uploading essays for GUEST batch...")
        files_data = []
        for essay_file in essay_files:
            essay_content = essay_file.read_bytes()
            files_data.append({"name": essay_file.name, "content": essay_content})

        upload_result = await self.service_manager.upload_files(
            batch_id=self.batch_id,
            files=files_data,
            user=user,
            correlation_id=self.correlation_id,
        )
        logger.info(f"✅ File upload successful: {upload_result}")

        # Wait for content provisioning and batch to be ready
        logger.info("⏳ Waiting for GUEST batch to be ready...")
        await asyncio.sleep(5)  # Give time for content provisioning

        # For GUEST batches, we should receive BatchEssaysReady directly after content provisioning
        ready_received = await self._wait_for_batch_essays_ready(timeout_seconds=15)

        if not ready_received:
            logger.warning("BatchEssaysReady not received for GUEST batch, but continuing...")

        logger.info("✅ GUEST batch ready for pipeline execution")
        return self.batch_id, self.correlation_id

    async def execute_pipeline(
        self,
        pipeline_name: str,
        expected_steps: list[str],
        expected_completion_event: str,
        validate_phase_pruning: bool = False,
        timeout_seconds: int = 120,
    ) -> PipelineExecutionResult:
        """
        Execute a pipeline and track results.

        Args:
            pipeline_name: Name of pipeline to execute
            expected_steps: Steps expected to execute (after pruning)
            expected_completion_event: Event type marking pipeline completion
            validate_phase_pruning: Whether to validate phase pruning occurred
            timeout_seconds: Timeout for pipeline execution

        Returns:
            PipelineExecutionResult with execution details
        """
        if not self.batch_id or not self.correlation_id:
            raise RuntimeError("Must call setup_regular_batch_with_student_matching first")

        # Ensure consumer is started
        await self.start_consumer()

        # Track execution
        tracker = PipelineExecutionTracker()
        start_time = asyncio.get_event_loop().time()

        # Send pipeline request
        logger.info(f"📤 Sending {pipeline_name} pipeline request...")
        request_correlation_id = await publish_client_pipeline_request(
            self.kafka_manager, self.batch_id, pipeline_name, self.correlation_id
        )
        logger.info(f"📡 Published {pipeline_name} pipeline request: {request_correlation_id}")

        # Monitor pipeline execution
        completion_event = await self._monitor_pipeline_execution(
            request_correlation_id,
            expected_steps,
            expected_completion_event,
            tracker,
            timeout_seconds,
        )

        execution_time = asyncio.get_event_loop().time() - start_time

        # Create result
        result = PipelineExecutionResult(
            pipeline_name=pipeline_name,
            all_steps_completed=completion_event is not None,
            executed_steps=list(tracker.completed_phases),
            pruned_phases=tracker.pruned_phases,
            reused_storage_ids=tracker.reused_storage_ids,
            completion_event=completion_event,
            execution_time_seconds=execution_time,
        )

        # Validate phase pruning if requested
        if validate_phase_pruning:
            self._validate_phase_pruning(tracker, expected_steps)

        # Update harness tracking
        self.completed_phases.update(tracker.completed_phases)
        self.storage_ids.update(tracker.storage_ids)

        logger.info(
            f"✅ Pipeline {pipeline_name} execution complete in {execution_time:.2f}s. "
            f"Executed: {result.executed_steps}, Pruned: {result.pruned_phases}"
        )

        return result

    async def _wait_for_student_matching_events(
        self, timeout_seconds: int = 60
    ) -> Optional[dict[str, Any]]:
        """Monitor Phase 2 student matching events."""
        start_time = asyncio.get_event_loop().time()
        end_time = start_time + timeout_seconds

        matching_initiated = False
        matching_requested = False

        while asyncio.get_event_loop().time() < end_time:
            try:
                if not self.consumer:
                    raise RuntimeError("Consumer not initialized")
                msg_batch = await self.consumer.getmany(timeout_ms=1000, max_records=10)

                for _topic_partition, messages in msg_batch.items():
                    for message in messages:
                        try:
                            # Parse message
                            if isinstance(message.value, bytes):
                                raw_message = message.value.decode("utf-8")
                            else:
                                raw_message = message.value

                            envelope_data: dict[str, Any] = json.loads(raw_message)
                            event_correlation_id = envelope_data.get("correlation_id")
                            event_type = envelope_data.get("event_type", "")

                            # Filter by correlation ID
                            if event_correlation_id != self.correlation_id:
                                continue

                            # Track student matching flow
                            if "student.matching.initiate.command" in event_type:
                                matching_initiated = True
                                logger.info("📨 BOS initiated student matching")

                            elif "student.matching.requested" in event_type:
                                matching_requested = True
                                logger.info("📨 ELS requested student matching from NLP")

                            elif "author.matches.suggested" in event_type:
                                logger.info("📨 NLP suggested student-essay associations")
                                return envelope_data

                        except Exception as e:
                            logger.warning(f"Error parsing message: {e}")
                            continue

            except asyncio.TimeoutError:
                continue

        logger.error(
            f"Timeout waiting for student matching events. "
            f"Initiated: {matching_initiated}, Requested: {matching_requested}"
        )
        return None

    async def _confirm_student_associations(self) -> dict[str, Any]:
        """Fetch suggested associations and confirm them as teacher."""
        # Get suggested associations
        response = await self.service_manager.make_request(
            method="GET",
            service="class_management_service",
            path=f"/v1/batches/{self.batch_id}/student-associations",
            user=self.teacher_user,
            correlation_id=self.correlation_id,
        )

        associations = response.get("associations", [])
        logger.info(f"📋 Retrieved {len(associations)} suggested associations")

        # Confirm all associations
        confirmation_data = {
            "associations": [
                {
                    "essay_id": assoc["essay_id"],
                    "student_id": assoc["suggested_student_id"],
                    "confirmed": True,
                }
                for assoc in associations
            ],
            "confirmation_method": "manual_teacher_review",
        }

        # Confirm associations
        confirm_response = await self.service_manager.make_request(
            method="POST",
            service="class_management_service",
            path=f"/v1/batches/{self.batch_id}/student-associations/confirm",
            json=confirmation_data,
            user=self.teacher_user,
            correlation_id=self.correlation_id,
        )

        logger.info("✅ Teacher confirmed all student-essay associations")
        return confirm_response

    async def _wait_for_batch_essays_ready(self, timeout_seconds: int = 30) -> bool:
        """Wait for BatchEssaysReady event after associations are confirmed."""
        start_time = asyncio.get_event_loop().time()
        end_time = start_time + timeout_seconds

        while asyncio.get_event_loop().time() < end_time:
            try:
                if not self.consumer:
                    raise RuntimeError("Consumer not initialized")
                msg_batch = await self.consumer.getmany(timeout_ms=1000, max_records=10)

                for _topic_partition, messages in msg_batch.items():
                    for message in messages:
                        try:
                            # Parse message
                            if isinstance(message.value, bytes):
                                raw_message = message.value.decode("utf-8")
                            else:
                                raw_message = message.value

                            envelope_data: dict[str, Any] = json.loads(raw_message)
                            event_correlation_id = envelope_data.get("correlation_id")
                            event_type = envelope_data.get("event_type", "")

                            # Check for our event
                            if (
                                event_correlation_id == self.correlation_id
                                and "batch.essays.ready" in event_type
                            ):
                                logger.info(
                                    "📨 BatchEssaysReady received - batch ready for pipeline!"
                                )
                                return True

                        except Exception as e:
                            logger.warning(f"Error parsing message: {e}")
                            continue

            except asyncio.TimeoutError:
                continue

        return False

    async def _monitor_pipeline_execution(
        self,
        request_correlation_id: str,
        expected_steps: list[str],
        expected_completion_event: str,
        tracker: PipelineExecutionTracker,
        timeout_seconds: int,
    ) -> Optional[dict[str, Any]]:
        """Monitor pipeline execution and track phases."""
        start_time = asyncio.get_event_loop().time()
        end_time = start_time + timeout_seconds

        while asyncio.get_event_loop().time() < end_time:
            try:
                if not self.consumer:
                    raise RuntimeError("Consumer not initialized")
                msg_batch = await self.consumer.getmany(timeout_ms=1000, max_records=10)

                for _topic_partition, messages in msg_batch.items():
                    for message in messages:
                        try:
                            # Parse message
                            if isinstance(message.value, bytes):
                                raw_message = message.value.decode("utf-8")
                            else:
                                raw_message = message.value

                            envelope_data: dict[str, Any] = json.loads(raw_message)
                            event_correlation_id = envelope_data.get("correlation_id")
                            event_type = envelope_data.get("event_type", "")
                            event_data = envelope_data.get("data", {})

                            # Filter by correlation ID - STRICT filtering for THIS pipeline request
                            # Special-case: CJ completion events may be published with the original
                            # batch registration correlation_id instead of the pipeline request ID.
                            if event_correlation_id != request_correlation_id:
                                is_cj_completion = (
                                    expected_completion_event in event_type
                                    and "cj_assessment.completed" in event_type
                                )
                                if not (
                                    is_cj_completion
                                    and self.correlation_id
                                    and event_correlation_id == self.correlation_id
                                ):
                                    continue

                            # Debug log ALL events with our correlation ID
                            logger.debug(
                                f"📡 Event received: type={event_type}, "
                                f"phase={event_data.get('phase_name', 'N/A')}, "
                                f"correlation={event_correlation_id[:8]}..."
                            )

                            # Track phase initiations - these determine what's actually executing
                            if "initiate.command" in event_type:
                                if "spellcheck" in event_type:
                                    tracker.initiated_phases.add("spellcheck")
                                    logger.info("📨 Spellcheck phase initiated")
                                elif "nlp" in event_type and "student.matching" not in event_type:
                                    tracker.initiated_phases.add("nlp")
                                    logger.info("📨 NLP analysis phase initiated")
                                elif "cj_assessment" in event_type or "cj.assessment" in event_type:
                                    tracker.initiated_phases.add("cj_assessment")
                                    logger.info("📨 CJ Assessment phase initiated")
                                elif "ai_feedback" in event_type or "ai.feedback" in event_type:
                                    tracker.initiated_phases.add("ai_feedback")
                                    logger.info("📨 AI Feedback phase initiated")

                            # Track phase completions - ONLY count as executed if initiated
                            elif "phase.outcome" in event_type:
                                phase_name = event_data.get("phase_name")
                                phase_status = event_data.get("phase_status")
                                storage_id = event_data.get("storage_id")

                                if phase_status in [
                                    "completed_successfully",
                                    "completed_with_failures",
                                ]:
                                    # CRITICAL: Only add to completed if initiated in THIS execution
                                    if phase_name in tracker.initiated_phases:
                                        tracker.completed_phases.add(phase_name)
                                        if storage_id:
                                            tracker.storage_ids[phase_name] = storage_id
                                        logger.info(f"✅ Phase {phase_name} completed")
                                    else:
                                        logger.debug(
                                            f"⚠️ Ignoring phase completion for {phase_name} - "
                                            f"not initiated in this pipeline execution"
                                        )

                            # Check for phase skipped/pruned events
                            elif "phase.skipped" in event_type:
                                phase_name = event_data.get("phase_name")
                                storage_id = event_data.get("storage_id")
                                skip_reason = event_data.get("skip_reason", "already_completed")

                                tracker.pruned_phases.append(phase_name)
                                if storage_id:
                                    tracker.reused_storage_ids[phase_name] = storage_id
                                logger.info(f"⏭️ Phase {phase_name} SKIPPED (reason: {skip_reason})")

                            # Legacy phase reuse detection (remove once phase.skipped events work)
                            elif "phase.reused" in event_type:
                                phase_name = event_data.get("phase_name")
                                storage_id = event_data.get("storage_id")
                                tracker.pruned_phases.append(phase_name)
                                if storage_id:
                                    tracker.reused_storage_ids[phase_name] = storage_id
                                logger.info(
                                    f"⏭️ Phase {phase_name} pruned (reusing existing results)"
                                )

                            # Check for specific completion events - indicate pipeline completion
                            # but should NOT add phases to executed list
                            if expected_completion_event in event_type:
                                # Extract phase from completion event type for special handling
                                if "spellcheck.completed" in event_type:
                                    # Individual essay completions - don't track as phase completion
                                    pass
                                elif "nlp.analysis.completed" in event_type:
                                    # Only mark nlp as completed if it was initiated
                                    if "nlp" in tracker.initiated_phases:
                                        tracker.completed_phases.add("nlp")
                                        logger.info(
                                            "✅ Phase nlp completed (from analysis completion)"
                                        )
                                elif "cj_assessment.completed" in event_type:
                                    # Only mark cj_assessment as completed if it was initiated
                                    if "cj_assessment" in tracker.initiated_phases:
                                        tracker.completed_phases.add("cj_assessment")
                                        logger.info(
                                            "✅ Phase cj_assessment completed "
                                            "(from assessment completion)"
                                        )

                                logger.info(f"🎯 Pipeline completed: {expected_completion_event}")
                                return envelope_data

                        except Exception as e:
                            logger.warning(f"Error parsing message: {e}")
                            continue

            except asyncio.TimeoutError:
                continue

        logger.error(f"Pipeline did not complete within {timeout_seconds} seconds")
        logger.error(f"Initiated phases: {tracker.initiated_phases}")
        logger.error(f"Completed phases: {tracker.completed_phases}")
        return None

    def _validate_phase_pruning(
        self, tracker: PipelineExecutionTracker, expected_steps: list[str]
    ) -> None:
        """Verify that already-completed phases were skipped."""
        for phase in self.completed_phases:
            # Phase should not be initiated if it's already completed and not expected to run again
            if phase not in expected_steps and phase in tracker.initiated_phases:
                raise AssertionError(f"Phase {phase} should have been pruned but was initiated")

            # Check if storage ID was reused for pruned phases
            if phase in self.storage_ids and phase not in expected_steps:
                assert tracker.reused_storage_ids.get(phase) == self.storage_ids.get(phase), (
                    f"Phase {phase} should have reused storage ID {self.storage_ids[phase]}"
                )

        logger.info(f"✅ Phase pruning validation passed. Pruned phases: {tracker.pruned_phases}")

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.consumer_context:
            await self.consumer_context.__aexit__(None, None, None)
            self.consumer = None
            self.consumer_context = None
            logger.info("🧹 Kafka consumer closed")
