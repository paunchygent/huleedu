This is an excellent direction for creating a flexible and maintainable pipeline system. By making BOS the "brains" of the pipeline sequence and using a formal state machine library like `transitions` within ELS, we can achieve the "mix and match" capability without ELS's `core_logic.py` becoming overly complex.

Here's a potential full implementation concept, outlining changes in `common_core` (minor), ELS (significant, including the new state machine file), and BOS (focused on orchestration logic).

## I. Common Core (`common_core`)

Your `common_core` package is already quite well-equipped.

1. **`EssayStatus` Enum (`common_core/src/common_core/enums.py`)**: Ensure all necessary states as discussed previously are present (e.g., `AWAITING_AI_FEEDBACK`, `AI_FEEDBACK_IN_PROGRESS`, `AI_FEEDBACK_SUCCESS`, `AI_FEEDBACK_FAILED`, and similarly for NLP, CJ Assessment, and `ALL_PROCESSING_COMPLETED`). This was covered in the previous response.
2. **`ProcessingPipelineState` (`common_core/src/common_core/pipeline_models.py`)**: This model is key for BOS. BOS will use `requested_pipelines: List[str]` to store the desired sequence of stages (e.g., `["spellcheck", "ai_feedback", "nlp"]`) and update the corresponding `PipelineStateDetail` fields (e.g., `spellcheck`, `ai_feedback`) as stages are initiated and completed.
3. **Command and Event Models**: Ensure all necessary Pydantic models for BOS->ELS commands (e.g., `BatchServiceAIFeedbackInitiateCommandDataV1`) and ELS->SpecializedService requests/results are defined. These largely exist.

No major new files are anticipated for `common_core` for this specific change, mostly ensuring the enums are complete.

## II. Essay Lifecycle Service (ELS) Changes

ELS will see the most structural change internally for state management.

### 1. New File: `services/essay_lifecycle_service/essay_state_machine.py`

This file will house the state machine definition using the `transitions` library.

