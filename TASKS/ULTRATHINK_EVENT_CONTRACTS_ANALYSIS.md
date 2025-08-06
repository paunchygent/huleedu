# ULTRATHINK: Service Event Emission Analysis for Notification Projection

## Executive Summary

**Key Finding**: Services already emit the necessary internal domain events for notification projectors to listen to. The projection pattern works by listening to existing events, not creating new ones.

**Correct Understanding**: No new event contracts needed - just notification projectors that listen to existing internal events.

## Service Event Emission Analysis

### ✅ File Service - READY
**Events Emitted**:
- `BatchFileAddedV1` (has user_id for direct teacher resolution)
- `BatchFileRemovedV1` (has user_id for direct teacher resolution)
- `EssayValidationFailedV1` (validation failures)

**Projector Strategy**: Listen to file management events, aggregate into batch notifications

### ✅ Assessment Services - READY  
**Events Emitted**:
- Essay-level: `SpellcheckResultDataV1`, `CJAssessmentCompletedV1`, `AIFeedbackResultDataV1`
- Batch-level: ELS aggregates these into `ELSBatchPhaseOutcomeV1` events

**Projector Strategy**: ELS projector listens to `ELSBatchPhaseOutcomeV1`, maps phases to notifications

### ✅ Batch Orchestrator - READY
**Events Emitted** (by ELS):
- `BatchContentProvisioningCompletedV1` - Processing starts
- `ELSBatchPhaseOutcomeV1` - Phases complete/fail

**Projector Strategy**: Listen to ELS batch lifecycle events for processing status

### ❌ Result Aggregator - NOT READY (CRITICAL ARCHITECTURE)
**Events Emitted**: NONE - Only consumes, never publishes completion events
**Critical Role**: RAS emits **results completion events** for AI Feedback Service coordination
**Blockers**: 
- Needs event emission capability for results completions (spellcheck_results_completed, cj_assessment_results_completed, etc.)
- Needs event emission capability for teacher notifications (batch_results_ready, batch_export_completed)
- AI Feedback Service depends on RAS results completion events to collect curated assessment data

## Implementation Order & Dependencies

### Correct Implementation Order:
1. **File Service** (FIRST - independent, has direct user_id events)
2. **Assessment Services** (SECOND - ELS aggregates essay results into batch events)  
3. **Batch Orchestrator** (THIRD - uses ELS batch lifecycle events)
4. **Result Aggregator** (LAST - most complex: emits phase events for AI Feedback coordination + teacher notifications)

## Key Insights

### No New Event Contracts Needed
- Services already emit the necessary internal domain events
- Notification projectors listen to existing events and transform them into `TeacherNotificationRequestedV1`
- The projection pattern is about listening to existing events, not creating new ones

### Result Aggregator Service Architecture (CRITICAL)
- **RAS Role**: Active pipeline participant, not passive final aggregator
- **Results Events**: RAS must emit results completion events (spellcheck_results_completed, cj_assessment_results_completed, etc.)
- **Partial Completion**: Events include both completed and partially_completed variants for realistic scenarios
- **AI Feedback Dependency**: AI Feedback Service depends on RAS results completion events to collect curated data
- **Dual Event Types**: RAS emits both service coordination events AND teacher notification events
- **Implementation Complexity**: Higher than initially understood due to dual event emission requirements

### Teacher ID Resolution Patterns  
- **File Service**: Direct user_id field (simple)
- **Other Services**: Batch repository lookup required (more complex)

## Next Session Focus

**Start with File Service notification projector implementation** - it has the simplest teacher ID resolution pattern and is independent of other services.

**Key Architectural Understanding**: RAS is not a simple final aggregator - it's a critical pipeline participant that emits results completion events (with partial completion variants) for AI Feedback Service coordination. The improved naming (`spellcheck_results_completed` vs `spellcheck_phase_completed`) aligns with RAS domain language and provides clear consumer guidance. This makes RAS the most complex service to implement and confirms it should be last in the implementation order.
