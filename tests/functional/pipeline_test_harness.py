"""
Pipeline Test Harness

Reusable test harness for comprehensive pipeline testing with student matching support.
Enables sequential pipeline execution with phase pruning validation.
"""

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from structlog import get_logger

from tests.functional.comprehensive_pipeline_utils import PIPELINE_TOPICS
from tests.functional.pipeline_harness_helpers import (
    BatchSetupHelper,
    CreditProvisioningHelper,
    EventWaitingHelper,
    KafkaMonitorHelper,
    PipelineValidationHelper,
    StudentManagementHelper,
)
from tests.functional.pipeline_harness_helpers.kafka_monitor import PipelineExecutionTracker
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
    ras_result_event: Optional[dict[str, Any]] = None  # BatchResultsReadyV1 event from RAS
    student_matches_found: int = 0
    execution_time_seconds: float = 0.0


class PipelineTestHarness:
    """Main orchestrator for pipeline end-to-end testing.

    This harness coordinates pipeline testing by delegating specific responsibilities
    to focused helper modules, following Single Responsibility Principle.
    """

    def __init__(
        self,
        service_manager: ServiceTestManager,
        kafka_manager: KafkaTestManager,
        auth_manager: AuthTestManager,
    ):
        """Initialize the test harness with required managers."""
        self.service_manager = service_manager
        self.kafka_manager = kafka_manager
        self.auth_manager = auth_manager

        # State tracking
        self.batch_id: Optional[str] = None
        self.correlation_id: Optional[str] = None
        self.class_id: Optional[str] = None
        self.consumer: Optional[Any] = None
        self.consumer_context: Optional[Any] = None
        self.teacher_user: Optional[Any] = None
        self.completed_phases: set[str] = set()
        self.storage_ids: dict[str, str] = {}

        # Initialize helpers
        self.batch_helper = BatchSetupHelper(
            service_manager=service_manager,
            kafka_manager=kafka_manager,
            auth_manager=auth_manager,
        )

    async def start_consumer(self) -> None:
        """Start the Kafka consumer for monitoring events."""
        if self.consumer:
            return  # Already started

        self.consumer, self.consumer_context = await KafkaMonitorHelper.start_consumer(
            kafka_manager=self.kafka_manager,
            pipeline_topics=PIPELINE_TOPICS,
        )

    async def setup_test_class_with_roster(self) -> str:
        """Create the test class with all students from essay files."""
        class_id, teacher_user, _ = await StudentManagementHelper.create_class_with_roster(
            service_manager=self.service_manager,
            auth_manager=self.auth_manager,
        )
        self.class_id = class_id
        self.teacher_user = teacher_user
        return class_id

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

        # Ensure teacher_user is set
        if not self.teacher_user:
            raise RuntimeError("Teacher user not initialized")

        # Delegate to batch helper
        (
            batch_id,
            correlation_id,
        ) = await self.batch_helper.setup_regular_batch_with_student_matching(
            essay_files=essay_files,
            class_id=self.class_id,
            teacher_user=self.teacher_user,
            consumer=self.consumer,
            provision_credits=True,
        )

        self.batch_id = batch_id
        self.correlation_id = correlation_id
        return batch_id, correlation_id

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
        # Start Kafka consumer if not already started
        await self.start_consumer()

        # Delegate to batch helper
        batch_id, correlation_id, used_user = await self.batch_helper.setup_guest_batch(
            essay_files=essay_files,
            consumer=self.consumer,
            user=user,
            provision_credits=True,
        )

        self.batch_id = batch_id
        self.correlation_id = correlation_id
        if not self.teacher_user:
            self.teacher_user = used_user

        return batch_id, correlation_id

    async def execute_pipeline(
        self,
        pipeline_name: str,
        expected_steps: list[str],
        expected_completion_event: str,
        validate_phase_pruning: bool = False,
        expected_pruned_phases: Optional[list[str]] = None,
        timeout_seconds: int = 120,
    ) -> PipelineExecutionResult:
        """
        Execute a pipeline and monitor its progress.

        Args:
            pipeline_name: Name of the pipeline to execute
            expected_steps: List of expected pipeline steps
            expected_completion_event: Event that signals pipeline completion
            validate_phase_pruning: Whether to validate phase pruning
            expected_pruned_phases: List of phases expected to be pruned
            timeout_seconds: Timeout for pipeline execution

        Returns:
            PipelineExecutionResult with execution details
        """
        import time

        if not self.batch_id or not self.correlation_id:
            raise RuntimeError(
                "Batch not setup. Call setup_regular_batch or setup_guest_batch first"
            )

        start_time = time.time()

        # Generate new correlation ID for this specific pipeline request
        request_correlation_id = str(uuid.uuid4())
        logger.info(
            f"🚀 Executing {pipeline_name} pipeline with correlation ID: {request_correlation_id}"
        )

        # Send pipeline execution request
        # Pipeline names match PhaseName enum values directly - no mapping needed
        response = await self.service_manager.make_request(
            method="POST",
            service="api_gateway_service",
            path=f"/v1/batches/{self.batch_id}/pipelines",
            json={
                "batch_id": self.batch_id,
                "requested_pipeline": pipeline_name,
            },
            user=self.teacher_user,
            correlation_id=request_correlation_id,
        )

        if response.get("status") != "accepted":
            raise RuntimeError(f"Pipeline request not accepted: {response}")

        logger.info(f"✅ Pipeline request accepted: {response}")

        # Create execution tracker
        tracker = PipelineExecutionTracker()

        # Monitor pipeline execution with the NEW correlation ID for THIS pipeline
        completion_event = await KafkaMonitorHelper.monitor_pipeline_execution(
            consumer=self.consumer,
            request_correlation_id=request_correlation_id,
            batch_correlation_id=self.correlation_id,
            expected_steps=expected_steps,
            expected_completion_event=expected_completion_event,
            tracker=tracker,
            timeout_seconds=timeout_seconds,
        )

        # Prepare result
        result = PipelineExecutionResult(
            pipeline_name=pipeline_name,
            all_steps_completed=completion_event is not None,
            executed_steps=list(tracker.completed_phases),
            pruned_phases=tracker.pruned_phases,
            reused_storage_ids=tracker.reused_storage_ids,
            completion_event=completion_event,
            ras_result_event=tracker.ras_result_event,
            execution_time_seconds=time.time() - start_time,
        )

        # Update harness state
        self.completed_phases.update(tracker.completed_phases)
        self.storage_ids.update(tracker.storage_ids)

        # Validate phase pruning if requested
        if validate_phase_pruning and expected_pruned_phases:
            PipelineValidationHelper.validate_phase_pruning(
                expected_phases=expected_pruned_phases,
                executed_steps=set(result.executed_steps),
                pruned_phases=result.pruned_phases,
                reused_storage_ids=result.reused_storage_ids,
            )

        logger.info(
            f"📊 Pipeline {pipeline_name} execution complete. "
            f"Executed: {result.executed_steps}, Pruned: {result.pruned_phases}"
        )

        return result

    async def provision_credits(
        self,
        amount: int = 10000,
        provision_credits: bool = True,
    ) -> None:
        """
        Provision credits for test user to ensure pipelines can execute.

        Args:
            amount: Credit amount to provision (default 10000 is sufficient for most tests)
            provision_credits: Set to False to test credit denial scenarios
        """
        if not self.teacher_user:
            raise RuntimeError("Teacher user not initialized")
        if not self.correlation_id:
            raise RuntimeError("Correlation ID not initialized")

        await CreditProvisioningHelper.provision_credits(
            teacher_user=self.teacher_user,
            service_manager=self.service_manager,
            correlation_id=self.correlation_id,
            amount=amount,
            enabled=provision_credits,
        )

    async def cleanup(self) -> None:
        """Cleanup resources after test completion."""
        if self.consumer_context:
            await KafkaMonitorHelper.cleanup_consumer(self.consumer_context)
            self.consumer = None
            self.consumer_context = None

    # Private methods that delegate to helpers
    async def _wait_for_student_matching_events(
        self, timeout_seconds: int = 60
    ) -> Optional[dict[str, Any]]:
        """Monitor Phase 2 student matching events."""
        if not self.correlation_id:
            raise RuntimeError("Correlation ID not initialized")

        return await EventWaitingHelper.wait_for_student_matching_events(
            consumer=self.consumer,
            correlation_id=self.correlation_id,
            timeout_seconds=timeout_seconds,
        )

    async def _confirm_student_associations(self) -> dict[str, Any]:
        """Fetch suggested associations and confirm them as teacher."""
        if not self.teacher_user:
            raise RuntimeError("Teacher user not initialized")
        if not self.batch_id:
            raise RuntimeError("Batch ID not initialized")
        if not self.correlation_id:
            raise RuntimeError("Correlation ID not initialized")

        return await StudentManagementHelper.verify_student_associations(
            service_manager=self.service_manager,
            teacher_user=self.teacher_user,
            batch_id=self.batch_id,
            correlation_id=self.correlation_id,
        )

    async def _wait_for_guest_batch_ready(self, timeout_seconds: int = 10) -> bool:
        """Wait for BatchContentProvisioningCompleted event for GUEST batches."""
        if not self.correlation_id:
            raise RuntimeError("Correlation ID not initialized")

        return await EventWaitingHelper.wait_for_guest_batch_ready(
            consumer=self.consumer,
            correlation_id=self.correlation_id,
            timeout_seconds=timeout_seconds,
        )

    async def _wait_for_batch_essays_ready(self, timeout_seconds: int = 30) -> bool:
        """Wait for BatchEssaysReady event after associations are confirmed."""
        if not self.correlation_id:
            raise RuntimeError("Correlation ID not initialized")

        return await EventWaitingHelper.wait_for_batch_essays_ready(
            consumer=self.consumer,
            correlation_id=self.correlation_id,
            timeout_seconds=timeout_seconds,
        )

    def _validate_phase_pruning(
        self,
        expected_phases: list[str],
        executed_steps: set[str],
        pruned_phases: list[str],
        reused_storage_ids: dict[str, str],
    ) -> None:
        """Validate that phase pruning worked correctly."""
        PipelineValidationHelper.validate_phase_pruning(
            expected_phases=expected_phases,
            executed_steps=executed_steps,
            pruned_phases=pruned_phases,
            reused_storage_ids=reused_storage_ids,
        )