```python
# services/essay_lifecycle_service/essay_state_machine.py
"""
Defines the state machine for an individual essay's lifecycle using the 'transitions' library.
"""
from __future__ import annotations

from typing import Any

from transitions import Machine, State
from common_core.enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("els.essay_state_machine")

# --- Define State Names from Enum ---
# Helper to create State objects with on_enter/on_exit if needed later
# For now, just using string values of the enum for states.
state_values: list[str] = [s.value for s in EssayStatus]

# --- Define Triggers (Events that cause state transitions) ---
# These correspond to BOS commands or results from specialized services
# Using a more descriptive naming convention for triggers
# Format: <SOURCE>_<ACTION>_<TARGET_PHASE_OR_STATUS>
# SOURCE: CMD (command from BOS), EVT (event from specialized service)

# Triggers for BOS Commands
CMD_INITIATE_SPELLCHECK: str = "CMD_INITIATE_SPELLCHECK"
CMD_INITIATE_AI_FEEDBACK: str = "CMD_INITIATE_AI_FEEDBACK"
CMD_INITIATE_CJ_ASSESSMENT: str = "CMD_INITIATE_CJ_ASSESSMENT"
CMD_INITIATE_NLP: str = "CMD_INITIATE_NLP"
CMD_MARK_PIPELINE_COMPLETE: str = "CMD_MARK_PIPELINE_COMPLETE" # If BOS determines no more steps
CMD_RETRY_SPELLCHECK: str = "CMD_RETRY_SPELLCHECK"
CMD_RETRY_AI_FEEDBACK: str = "CMD_RETRY_AI_FEEDBACK"
CMD_RETRY_CJ_ASSESSMENT: str = "CMD_RETRY_CJ_ASSESSMENT"
CMD_RETRY_NLP: str = "CMD_RETRY_NLP"
CMD_FORCE_FAILURE: str = "CMD_FORCE_FAILURE" # Generic command to fail an essay

# Triggers for Events from Specialized Services (Internal ELS events representing external results)
EVT_SPELLCHECK_STARTED: str = "EVT_SPELLCHECK_STARTED"
EVT_SPELLCHECK_SUCCEEDED: str = "EVT_SPELLCHECK_SUCCEEDED"
EVT_SPELLCHECK_FAILED: str = "EVT_SPELLCHECK_FAILED"

EVT_AI_FEEDBACK_STARTED: str = "EVT_AI_FEEDBACK_STARTED"
EVT_AI_FEEDBACK_SUCCEEDED: str = "EVT_AI_FEEDBACK_SUCCEEDED"
EVT_AI_FEEDBACK_FAILED: str = "EVT_AI_FEEDBACK_FAILED"

EVT_CJ_ASSESSMENT_STARTED: str = "EVT_CJ_ASSESSMENT_STARTED"
EVT_CJ_ASSESSMENT_SUCCEEDED: str = "EVT_CJ_ASSESSMENT_SUCCEEDED"
EVT_CJ_ASSESSMENT_FAILED: str = "EVT_CJ_ASSESSMENT_FAILED"

EVT_NLP_STARTED: str = "EVT_NLP_STARTED"
EVT_NLP_SUCCEEDED: str = "EVT_NLP_SUCCEEDED"
EVT_NLP_FAILED: str = "EVT_NLP_FAILED"


class EssayStateMachine:
    """
    Manages the state and transitions of an individual essay using the 'transitions' library.
    The actual sequence of pipeline stages (e.g., spellcheck then AI feedback)
    is determined by BOS sending specific commands (triggers).
    """

    def __init__(self: EssayStateMachine, essay_id: str, initial_status: EssayStatus) -> None:
        """
        Initializes the EssayStateMachine.

        Args:
            essay_id: The unique identifier for the essay.
            initial_status: The starting status of the essay.
        """
        self.essay_id: str = essay_id
        self._current_status_enum: EssayStatus = initial_status # For type safety with our enum

        # Define all transitions.
        # The 'source' can be a single state or a list of states.
        # 'dest' is the target state.
        # 'conditions' or 'unless' can be used to guard transitions.
        # Callbacks like 'before', 'after', 'prepare' can be added.
        transitions = [
            # --- From READY_FOR_PROCESSING (initial commands from BOS) ---
            {'trigger': CMD_INITIATE_SPELLCHECK, 'source': EssayStatus.READY_FOR_PROCESSING.value, 'dest': EssayStatus.AWAITING_SPELLCHECK.value},
            {'trigger': CMD_INITIATE_AI_FEEDBACK, 'source': EssayStatus.READY_FOR_PROCESSING.value, 'dest': EssayStatus.AWAITING_AI_FEEDBACK.value},
            {'trigger': CMD_INITIATE_CJ_ASSESSMENT, 'source': EssayStatus.READY_FOR_PROCESSING.value, 'dest': EssayStatus.AWAITING_CJ_ASSESSMENT.value},
            {'trigger': CMD_INITIATE_NLP, 'source': EssayStatus.READY_FOR_PROCESSING.value, 'dest': EssayStatus.AWAITING_NLP.value},
            {'trigger': CMD_MARK_PIPELINE_COMPLETE, 'source': EssayStatus.READY_FOR_PROCESSING.value, 'dest': EssayStatus.ALL_PROCESSING_COMPLETED.value},

            # --- Spellcheck Lifecycle ---
            {'trigger': EVT_SPELLCHECK_STARTED, 'source': EssayStatus.AWAITING_SPELLCHECK.value, 'dest': EssayStatus.SPELLCHECKING_IN_PROGRESS.value},
            {'trigger': EVT_SPELLCHECK_SUCCEEDED, 'source': EssayStatus.SPELLCHECKING_IN_PROGRESS.value, 'dest': EssayStatus.SPELLCHECKED_SUCCESS.value},
            {'trigger': EVT_SPELLCHECK_FAILED, 'source': [EssayStatus.AWAITING_SPELLCHECK.value, EssayStatus.SPELLCHECKING_IN_PROGRESS.value], 'dest': EssayStatus.SPELLCHECK_FAILED.value},
            {'trigger': CMD_RETRY_SPELLCHECK, 'source': EssayStatus.SPELLCHECK_FAILED.value, 'dest': EssayStatus.AWAITING_SPELLCHECK.value},

            # --- Transitions from SPELLCHECKED_SUCCESS (to next stage commanded by BOS) ---
            {'trigger': CMD_INITIATE_AI_FEEDBACK, 'source': EssayStatus.SPELLCHECKED_SUCCESS.value, 'dest': EssayStatus.AWAITING_AI_FEEDBACK.value},
            {'trigger': CMD_INITIATE_CJ_ASSESSMENT, 'source': EssayStatus.SPELLCHECKED_SUCCESS.value, 'dest': EssayStatus.AWAITING_CJ_ASSESSMENT.value},
            {'trigger': CMD_INITIATE_NLP, 'source': EssayStatus.SPELLCHECKED_SUCCESS.value, 'dest': EssayStatus.AWAITING_NLP.value},
            {'trigger': CMD_MARK_PIPELINE_COMPLETE, 'source': EssayStatus.SPELLCHECKED_SUCCESS.value, 'dest': EssayStatus.ALL_PROCESSING_COMPLETED.value},

            # --- AI Feedback Lifecycle ---
            {'trigger': EVT_AI_FEEDBACK_STARTED, 'source': EssayStatus.AWAITING_AI_FEEDBACK.value, 'dest': EssayStatus.AI_FEEDBACK_IN_PROGRESS.value},
            {'trigger': EVT_AI_FEEDBACK_SUCCEEDED, 'source': EssayStatus.AI_FEEDBACK_IN_PROGRESS.value, 'dest': EssayStatus.AI_FEEDBACK_SUCCESS.value},
            {'trigger': EVT_AI_FEEDBACK_FAILED, 'source': [EssayStatus.AWAITING_AI_FEEDBACK.value, EssayStatus.AI_FEEDBACK_IN_PROGRESS.value], 'dest': EssayStatus.AI_FEEDBACK_FAILED.value},
            {'trigger': CMD_RETRY_AI_FEEDBACK, 'source': EssayStatus.AI_FEEDBACK_FAILED.value, 'dest': EssayStatus.AWAITING_AI_FEEDBACK.value},

            # --- Transitions from AI_FEEDBACK_SUCCESS ---
            {'trigger': CMD_INITIATE_SPELLCHECK, 'source': EssayStatus.AI_FEEDBACK_SUCCESS.value, 'dest': EssayStatus.AWAITING_SPELLCHECK.value}, # Example: re-spellcheck
            {'trigger': CMD_INITIATE_CJ_ASSESSMENT, 'source': EssayStatus.AI_FEEDBACK_SUCCESS.value, 'dest': EssayStatus.AWAITING_CJ_ASSESSMENT.value},
            {'trigger': CMD_INITIATE_NLP, 'source': EssayStatus.AI_FEEDBACK_SUCCESS.value, 'dest': EssayStatus.AWAITING_NLP.value},
            {'trigger': CMD_MARK_PIPELINE_COMPLETE, 'source': EssayStatus.AI_FEEDBACK_SUCCESS.value, 'dest': EssayStatus.ALL_PROCESSING_COMPLETED.value},

            # --- CJ Assessment Lifecycle (similar pattern) ---
            {'trigger': EVT_CJ_ASSESSMENT_STARTED, 'source': EssayStatus.AWAITING_CJ_ASSESSMENT.value, 'dest': EssayStatus.CJ_ASSESSMENT_IN_PROGRESS.value},
            {'trigger': EVT_CJ_ASSESSMENT_SUCCEEDED, 'source': EssayStatus.CJ_ASSESSMENT_IN_PROGRESS.value, 'dest': EssayStatus.CJ_ASSESSMENT_SUCCESS.value},
            {'trigger': EVT_CJ_ASSESSMENT_FAILED, 'source': [EssayStatus.AWAITING_CJ_ASSESSMENT.value, EssayStatus.CJ_ASSESSMENT_IN_PROGRESS.value], 'dest': EssayStatus.CJ_ASSESSMENT_FAILED.value},
            {'trigger': CMD_RETRY_CJ_ASSESSMENT, 'source': EssayStatus.CJ_ASSESSMENT_FAILED.value, 'dest': EssayStatus.AWAITING_CJ_ASSESSMENT.value},

            # --- Transitions from CJ_ASSESSMENT_SUCCESS ---
            {'trigger': CMD_INITIATE_SPELLCHECK, 'source': EssayStatus.CJ_ASSESSMENT_SUCCESS.value, 'dest': EssayStatus.AWAITING_SPELLCHECK.value},
            {'trigger': CMD_INITIATE_AI_FEEDBACK, 'source': EssayStatus.CJ_ASSESSMENT_SUCCESS.value, 'dest': EssayStatus.AWAITING_AI_FEEDBACK.value},
            {'trigger': CMD_INITIATE_NLP, 'source': EssayStatus.CJ_ASSESSMENT_SUCCESS.value, 'dest': EssayStatus.AWAITING_NLP.value},
            {'trigger': CMD_MARK_PIPELINE_COMPLETE, 'source': EssayStatus.CJ_ASSESSMENT_SUCCESS.value, 'dest': EssayStatus.ALL_PROCESSING_COMPLETED.value},

            # --- NLP Lifecycle (similar pattern) ---
            {'trigger': EVT_NLP_STARTED, 'source': EssayStatus.AWAITING_NLP.value, 'dest': EssayStatus.NLP_IN_PROGRESS.value},
            {'trigger': EVT_NLP_SUCCEEDED, 'source': EssayStatus.NLP_IN_PROGRESS.value, 'dest': EssayStatus.NLP_SUCCESS.value},
            {'trigger': EVT_NLP_FAILED, 'source': [EssayStatus.AWAITING_NLP.value, EssayStatus.NLP_IN_PROGRESS.value], 'dest': EssayStatus.NLP_FAILED.value},
            {'trigger': CMD_RETRY_NLP, 'source': EssayStatus.NLP_FAILED.value, 'dest': EssayStatus.AWAITING_NLP.value},
            
            # --- Transitions from NLP_SUCCESS ---
            {'trigger': CMD_INITIATE_SPELLCHECK, 'source': EssayStatus.NLP_SUCCESS.value, 'dest': EssayStatus.AWAITING_SPELLCHECK.value},
            {'trigger': CMD_INITIATE_AI_FEEDBACK, 'source': EssayStatus.NLP_SUCCESS.value, 'dest': EssayStatus.AWAITING_AI_FEEDBACK.value},
            {'trigger': CMD_INITIATE_CJ_ASSESSMENT, 'source': EssayStatus.NLP_SUCCESS.value, 'dest': EssayStatus.AWAITING_CJ_ASSESSMENT.value},
            {'trigger': CMD_MARK_PIPELINE_COMPLETE, 'source': EssayStatus.NLP_SUCCESS.value, 'dest': EssayStatus.ALL_PROCESSING_COMPLETED.value},

            # --- Generic Failure Transition (can be triggered from many states) ---
            # This allows any active state to be forced into critical failure by BOS
            # '*' source means any state. Use with caution or list specific sources.
            {'trigger': CMD_FORCE_FAILURE, 'source': '*', 'dest': EssayStatus.ESSAY_CRITICAL_FAILURE.value},
        ]

        self.machine: Machine = Machine(
            model=self,
            states=state_values, # Uses string values of EssayStatus
            transitions=transitions,
            initial=initial_status.value, # Machine state is stored as string
            auto_transitions=False, # We explicitly call trigger methods
            after_state_change='_update_current_status_enum' # Keep our enum in sync
        )
        self._update_current_status_enum() # Initialize after machine setup

    def _update_current_status_enum(self: EssayStateMachine) -> None:
        """Keeps the internal _current_status_enum in sync with the machine's string state."""
        try:
            self._current_status_enum = EssayStatus(self.state) # self.state is from Machine
        except ValueError:
            logger.error(f"Essay {self.essay_id}: Invalid state '{self.state}' from machine.")
            # Potentially fall back to a default/error state or raise
            self._current_status_enum = EssayStatus.ESSAY_CRITICAL_FAILURE


    @property
    def current_status(self: EssayStateMachine) -> EssayStatus:
        """Returns the current status as an EssayStatus enum member."""
        return self._current_status_enum

    def can_trigger(self: EssayStateMachine, trigger_name: str) -> bool:
        """Checks if a named trigger can be fired from the current state."""
        return self.machine.may_trigger(trigger_name)

    def trigger(self: EssayStateMachine, trigger_name: str, **kwargs: Any) -> bool:
        """
        Fires a named trigger, causing a state transition if valid.

        Args:
            trigger_name: The name of the trigger event.
            **kwargs: Optional arguments to pass to transition callbacks.

        Returns:
            True if the transition occurred, False otherwise.
        """
        if not hasattr(self.machine, trigger_name):
            logger.error(f"Essay {self.essay_id}: Trigger '{trigger_name}' not defined on state machine.")
            return False
        
        # The trigger method on the machine is named after the trigger string
        trigger_method = getattr(self.machine, trigger_name)
        result: bool = trigger_method(**kwargs)
        if result:
            logger.info(f"Essay {self.essay_id}: State transitioned to '{self.state}' via trigger '{trigger_name}'.")
        else:
            logger.warning(f"Essay {self.essay_id}: Trigger '{trigger_name}' failed to transition from state '{self.state}'.")
        return result

    # Convenience methods for each trigger (optional, but can be nice for type hinting and clarity)
    # Example for one trigger:
    def cmd_initiate_spellcheck(self: EssayStateMachine, **kwargs: Any) -> bool:
        """Attempts to transition to AWAITING_SPELLCHECK based on BOS command."""
        return self.trigger(CMD_INITIATE_SPELLCHECK, **kwargs)

    # ... Add similar convenience methods for all other defined triggers ...
    # For example:
    def evt_spellcheck_succeeded(self: EssayStateMachine, **kwargs: Any) -> bool:
        return self.trigger(EVT_SPELLCHECK_SUCCEEDED, **kwargs)

    def cmd_initiate_ai_feedback(self: EssayStateMachine, **kwargs: Any) -> bool:
        return self.trigger(CMD_INITIATE_AI_FEEDBACK, **kwargs)

```

