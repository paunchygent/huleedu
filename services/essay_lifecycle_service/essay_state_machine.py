"""
EssayStateMachine - Formal state machine for essay processing workflow.

This module implements a formal state machine using the transitions library to manage
essay status changes throughout the processing pipeline. It provides deterministic
state transitions driven by triggers corresponding to BOS commands and service results.
"""

from __future__ import annotations

from common_core.enums import EssayStatus
from transitions import Machine

# Define all trigger constants for clear interface
# Command triggers (from BOS commands)
CMD_INITIATE_SPELLCHECK = "CMD_INITIATE_SPELLCHECK"
CMD_INITIATE_AI_FEEDBACK = "CMD_INITIATE_AI_FEEDBACK"
CMD_INITIATE_CJ_ASSESSMENT = "CMD_INITIATE_CJ_ASSESSMENT"
CMD_INITIATE_NLP = "CMD_INITIATE_NLP"
CMD_MARK_PIPELINE_COMPLETE = "CMD_MARK_PIPELINE_COMPLETE"

# Event triggers (from specialized service results)
EVT_SPELLCHECK_STARTED = "EVT_SPELLCHECK_STARTED"
EVT_SPELLCHECK_SUCCEEDED = "EVT_SPELLCHECK_SUCCEEDED"
EVT_SPELLCHECK_FAILED = "EVT_SPELLCHECK_FAILED"

EVT_AI_FEEDBACK_STARTED = "EVT_AI_FEEDBACK_STARTED"
EVT_AI_FEEDBACK_SUCCEEDED = "EVT_AI_FEEDBACK_SUCCEEDED"
EVT_AI_FEEDBACK_FAILED = "EVT_AI_FEEDBACK_FAILED"

EVT_CJ_ASSESSMENT_STARTED = "EVT_CJ_ASSESSMENT_STARTED"
EVT_CJ_ASSESSMENT_SUCCEEDED = "EVT_CJ_ASSESSMENT_SUCCEEDED"
EVT_CJ_ASSESSMENT_FAILED = "EVT_CJ_ASSESSMENT_FAILED"

EVT_NLP_STARTED = "EVT_NLP_STARTED"
EVT_NLP_SUCCEEDED = "EVT_NLP_SUCCEEDED"
EVT_NLP_FAILED = "EVT_NLP_FAILED"

# Error triggers
EVT_CRITICAL_FAILURE = "EVT_CRITICAL_FAILURE"


