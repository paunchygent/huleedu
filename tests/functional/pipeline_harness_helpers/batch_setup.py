"""Batch setup helper for pipeline tests."""

import asyncio
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from common_core.domain_enums import CourseCode
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from tests.utils.auth_manager import AuthTestManager, AuthTestUser
    from tests.utils.kafka_test_manager import KafkaTestManager
    from tests.utils.service_test_manager import ServiceTestManager

logger = create_service_logger("test.batch_setup")


class BatchSetupHelper:
    """Helper class for setting up test batches."""

    def __init__(
        self,
        service_manager: "ServiceTestManager",
        kafka_manager: "KafkaTestManager",
        auth_manager: "AuthTestManager",
    ):
        """
        Initialize the batch setup helper.

        Args:
            service_manager: Service manager for API requests
            kafka_manager: Kafka manager for consumer operations
            auth_manager: Auth manager for user management
        """
        self.service_manager = service_manager
        self.kafka_manager = kafka_manager
        self.auth_manager = auth_manager

    async def setup_regular_batch_with_student_matching(
        self,
        essay_files: List[Path],
        class_id: str,
        teacher_user: "AuthTestUser",
        consumer: Any,
        provision_credits: bool = True,
    ) -> Tuple[str, str]:
        """
        Setup Phase 1: Create batch, upload essays, complete student matching.

        Args:
            essay_files: List of essay files to upload
            class_id: Class ID for the batch
            teacher_user: Teacher user for batch creation
            consumer: Kafka consumer instance
            provision_credits: Whether to provision credits

        Returns:
            Tuple of (batch_id, correlation_id)
        """
        # Import helpers to avoid circular dependency
        from tests.functional.pipeline_harness_helpers import (
            CreditProvisioningHelper,
            EventWaitingHelper,
            StudentManagementHelper,
        )

        # Generate correlation ID
        correlation_id = str(uuid.uuid4())
        logger.info(f"🔍 Test correlation ID: {correlation_id}")

        # Register batch WITH class_id (triggers REGULAR flow)
        logger.info(f"📝 Registering REGULAR batch with class_id: {class_id}")
        batch_id, actual_correlation_id = await self.service_manager.create_batch_via_agw(
            expected_essay_count=len(essay_files),
            course_code=CourseCode.ENG5,
            user=teacher_user,
            correlation_id=correlation_id,
            class_id=class_id,  # This triggers REGULAR flow!
        )

        # Update correlation ID to match service
        correlation_id = actual_correlation_id

        logger.info(f"✅ REGULAR batch registered: {batch_id}")
        logger.info(f"🔗 Monitoring events with correlation ID: {correlation_id}")

        # Upload real student essays
        logger.info("🚀 Uploading real student essays...")
        files_data = []
        for essay_file in essay_files:
            essay_content = essay_file.read_bytes()
            files_data.append({"name": essay_file.name, "content": essay_content})

        upload_result = await self.service_manager.upload_files(
            batch_id=batch_id,
            files=files_data,
            user=teacher_user,
            correlation_id=correlation_id,
            assignment_id=os.getenv("FUNCTIONAL_ASSIGNMENT_ID", "test_eng5_writing_2025"),
        )
        logger.info(f"✅ File upload successful: {upload_result}")

        # Wait for content provisioning to complete
        logger.info("⏳ Waiting for content provisioning...")
        await asyncio.sleep(3)

        # Wait for student matching events
        logger.info("⏳ Waiting for student matching to begin...")
        matching_event = await EventWaitingHelper.wait_for_student_matching_events(
            consumer=consumer,
            correlation_id=correlation_id,
            timeout_seconds=60,
        )

        if not matching_event:
            raise RuntimeError("Student matching events not received within timeout")

        # Give NLP service time to process and Class Management to store
        await asyncio.sleep(2)

        # Teacher confirms associations
        logger.info("👨‍🏫 Teacher reviewing and confirming student associations...")
        await StudentManagementHelper.verify_student_associations(
            service_manager=self.service_manager,
            teacher_user=teacher_user,
            batch_id=batch_id,
            correlation_id=correlation_id,
        )

        # Wait for BatchEssaysReady
        logger.info("⏳ Waiting for BatchEssaysReady after association confirmation...")
        ready_received = await EventWaitingHelper.wait_for_batch_essays_ready(
            consumer=consumer,
            correlation_id=correlation_id,
        )

        if not ready_received:
            raise RuntimeError("BatchEssaysReady not received after association confirmation")

        logger.info("✅ Batch ready for pipeline execution")

        # Provision credits to ensure pipeline preflight passes
        if provision_credits:
            await CreditProvisioningHelper.provision_credits(
                teacher_user=teacher_user,
                service_manager=self.service_manager,
                correlation_id=correlation_id,
            )

        return batch_id, correlation_id

    async def setup_guest_batch(
        self,
        essay_files: List[Path],
        consumer: Any,
        user: Optional["AuthTestUser"] = None,
        provision_credits: bool = True,
        attach_prompt: bool = True,
    ) -> Tuple[str, str, "AuthTestUser"]:
        """
        Setup a GUEST batch (no student matching) for pipeline testing.

        Args:
            essay_files: List of essay files to upload
            consumer: Kafka consumer instance
            user: Optional user for batch creation (creates guest user if not provided)
            provision_credits: Whether to provision credits

        Returns:
            Tuple of (batch_id, correlation_id, user)
        """
        # Import helpers to avoid circular dependency
        from tests.functional.pipeline_harness_helpers import (
            CreditProvisioningHelper,
            EventWaitingHelper,
        )

        # Create guest user if not provided
        if not user:
            user = self.auth_manager.create_test_user(role="guest")

        # Generate correlation ID
        correlation_id = str(uuid.uuid4())
        logger.info(f"🔍 Test correlation ID: {correlation_id}")

        # Register GUEST batch (NO class_id)
        logger.info("📝 Registering GUEST batch (no class_id)")
        batch_id, actual_correlation_id = await self.service_manager.create_batch_via_agw(
            expected_essay_count=len(essay_files),
            course_code=CourseCode.ENG5,
            user=user,
            correlation_id=correlation_id,
            attach_prompt=attach_prompt,
            # NO class_id - this triggers GUEST flow!
        )

        # Update correlation ID to match service
        correlation_id = actual_correlation_id

        logger.info(f"✅ GUEST batch registered: {batch_id}")

        # Upload essays
        logger.info("🚀 Uploading essays for GUEST batch...")
        files_data = []
        for essay_file in essay_files:
            essay_content = essay_file.read_bytes()
            files_data.append({"name": essay_file.name, "content": essay_content})

        upload_result = await self.service_manager.upload_files(
            batch_id=batch_id,
            files=files_data,
            user=user,
            correlation_id=correlation_id,
            assignment_id=os.getenv("FUNCTIONAL_ASSIGNMENT_ID", "test_eng5_writing_2025"),
        )
        logger.info(f"✅ File upload successful: {upload_result}")

        # Wait for content provisioning and batch to be ready
        logger.info("⏳ Waiting for GUEST batch to be ready...")
        await asyncio.sleep(2)  # Small delay for initial processing

        # For GUEST batches, wait for BatchContentProvisioningCompleted
        ready_received = await EventWaitingHelper.wait_for_guest_batch_ready(
            consumer=consumer,
            correlation_id=correlation_id,
            timeout_seconds=5,
        )

        if not ready_received:
            logger.warning("BatchContentProvisioningCompleted not received, but continuing...")

        logger.info("✅ GUEST batch ready for pipeline execution")

        # Provision credits to ensure pipeline preflight passes
        if provision_credits:
            await CreditProvisioningHelper.provision_credits(
                teacher_user=user,
                service_manager=self.service_manager,
                correlation_id=correlation_id,
            )

        return batch_id, correlation_id, user