### 2. Update `services/essay_lifecycle_service/core_logic.py`

The `StateTransitionValidator` will now use the `EssayStateMachine`.

```python
# services/essay_lifecycle_service/core_logic.py
from __future__ import annotations

from typing import TYPE_CHECKING # If using for types not directly instantiated
from uuid import UUID, uuid4

from common_core.enums import EssayStatus
from common_core.metadata_models import EntityReference
# Import the new state machine and its trigger constants
from .essay_state_machine import (
    CMD_FORCE_FAILURE, # Assuming you add this trigger too
    EssayStateMachine
)


class StateTransitionValidator:
    """
    Validates essay state transitions by deferring to the EssayStateMachine.
    """

    def validate_transition(
        self: StateTransitionValidator,
        current_machine_state: EssayStateMachine, # Pass the machine instance
        target_trigger_name: str # The trigger name corresponding to the desired transition
    ) -> bool:
        """
        Validate if a named trigger can transition the essay from its current state.

        Args:
            current_machine_state: The EssayStateMachine instance for the essay.
            target_trigger_name: The string name of the trigger to attempt.

        Returns:
            True if the trigger is valid from the current state, False otherwise.
        """
        return current_machine_state.can_trigger(target_trigger_name)

    def get_possible_triggers(
        self: StateTransitionValidator,
        current_machine_state: EssayStateMachine
    ) -> list[str]:
        """
        Get list of valid triggers from the essay's current state.

        Args:
            current_machine_state: The EssayStateMachine instance for the essay.
        
        Returns:
            A list of trigger names that can be fired from the current state.
        """
        # The `transitions` library provides `get_triggers` on the machine model
        return current_machine_state.machine.get_triggers(current_machine_state.state)


    @classmethod
    def is_terminal_status(cls: type[StateTransitionValidator], status: EssayStatus) -> bool:
        """Check if a status is terminal (no further *processing* transitions allowed)."""
        # ALL_PROCESSING_COMPLETED is now the main terminal success state
        return status in {
            EssayStatus.ALL_PROCESSING_COMPLETED,
            EssayStatus.ESSAY_CRITICAL_FAILURE,
        }
    # ... (other helper methods like is_failure_status, is_processing_status remain similar)
# ... (generate_correlation_id, create_entity_reference remain the same)
```