class EssayStateMachine:
    """
    Formal state machine for essay processing workflow.

    Uses the transitions library to provide deterministic state transitions
    based on triggers from BOS commands and specialized service results.
    Maintains compatibility with existing EssayStatus enum.
    """

    def __init__(self, essay_id: str, initial_status: EssayStatus):
        """
        Initialize state machine for an essay.

        Args:
            essay_id: Unique identifier for the essay
            initial_status: Starting status from EssayStatus enum
        """
        self.essay_id = essay_id
        self._current_status = initial_status

        # Define all states using EssayStatus enum values
        states = [status.value for status in EssayStatus]

        # Define transitions with triggers
        transitions = [
            # Spellcheck workflow
            {
                'trigger': CMD_INITIATE_SPELLCHECK,
                'source': EssayStatus.READY_FOR_PROCESSING.value,
                'dest': EssayStatus.AWAITING_SPELLCHECK.value
            },
            {
                'trigger': EVT_SPELLCHECK_STARTED,
                'source': EssayStatus.AWAITING_SPELLCHECK.value,
                'dest': EssayStatus.SPELLCHECKING_IN_PROGRESS.value
            },
            {
                'trigger': EVT_SPELLCHECK_SUCCEEDED,
                'source': EssayStatus.SPELLCHECKING_IN_PROGRESS.value,
                'dest': EssayStatus.SPELLCHECKED_SUCCESS.value
            },
            {
                'trigger': EVT_SPELLCHECK_FAILED,
                'source': EssayStatus.SPELLCHECKING_IN_PROGRESS.value,
                'dest': EssayStatus.SPELLCHECK_FAILED.value
            },
            {
                'trigger': EVT_SPELLCHECK_FAILED,
                'source': EssayStatus.AWAITING_SPELLCHECK.value,
                'dest': EssayStatus.SPELLCHECK_FAILED.value
            },

            # AI Feedback workflow
            {
                'trigger': CMD_INITIATE_AI_FEEDBACK,
                'source': EssayStatus.SPELLCHECKED_SUCCESS.value,
                'dest': EssayStatus.AWAITING_AI_FEEDBACK.value
            },
            {
                'trigger': EVT_AI_FEEDBACK_STARTED,
                'source': EssayStatus.AWAITING_AI_FEEDBACK.value,
                'dest': EssayStatus.AI_FEEDBACK_IN_PROGRESS.value
            },
            {
                'trigger': EVT_AI_FEEDBACK_SUCCEEDED,
                'source': EssayStatus.AI_FEEDBACK_IN_PROGRESS.value,
                'dest': EssayStatus.AI_FEEDBACK_SUCCESS.value
            },
            {
                'trigger': EVT_AI_FEEDBACK_FAILED,
                'source': EssayStatus.AI_FEEDBACK_IN_PROGRESS.value,
                'dest': EssayStatus.AI_FEEDBACK_FAILED.value
            },
            {
                'trigger': EVT_AI_FEEDBACK_FAILED,
                'source': EssayStatus.AWAITING_AI_FEEDBACK.value,
                'dest': EssayStatus.AI_FEEDBACK_FAILED.value
            },

            # CJ Assessment workflow
            {
                'trigger': CMD_INITIATE_CJ_ASSESSMENT,
                'source': EssayStatus.SPELLCHECKED_SUCCESS.value,
                'dest': EssayStatus.AWAITING_CJ_ASSESSMENT.value
            },
            {
                'trigger': CMD_INITIATE_CJ_ASSESSMENT,
                'source': EssayStatus.AI_FEEDBACK_SUCCESS.value,
                'dest': EssayStatus.AWAITING_CJ_ASSESSMENT.value
            },
            {
                'trigger': EVT_CJ_ASSESSMENT_STARTED,
                'source': EssayStatus.AWAITING_CJ_ASSESSMENT.value,
                'dest': EssayStatus.CJ_ASSESSMENT_IN_PROGRESS.value
            },
            {
                'trigger': EVT_CJ_ASSESSMENT_SUCCEEDED,
                'source': EssayStatus.CJ_ASSESSMENT_IN_PROGRESS.value,
                'dest': EssayStatus.CJ_ASSESSMENT_SUCCESS.value
            },
            {
                'trigger': EVT_CJ_ASSESSMENT_FAILED,
                'source': EssayStatus.CJ_ASSESSMENT_IN_PROGRESS.value,
                'dest': EssayStatus.CJ_ASSESSMENT_FAILED.value
            },
            {
                'trigger': EVT_CJ_ASSESSMENT_FAILED,
                'source': EssayStatus.AWAITING_CJ_ASSESSMENT.value,
                'dest': EssayStatus.CJ_ASSESSMENT_FAILED.value
            },

            # NLP workflow
            {
                'trigger': CMD_INITIATE_NLP,
                'source': EssayStatus.SPELLCHECKED_SUCCESS.value,
                'dest': EssayStatus.AWAITING_NLP.value
            },
            {
                'trigger': CMD_INITIATE_NLP,
                'source': EssayStatus.AI_FEEDBACK_SUCCESS.value,
                'dest': EssayStatus.AWAITING_NLP.value
            },
            {
                'trigger': EVT_NLP_STARTED,
                'source': EssayStatus.AWAITING_NLP.value,
                'dest': EssayStatus.NLP_IN_PROGRESS.value
            },
            {
                'trigger': EVT_NLP_SUCCEEDED,
                'source': EssayStatus.NLP_IN_PROGRESS.value,
                'dest': EssayStatus.NLP_SUCCESS.value
            },
            {
                'trigger': EVT_NLP_FAILED,
                'source': EssayStatus.NLP_IN_PROGRESS.value,
                'dest': EssayStatus.NLP_FAILED.value
            },
            {
                'trigger': EVT_NLP_FAILED,
                'source': EssayStatus.AWAITING_NLP.value,
                'dest': EssayStatus.NLP_FAILED.value
            },

            # Pipeline completion
            {
                'trigger': CMD_MARK_PIPELINE_COMPLETE,
                'source': EssayStatus.SPELLCHECKED_SUCCESS.value,
                'dest': EssayStatus.ALL_PROCESSING_COMPLETED.value
            },
            {
                'trigger': CMD_MARK_PIPELINE_COMPLETE,
                'source': EssayStatus.AI_FEEDBACK_SUCCESS.value,
                'dest': EssayStatus.ALL_PROCESSING_COMPLETED.value
            },
            {
                'trigger': CMD_MARK_PIPELINE_COMPLETE,
                'source': EssayStatus.CJ_ASSESSMENT_SUCCESS.value,
                'dest': EssayStatus.ALL_PROCESSING_COMPLETED.value
            },
            {
                'trigger': CMD_MARK_PIPELINE_COMPLETE,
                'source': EssayStatus.NLP_SUCCESS.value,
                'dest': EssayStatus.ALL_PROCESSING_COMPLETED.value
            },

            # Critical failure from any state
            {
                'trigger': EVT_CRITICAL_FAILURE,
                'source': '*',  # Any state
                'dest': EssayStatus.ESSAY_CRITICAL_FAILURE.value
            }
        ]

        # Create the state machine
        self.machine = Machine(
            model=self,
            states=states,
            transitions=transitions,
            initial=initial_status.value,
            ignore_invalid_triggers=False  # Raise exceptions for invalid triggers
        )

    @property
    def current_status(self) -> EssayStatus:
        """Get current status as EssayStatus enum."""
        # The state is set on the model by the transitions library
        return EssayStatus(getattr(self, 'state', self._current_status.value))

    def trigger(self, trigger_name: str) -> bool:
        """
        Trigger a state transition.

        Args:
            trigger_name: Name of the trigger to fire

        Returns:
            True if transition succeeded, False otherwise
        """
        try:
            # Get the trigger method dynamically
            trigger_method = getattr(self, trigger_name, None)
            if trigger_method and callable(trigger_method):
                result = trigger_method()
                # transitions library methods return True on success, ensure boolean return
                return bool(result) if result is not None else True
            return False
        except Exception:
            return False

    def can_trigger(self, trigger_name: str) -> bool:
        """
        Check if a trigger can be fired from current state.

        Args:
            trigger_name: Name of the trigger to check

        Returns:
            True if trigger is valid from current state
        """
        try:
            # Use the machine's may_<trigger> methods
            may_method_name = f"may_{trigger_name}"
            may_method = getattr(self, may_method_name, None)
            if may_method and callable(may_method):
                result = may_method()
                return bool(result)
            return False
        except Exception:
            return False

    def get_valid_triggers(self) -> list[str]:
        """
        Get list of valid triggers from current state.

        Returns:
            List of trigger names that can be fired from current state
        """
        valid_triggers = []
        all_triggers = [
            CMD_INITIATE_SPELLCHECK, CMD_INITIATE_AI_FEEDBACK, CMD_INITIATE_CJ_ASSESSMENT,
            CMD_INITIATE_NLP, CMD_MARK_PIPELINE_COMPLETE,
            EVT_SPELLCHECK_STARTED, EVT_SPELLCHECK_SUCCEEDED, EVT_SPELLCHECK_FAILED,
            EVT_AI_FEEDBACK_STARTED, EVT_AI_FEEDBACK_SUCCEEDED, EVT_AI_FEEDBACK_FAILED,
            EVT_CJ_ASSESSMENT_STARTED, EVT_CJ_ASSESSMENT_SUCCEEDED, EVT_CJ_ASSESSMENT_FAILED,
            EVT_NLP_STARTED, EVT_NLP_SUCCEEDED, EVT_NLP_FAILED,
            EVT_CRITICAL_FAILURE
        ]

        for trigger_name in all_triggers:
            if self.can_trigger(trigger_name):
                valid_triggers.append(trigger_name)

        return valid_triggers

    # Convenience methods for common operations
    def cmd_initiate_spellcheck(self) -> bool:
        """Convenience method to initiate spellcheck."""
        return self.trigger(CMD_INITIATE_SPELLCHECK)

    def cmd_initiate_ai_feedback(self) -> bool:
        """Convenience method to initiate AI feedback."""
        return self.trigger(CMD_INITIATE_AI_FEEDBACK)

    def cmd_initiate_cj_assessment(self) -> bool:
        """Convenience method to initiate CJ assessment."""
        return self.trigger(CMD_INITIATE_CJ_ASSESSMENT)

    def cmd_mark_pipeline_complete(self) -> bool:
        """Convenience method to mark pipeline complete."""
        return self.trigger(CMD_MARK_PIPELINE_COMPLETE)

    def __str__(self) -> str:
        """String representation of the state machine."""
        return f"EssayStateMachine(essay_id={self.essay_id}, status={self.current_status.value})"

    def __repr__(self) -> str:
        """Detailed representation of the state machine."""
        return (
            f"EssayStateMachine(essay_id='{self.essay_id}', "
            f"current_status={self.current_status}, "
            f"valid_triggers={self.get_valid_triggers()})"
        )
