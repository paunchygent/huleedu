"""
Shared utilities for essay state machine tests.

Common imports, constants, and utilities used across all essay state machine
test modules to avoid duplication and maintain consistency.
"""

from __future__ import annotations

from common_core.status_enums import EssayStatus

from essay_state_machine import (
    CMD_INITIATE_AI_FEEDBACK,
    CMD_INITIATE_CJ_ASSESSMENT,
    CMD_INITIATE_NLP,
    CMD_INITIATE_SPELLCHECK,
    CMD_MARK_PIPELINE_COMPLETE,
    EVT_AI_FEEDBACK_FAILED,
    EVT_AI_FEEDBACK_STARTED,
    EVT_AI_FEEDBACK_SUCCEEDED,
    EVT_CJ_ASSESSMENT_FAILED,
    EVT_CJ_ASSESSMENT_STARTED,
    EVT_CJ_ASSESSMENT_SUCCEEDED,
    EVT_CRITICAL_FAILURE,
    EVT_NLP_STARTED,
    EVT_NLP_SUCCEEDED,
    EVT_SPELLCHECK_FAILED,
    EVT_SPELLCHECK_STARTED,
    EVT_SPELLCHECK_SUCCEEDED,
    EssayStateMachine,
)

# Export all constants and classes for test modules
__all__ = [
    "EssayStatus",
    "EssayStateMachine",
    "CMD_INITIATE_AI_FEEDBACK",
    "CMD_INITIATE_CJ_ASSESSMENT",
    "CMD_INITIATE_NLP",
    "CMD_INITIATE_SPELLCHECK",
    "CMD_MARK_PIPELINE_COMPLETE",
    "EVT_AI_FEEDBACK_FAILED",
    "EVT_AI_FEEDBACK_STARTED",
    "EVT_AI_FEEDBACK_SUCCEEDED",
    "EVT_CJ_ASSESSMENT_FAILED",
    "EVT_CJ_ASSESSMENT_STARTED",
    "EVT_CJ_ASSESSMENT_SUCCEEDED",
    "EVT_CRITICAL_FAILURE",
    "EVT_NLP_STARTED",
    "EVT_NLP_SUCCEEDED",
    "EVT_SPELLCHECK_FAILED",
    "EVT_SPELLCHECK_STARTED",
    "EVT_SPELLCHECK_SUCCEEDED",
]