### 3. Update `services/essay_lifecycle_service/state_store.py`

The `SQLiteEssayStateStore` will primarily store `EssayState.current_status` as a string. The `EssayStateMachine` will be instantiated in memory when logic needs to be applied.

```python
# services/essay_lifecycle_service/state_store.py
# ... (imports for EssayState Pydantic model, json, datetime, aiosqlite, etc.)
from common_core.enums import EssayStatus # Make sure it's imported
from .essay_state_machine import EssayStateMachine # For type hinting if needed

# ... (EssayState Pydantic model remains largely the same, storing current_status as EssayStatus)

class SQLiteEssayStateStore:
    # ... (init, initialize, etc. largely the same)

    async def get_essay_state(self: SQLiteEssayStateStore, essay_id: str) -> EssayState | None:
        # ... (implementation remains similar, fetches and reconstructs Pydantic EssayState)
        # The current_status field will be an EssayStatus enum member.
        pass

    async def update_essay_status_via_machine(
        self: SQLiteEssayStateStore,
        essay_id: str,
        new_status_from_machine: EssayStatus, # Status comes from the machine after successful trigger
        processing_metadata_update: dict[str, Any] | None = None,
    ) -> None:
        """
        Updates the essay's status in the database based on a new status
        determined by the EssayStateMachine. Also updates timeline and metadata.
        """
        async with aiosqlite.connect(self.database_path, timeout=self.timeout) as db:
            current_pydantic_state = await self.get_essay_state(essay_id)
            if current_pydantic_state is None:
                # This should ideally not happen if machine was based on existing state
                raise ValueError(f"Essay {essay_id} not found for status update.")

            now_utc = datetime.now(UTC)
            current_pydantic_state.current_status = new_status_from_machine
            current_pydantic_state.updated_at = now_utc
            current_pydantic_state.timeline[new_status_from_machine.value] = now_utc

            if processing_metadata_update:
                current_pydantic_state.processing_metadata.update(processing_metadata_update)

            await db.execute(
                """
                UPDATE essay_states
                SET current_status = ?, processing_metadata = ?, timeline = ?, updated_at = ?
                WHERE essay_id = ?
                """,
                (
                    current_pydantic_state.current_status.value,
                    json.dumps(current_pydantic_state.processing_metadata),
                    json.dumps({k: v.isoformat() for k, v in current_pydantic_state.timeline.items()}),
                    current_pydantic_state.updated_at.isoformat(),
                    essay_id,
                ),
            )
            await db.commit()
            logger.info(f"Persisted new status '{new_status_from_machine.value}' for essay {essay_id}")

    # create_essay_record will set an initial status, e.g., EssayStatus.READY_FOR_PROCESSING
    # create_or_update_essay_state_for_slot_assignment also sets an initial status.
    # These initial statuses will be the entry point for the EssayStateMachine.
```

