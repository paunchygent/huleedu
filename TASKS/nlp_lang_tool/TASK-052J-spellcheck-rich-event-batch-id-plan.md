# TASK-052J — Spellcheck Rich Event Batch ID Alignment

## Objective

Align the spellchecker rich event contract (`SpellcheckResultV1`) with the CJ Assessment and planned NLP patterns by making `batch_id` an explicit, mandatory field. This removes reliance on envelope metadata for batch context and simplifies downstream processing.

## Rationale

- **Contract symmetry**: CJ rich events already expose `batch_id`; NLP will follow. Spellcheck should match so every rich result event carries batch context in the payload.
- **No legacy ambiguity**: Eliminating the `parent_id` fallback prevents subtle regressions and enforces a single contract surface for all consumers.
- **Straightforward automation**: Pure development mode lets us refactor aggressively—AI-driven edits and tests only, no deployment choreography.

## Scope

- `libs/common_core/src/common_core/events/spellcheck_models.py`
- `services/spellchecker_service/implementations/event_publisher_impl.py`
- `services/result_aggregator_service/implementations/spellcheck_event_handler.py`
- Spellchecker and RAS unit/integration tests referencing `SpellcheckResultV1`

## Deliverables

1. Updated `SpellcheckResultV1` model with a required `batch_id: str` field; remove any implied reliance on `parent_id`.
2. Spellchecker publisher populates both `batch_id` and `parent_id` (the latter kept for envelope consistency only).
3. Result Aggregator consumer reads `data.batch_id` exclusively; any payload without it should fail fast.
4. Test suites updated so fixtures supply `batch_id`. Add regression coverage that verifies the consumer raises if `batch_id` is missing, proving the fallback path is gone.
5. Document the contract change (task notes/CHANGELOG) to guide other services.

## Implementation Steps

1. **Model Update (Library)**
   - Add `batch_id: str = Field(description="Batch identifier")` to `SpellcheckResultV1`.
   - If the existing contract version must be preserved, bump to `SpellcheckResultV2`; otherwise treat this as a breaking change in development.

2. **Publisher Refactor (Spellchecker Service)**
   - When constructing the rich event, set `batch_id = event_data.parent_id` (enforcing non-null before publish) and keep `parent_id` for envelope compatibility.
   - Consider asserting `batch_id` presence to catch missing metadata upstream.

3. **Consumer Update (Result Aggregator Service)**
   - Replace `data.parent_id` lookups with `data.batch_id`.
   - Fail immediately (structured error) if `batch_id` is absent—no fallback logic.

4. **Test Refresh**
   - Update spellchecker publisher tests and RAS handlers to pass/expect `batch_id`.
   - Add a regression test ensuring that omitting `batch_id` raises, confirming the legacy path is removed.

5. **Contract Notes**
   - Record the change in the task document or service README so NLP and future services follow the same explicit-field pattern.

## Out of Scope

- Database schema changes (RAS already persists batch IDs).
- Deployment coordination; we remain in development-only mode.

## Success Criteria

- All unit/integration tests pass locally with the new field enforced.
- RAS logs show spellcheck rich events referencing `data.batch_id` with no fallback warnings.
- Attempting to publish or consume a payload without `batch_id` fails fast, proving the old path is gone.
