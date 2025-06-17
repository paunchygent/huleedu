# Here is the validated list of pruning candidates, complete with file and line references and the assurance of no dependencies

## **Pruning Candidates & Status (updated 2025-06-17)**

### Completed

- **Candidate #1 – Unused Metadata Models**  
  ✅ Removed `UserActivityMetadata` and `CancellationMetadata` (common_core).  
  🔄 Replacement guidance: once the API-gateway/auth layer is in place, model user context from JWT claims (e.g. `user_id`, `roles`) and represent cancellation as explicit domain commands/events with a `requested_by` field.

- **Candidate #2 – Obsolete `ProcessingEvent` Enum Members**  
  ✅ Removed generic batch pipeline events.  
  🔄 Use specific command/outcome events instead (already in use).

- **Candidate #3 – Unused `BatchStatusResponseV1` Model**  
  ✅ Removed from BOS.  
  🔄 UI should consume real-time Kafka events via a WebSocket relay service that maintains a projection (Redis/in-memory) and pushes incremental updates.

- **Candidate #5 – Obsolete `StateTransitionValidator` in ELS**  
  ✅ Removed class, protocol, DI provider, and updated test framework.  
  🔄 All state validation now uses `EssayStateMachine` directly for formal state management.  
  📝 **Test Updated**: Converted `test_state_transition_validator_integration()` to `test_state_machine_validation_capabilities()` to test EssayStateMachine directly.

- **Candidate #6 – Unused `ContentClient` in ELS**  
  ✅ Removed protocol, implementation, and DI provider.  
  🔄 Content interactions are handled by specialized services (e.g., Spell Checker), not ELS.

- **Candidate #7 – Unused `hypercorn_config.py` in Content Service**  
  ✅ Removed dead configuration file.  
  🔄 Service uses direct hypercorn command line configuration via pyproject.toml.

- **Candidate #8 – Legacy Shim Module in CJ Assessment Service**  
  ✅ Removed `core_assessment_logic.py` shim file.  
  🔄 Direct imports from `cj_core_logic` package work correctly via `__init__.py` exports.

### Validation Results

#### **✅ All Removals Successful**

- 118/118 ELS unit tests pass
- Test framework updated to use EssayStateMachine directly  
- No broken dependencies detected
- Clean removal of all obsolete components

**🎯 Cleanup Impact**

- **Eliminated** ~150 lines of duplicate state transition logic
- **Removed** 4 unused protocols and implementations
- **Simplified** test infrastructure by removing wrapper abstractions
- **Enhanced** codebase clarity by removing dead code

---

### **Candidate #2: Obsolete Generic `ProcessingEvent` Enum Members**

- **File(s) & Lines to Modify**:
  - `common_core/src/common_core/enums.py`: Remove the specified enum members from the `ProcessingEvent` enum.
- **Code to Remove**: The enum members:
  - `BATCH_PIPELINE_REQUESTED`
  - `BATCH_PHASE_INITIATED`
  - `BATCH_PIPELINE_PROGRESS_UPDATED`
  - `BATCH_PHASE_CONCLUDED`
- **Dependency Check & Assurance**:
  - **Validation**: I have confirmed that these generic events are not used in the `topic_name()` mapping function, nor are they referenced by any Kafka producers or consumers in the services.
  - **Assurance**: The architecture has evolved to use more specific command and outcome events (e.g., `BATCH_SPELLCHECK_INITIATE_COMMAND`, `ELS_BATCH_PHASE_OUTCOME`). Removing these legacy enum members will clean up the contract without affecting any logic.

---

### **Candidate #3: Unused `BatchStatusResponseV1` Model in BOS**

- **File(s) & Lines to Modify**:
  - `services/batch_orchestrator_service/api_models.py`: Remove the entire `BatchStatusResponseV1` class definition.
- **Code to Remove**: The `BatchStatusResponseV1` Pydantic model.
- **Dependency Check & Assurance**:
  - **Validation**: I have analyzed the `services/batch_orchestrator_service/api/batch_routes.py` file. The `get_batch_status` route does not import or instantiate this model. No other part of the service uses it.
  - **Assurance**: This model is unreferenced and represents dead code. Its removal has no impact on the service's API.

---

### **Candidate #4: Legacy Test Endpoint in BOS**

- **File(s) & Lines to Modify**:
  - `services/batch_orchestrator_service/api/batch_routes.py`: Remove the `@batch_bp.route("/trigger-spellcheck-test", ...)` function and its logic.
- **Code to Remove**: The `/v1/batches/trigger-spellcheck-test` endpoint.
- **Dependency Check & Assurance**:
  - **Validation**: I have reviewed the functional and E2E tests in the `tests/` directory. None of the current test suites (`test_e2e_...`) make calls to this endpoint. The standard workflow now starts with batch registration and file uploads.
  - **Assurance**: This is a development artifact that is no longer used by any automated tests or the documented user flow. Removing it cleans the API surface with no impact.

---

### **Candidate #6: Unused `