### 4. Update `services/essay_lifecycle_service/batch_command_handlers.py`

This is where ELS receives commands from BOS or results from specialized services and uses the `EssayStateMachine`.

```python
# services/essay_lifecycle_service/batch_command_handlers.py
# ... (imports)
from .essay_state_machine import (
    CMD_INITIATE_AI_FEEDBACK, # Import all relevant CMD_* triggers
    CMD_INITIATE_CJ_ASSESSMENT,
    CMD_INITIATE_NLP,
    CMD_INITIATE_SPELLCHECK,
    EVT_AI_FEEDBACK_SUCCEEDED, # Import all relevant EVT_* triggers
    EVT_AI_FEEDBACK_FAILED,
    # ... etc.
    EssayStateMachine,
)
from .protocols import ( # Ensure all dependencies are protocol-based
    BatchCommandHandler as BatchCommandHandlerProtocol, # Alias if needed
    BatchEssayTracker,
    EssayStateStore,
    EventPublisher,
    MetricsCollector,
    # StateTransitionValidator, # This might be less used directly if logic moves to machine
)


# The main process_single_message function will need to be adapted.
# When handling a BOS command for a batch:
async def _handle_batch_spellcheck_initiate_command(
    envelope: EventEnvelope[BatchServiceSpellcheckInitiateCommandDataV1], # Specific command type
    state_store: EssayStateStore,
    # transition_validator: StateTransitionValidator, # May not be needed directly
    event_publisher: EventPublisher, # For dispatching to Spell Checker
    # ... other necessary dependencies
    correlation_id: UUID | None,
) -> bool:
    command_data = BatchServiceSpellcheckInitiateCommandDataV1.model_validate(envelope.data)
    batch_id = command_data.entity_ref.entity_id
    logger.info(f"Handling BOS command CMD_INITIATE_SPELLCHECK for batch {batch_id}")
    
    success_all_essays = True
    for essay_input_ref in command_data.essays_to_process:
        essay_id = essay_input_ref.essay_id
        pydantic_essay_state = await state_store.get_essay_state(essay_id)

        if not pydantic_essay_state:
            logger.error(f"Essay {essay_id} not found for CMD_INITIATE_SPELLCHECK.")
            success_all_essays = False
            continue

        # Instantiate the state machine for this essay with its current status
        essay_machine = EssayStateMachine(essay_id, pydantic_essay_state.current_status)

        # Attempt to trigger the transition
        if essay_machine.trigger(CMD_INITIATE_SPELLCHECK): # Or essay_machine.cmd_initiate_spellcheck()
            # Persist the new state
            await state_store.update_essay_status_via_machine(
                essay_id,
                essay_machine.current_status, # Get the new status from the machine
                {"spellcheck_initiated_by_bos": True} # Example metadata
            )
            # Now, dispatch to Spell Checker Service using event_publisher
            # (This part uses SpecializedServiceRequestDispatcher logic, not shown here for brevity)
            # await event_publisher.dispatch_spellcheck_requests(...)
            logger.info(f"Essay {essay_id} transitioned to {essay_machine.current_status.value} and request dispatched.")
        else:
            logger.warning(f"Essay {essay_id} could not transition via {CMD_INITIATE_SPELLCHECK} from {pydantic_essay_state.current_status.value}.")
            success_all_essays = False
            # Potentially publish a failure/warning event back to BOS or log extensively

    return success_all_essays


# When handling a result from a specialized service (e.g., SpellcheckResultDataV1):
async def _handle_spellcheck_result_event(
    envelope: EventEnvelope[SpellcheckResultDataV1], # Specific result type
    state_store: EssayStateStore,
    event_publisher: EventPublisher, # For notifying BOS
    correlation_id: UUID | None,
) -> bool:
    result_data = SpellcheckResultDataV1.model_validate(envelope.data)
    essay_id = result_data.entity_ref.entity_id
    logger.info(f"Handling spellcheck result for essay {essay_id}, status: {result_data.status.value}")

    pydantic_essay_state = await state_store.get_essay_state(essay_id)
    if not pydantic_essay_state:
        logger.error(f"Essay {essay_id} not found for spellcheck result.")
        return False # Or True to ack message if non-recoverable

    essay_machine = EssayStateMachine(essay_id, pydantic_essay_state.current_status)
    
    trigger_to_fire = ""
    if result_data.status == EssayStatus.SPELLCHECKED_SUCCESS:
        trigger_to_fire = EVT_SPELLCHECK_SUCCEEDED
    elif result_data.status == EssayStatus.SPELLCHECK_FAILED:
        trigger_to_fire = EVT_SPELLCHECK_FAILED
    else:
        logger.warning(f"Unknown status {result_data.status.value} in spellcheck result for {essay_id}.")
        return True # Acknowledge message

    if essay_machine.trigger(trigger_to_fire):
        await state_store.update_essay_status_via_machine(
            essay_id,
            essay_machine.current_status,
            {"spellcheck_result_received": True}
        )
        # Notify BOS of phase completion for this essay/batch
        # This logic would involve checking if all essays in a phase for a batch are done
        # and then using event_publisher.publish_batch_phase_progress/concluded
        logger.info(f"Essay {essay_id} updated to {essay_machine.current_status.value} after spellcheck result.")
        return True
    else:
        logger.warning(f"Essay {essay_id} could not transition via {trigger_to_fire} from {pydantic_essay_state.current_status.value}.")
        return True # Acknowledge message, but indicates a state logic issue
```

