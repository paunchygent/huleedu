"""
Pydantic models for commands FROM Batch Orchestrator Service TO Essay Lifecycle Service.

This module defines the command data structures that
the Batch Orchestrator Service sends to ELS to initiate various processing phases.
"""

from __future__ import annotations

from .domain_enums import CourseCode
from .events.base_event_models import BaseEventData
from .metadata_models import EssayProcessingInputRefV1

__all__ = [
    "BatchServiceAIFeedbackInitiateCommandDataV1",
    "BatchServiceCJAssessmentInitiateCommandDataV1",
    "BatchServiceNLPInitiateCommandDataV1",
    "BatchServiceSpellcheckInitiateCommandDataV1",
    "BatchServiceStudentMatchingInitiateCommandDataV1",
]


class BatchServiceSpellcheckInitiateCommandDataV1(BaseEventData):
    """
    Command to initiate Phase 2 spellcheck processing (first pipeline step).

    Publisher: Batch Orchestrator Service (BOS)
    Consumer: Essay Lifecycle Service (ELS)
    Topic: batch.service.spellcheck.initiate.command
    Handler: ELS - SpellcheckCommandHandler (dispatches to Spellcheck Service)

    Flow (both GUEST and REGULAR batches):
    1. Client requests pipeline execution via API
    2. BOS verifies batch is in READY_FOR_PIPELINE_EXECUTION state
    3. BOS publishes this command to start Phase 2 processing
    4. ELS forwards request to Spellcheck Service
    5. Pipeline processing begins

    Note: This is the first Phase 2 command after batch readiness is achieved.
    GUEST batches reach this state directly from BatchContentProvisioningCompletedV1.
    REGULAR batches reach this state after student associations are confirmed.
    """

    essays_to_process: list[EssayProcessingInputRefV1]
    language: str  # infered from course_code


class BatchServiceStudentMatchingInitiateCommandDataV1(BaseEventData):
    """
    Command to initiate Phase 1 student matching for REGULAR batches.

    Publisher: Batch Orchestrator Service (BOS)
    Consumer: Essay Lifecycle Service (ELS)
    Topic: batch.service.student.matching.initiate.command
    Handler: ELS - StudentMatchingCommandHandler.handle_student_matching_command()

    Flow (REGULAR batches only):
    1. BOS receives BatchContentProvisioningCompletedV1 from ELS
    2. BOS checks class_id exists (REGULAR batch)
    3. BOS publishes this command to ELS
    4. ELS marks batch as awaiting_student_associations
    5. ELS publishes BatchStudentMatchingRequestedV1 to NLP Service

    Note: GUEST batches never receive this command - they skip student matching entirely.
    """

    essays_to_process: list[EssayProcessingInputRefV1]
    class_id: str  # Class ID for roster lookup (always present for REGULAR batches)


class BatchServiceNLPInitiateCommandDataV1(BaseEventData):
    """Command data for Batch Orchestrator Service to initiate NLP phase for a batch."""

    essays_to_process: list[EssayProcessingInputRefV1]
    language: str  # inferred from course_code


class BatchServiceAIFeedbackInitiateCommandDataV1(BaseEventData):
    """Command data for AI feedback with personalization context from Class Management Service."""

    essays_to_process: list[EssayProcessingInputRefV1]
    language: str  # inferred from course_code

    # Orchestration context (from BOS lean registration)
    course_code: CourseCode  # from batch registration
    essay_instructions: str  # from batch registration

    # Personalization context (from Class Management Service via enhanced BatchEssaysReady)
    class_type: str  # GUEST or REGULAR - determines AI feedback template selection
    teacher_first_name: str | None = None  # For personalized templates - REGULAR classes only
    teacher_last_name: str | None = None  # For personalized templates - REGULAR classes only


class BatchServiceCJAssessmentInitiateCommandDataV1(BaseEventData):
    """Command data for CJ assessment with educational context from Class Management Service."""

    essays_to_process: list[EssayProcessingInputRefV1]
    language: str  # inferred from course_code

    # Orchestration context (from BOS lean registration)
    course_code: CourseCode  # from batch registration
    essay_instructions: str  # from batch registration

    # Educational context (from Class Management Service via enhanced BatchEssaysReady)
    # Note: CJ assessment works identically for GUEST and REGULAR classes
    class_type: str  # GUEST or REGULAR - for audit/reporting purposes only