**Note**: The `process_single_message` in `batch_command_handlers.py` would need to be refactored to correctly route different event types (BOS commands vs. Specialized Service results) to these new handlers, which then use the `EssayStateMachine`.

### 5. `services/essay_lifecycle_service/di.py`

No major changes expected here, as `EssayStateMachine` is instantiated on-the-fly. `EssayStateStore` and `EventPublisher` remain crucial DI components.

---

## III. Batch Orchestrator Service (BOS) Changes

BOS's role as the pipeline sequence owner becomes more explicit.

### 1. Pipeline Definition and Storage

* **During Batch Registration (`implementations/batch_processing_service_impl.py`)**:
  * BOS must determine and store the intended pipeline for the batch (e.g., from user input, a template, or default). This sequence (e.g., `["spellcheck", "ai_feedback", "nlp"]`) should be stored in the `requested_pipelines: List[str]` field of the `ProcessingPipelineState` model.
  * The `ProcessingPipelineState` (from `common_core.pipeline_models`) should be initialized with all potential stages set to a default "not started" or "pending" status.

    ```python
    # services/batch_orchestrator_service/implementations/batch_processing_service_impl.py
    # In register_new_batch method:
    
    # ... (after batch_id is generated and basic context stored)
    
    # Example: Define the pipeline sequence for this batch
    # This could come from the registration_data or a configuration lookup
    # For this example, let's assume a fixed pipeline for all new batches
    pipeline_sequence = ["spellcheck", "ai_feedback", "cj_assessment", "nlp"]
    
    initial_pipeline_state_details = {}
    for stage_name in pipeline_sequence:
        # Assuming PipelineStateDetail has a status field from PipelineExecutionStatus
        from common_core.pipeline_models import PipelineStateDetail, PipelineExecutionStatus
        initial_pipeline_state_details[stage_name.lower()] = PipelineStateDetail(
            status=PipelineExecutionStatus.REQUESTED_BY_USER # Or PENDING_DEPENDENCIES
        )

    pipeline_state = ProcessingPipelineState(
        batch_id=batch_id,
        requested_pipelines=pipeline_sequence,
        spellcheck=initial_pipeline_state_details.get("spellcheck"),
        ai_feedback=initial_pipeline_state_details.get("ai_feedback"),
        cj_assessment=initial_pipeline_state_details.get("cj_assessment"),
        nlp_metrics=initial_pipeline_state_details.get("nlp"), # field name is nlp_metrics
        # ... initialize other pipeline details if they exist in ProcessingPipelineState
    )
    await self.batch_repo.save_processing_pipeline_state(batch_id, pipeline_state)
    
    # ... (rest of the registration logic, e.g., publishing BatchEssaysRegistered)
    ```

### 2. Orchestration Logic (`kafka_consumer.py` or a dedicated orchestrator module)

* BOS consumes events from ELS indicating phase completion for essays/batches (e.g., `BatchPhaseConcluded`, or if all essays in a batch have reached `SPELLCHECKED_SUCCESS`).
* Upon such notification:
    1. BOS retrieves the `ProcessingPipelineState` for the batch.
    2. It identifies the stage that just completed.
    3. It looks at `requested_pipelines` to find the *next* stage.
    4. If a next stage exists and hasn't been initiated:
        * BOS constructs the appropriate `BatchService<NextPhase>InitiateCommandDataV1`.
        * Publishes this command to ELS.
        * Updates its `ProcessingPipelineState` to mark the new phase as initiated.
    5. If all stages in `requested_pipelines` are complete, BOS marks the overall batch processing as complete.

```python
# services/batch_orchestrator_service/kafka_consumer.py (conceptual logic in _handle_message or a new method)

async def _handle_els_phase_completion_event(
    self: BatchKafkaConsumer, # Assuming 'self' is an instance of BatchKafkaConsumer or similar
    batch_id: str,
    completed_phase_name: str, # e.g., "spellcheck"
    # ... other relevant data from ELS event
) -> None:
    logger.info(f"Batch {batch_id}: Phase '{completed_phase_name}' reported complete by ELS.")
    
    pipeline_state_obj = await self.batch_repo.get_processing_pipeline_state(batch_id)
    if not pipeline_state_obj: # Needs to handle dict vs Pydantic object
        logger.error(f"ProcessingPipelineState not found for batch {batch_id}.")
        return

    # Ensure we have the Pydantic model instance
    from common_core.pipeline_models import ProcessingPipelineState, PipelineExecutionStatus
    if isinstance(pipeline_state_obj, dict):
        pipeline_state = ProcessingPipelineState.model_validate(pipeline_state_obj)
    else:
        pipeline_state = pipeline_state_obj

    # Mark the completed phase in BOS's state
    current_phase_detail = pipeline_state.get_pipeline(completed_phase_name)
    if current_phase_detail:
        current_phase_detail.status = PipelineExecutionStatus.COMPLETED_SUCCESSFULLY
        current_phase_detail.completed_at = datetime.now(UTC)
        # current_phase_detail.essay_counts could be updated based on ELS event

    # Determine the next stage
    try:
        current_index = pipeline_state.requested_pipelines.index(completed_phase_name)
        if current_index + 1 < len(pipeline_state.requested_pipelines):
            next_phase_name = pipeline_state.requested_pipelines[current_index + 1]
        else:
            next_phase_name = None # All defined stages are complete
    except ValueError:
        logger.error(f"Completed phase '{completed_phase_name}' not found in requested_pipelines for batch {batch_id}.")
        return

    if next_phase_name:
        logger.info(f"Batch {batch_id}: Next phase in pipeline is '{next_phase_name}'.")
        next_phase_detail = pipeline_state.get_pipeline(next_phase_name)
        
        # Check if already initiated or completed to ensure idempotency
        if next_phase_detail and next_phase_detail.status not in [
            PipelineExecutionStatus.REQUESTED_BY_USER, 
            PipelineExecutionStatus.PENDING_DEPENDENCIES
        ]:
            logger.info(f"Batch {batch_id}: Next phase '{next_phase_name}' already processed/initiated ({next_phase_detail.status.value}). Skipping command.")
            await self.batch_repo.save_processing_pipeline_state(batch_id, pipeline_state) # Save updated current phase
            return

        # Construct and send command for the next phase
        # This requires mapping 'next_phase_name' (str) to specific command types and data
        # For example:
        command_to_send = None
        command_topic_event = None
        # Retrieve ready essays for the command (ELS should provide this in its completion event, or BOS queries ELS)
        # For now, let's assume ELS's "BatchPhaseConcluded" or similar event for 'completed_phase_name'
        # would trigger this, and perhaps BatchEssaysReady already provided the list initially.
        # BOS might need to query ELS for the current list of EssayProcessingInputRefV1 if not readily available.
        # This is a simplification for this example.
        
        # Placeholder: fetch batch_context to get language etc.
        batch_context = await self.batch_repo.get_batch_context(batch_id)
        if not batch_context: return # Should not happen

        # Placeholder: fetch ready essays for the command
        # This is a CRITICAL part. The BatchEssaysReady from ELS gives the initial list.
        # BOS needs to pass the relevant (and current state) list of essays for the next command.
        # This might mean BOS needs to get an updated list from ELS or ELS's "phase complete" event to BOS
        # includes the list of essays that successfully completed that phase.
        # Let's assume BatchEssaysReady event provided `ready_essays`.
        # In a real scenario, the event ELS sends to BOS to signify phase completion should contain the list of
        # essay_ids and their current text_storage_ids that are ready for the *next* phase.
        
        # This logic is simplified. The essays_to_process would come from ELS's notification.
        # For this example, we'll re-use the structure from BatchEssaysReady.
        # This is a significant detail for a real implementation.
        from common_core.events.batch_coordination_events import BatchEssaysReady # Placeholder
        # This would actually come from an event ELS sends after a phase is done for all essays in batch.
        # Or BOS queries ELS for essays ready for the next phase.
        mock_batch_ready_event = await self.batch_repo.get_mock_batch_ready_data(batch_id) # MOCK
        if not mock_batch_ready_event: return

        essays_for_next_phase = mock_batch_ready_event.ready_essays 
        language = _infer_language_from_course_code(batch_context.course_code) # From existing BOS logic

        if next_phase_name == "ai_feedback":
            from common_core.batch_service_models import BatchServiceAIFeedbackInitiateCommandDataV1
            from common_core.metadata_models import EntityReference
            command_data = BatchServiceAIFeedbackInitiateCommandDataV1(
                event_name=ProcessingEvent.BATCH_AIFEEDBACK_INITIATE_COMMAND, # Assuming this enum exists
                entity_ref=EntityReference(entity_id=batch_id, entity_type="batch"),
                essays_to_process=essays_for_next_phase, # This list needs to be accurate for current state
                language=language,
                course_code=batch_context.course_code,
                teacher_name="Teacher Name", # Placeholder
                class_designation=batch_context.class_designation,
                essay_instructions=batch_context.essay_instructions
            )
            command_topic_event = ProcessingEvent.BATCH_AIFEEDBACK_INITIATE_COMMAND
        elif next_phase_name == "cj_assessment":
            # ... construct BatchServiceCJAssessmentInitiateCommandDataV1 ...
            pass
        elif next_phase_name == "nlp":
            # ... construct BatchServiceNLPInitiateCommandDataV1 ...
            pass

        if command_data and command_topic_event:
            from common_core.events.envelope import EventEnvelope
            command_envelope = EventEnvelope( # Auto-populates event_id, timestamp
                event_type=topic_name(command_topic_event), # Ensure topic_name maps this
                source_service=self.settings.SERVICE_NAME, # BOS service name from its settings
                # correlation_id= original_correlation_id_from_els_event, # Propagate correlation
                data=command_data
            )
            await self.event_publisher.publish_batch_event(command_envelope)
            logger.info(f"Batch {batch_id}: Initiated next phase '{next_phase_name}'.")
            if next_phase_detail:
                next_phase_detail.status = PipelineExecutionStatus.DISPATCH_INITIATED
                next_phase_detail.started_at = datetime.now(UTC)
        else:
            logger.warning(f"Batch {batch_id}: No command constructed for next phase '{next_phase_name}'.")
            
    else: # All stages in requested_pipelines are complete
        logger.info(f"Batch {batch_id}: All requested pipeline stages completed.")
        # Potentially update batch status to a final completed state in BOS's primary batch store
        pipeline_state.batch_status = BatchStatus.COMPLETED_SUCCESSFULLY # Assuming BatchStatus on pipeline_state

    await self.batch_repo.save_processing_pipeline_state(batch_id, pipeline_state)

# Helper in BOS to infer language (already present in your kafka_consumer.py)
def _infer_language_from_course_code(course_code: str) -> str:
    # ... (implementation from your BOS file)
    course_code_upper = course_code.upper()
    if course_code_upper.startswith("SV"): return "sv"
    elif course_code_upper.startswith("ENG"): return "en"
    # ... more ...
    return "en"

```

**Note on `get_mock_batch_ready_data`**: This is a placeholder. In a real system, when ELS informs BOS that, for example, all essays in batch X have `SPELLCHECKED_SUCCESS`, that notification event from ELS to BOS should contain the list of `EssayProcessingInputRefV1` objects (with their latest `text_storage_id` if spellcheck modified content and stored a new version). BOS would then use *that* list for the *next* command.

### 3. Repository (`implementations/batch_repository_impl.py`)

* `MockBatchRepositoryImpl` would need to correctly store and retrieve the `ProcessingPipelineState` Pydantic model (or its dictionary representation if you prefer to store JSON in a real DB later).

This setup gives you the desired "mix and match" capability orchestrated by BOS, with ELS managing the state of each essay through each commanded phase using a more robust and declarative state machine. The complexity of *defining valid sequences* is shifted to BOS's configuration/logic for a batch, while ELS's state machine defines *valid transitions within and between any recognized processing stage*.
