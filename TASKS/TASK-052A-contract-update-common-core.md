# TASK-052A — Common Core Contracts Update (GrammarError enrichment)

## Objective

Enhance `libs/common_core/src/common_core/events/nlp_events.py` to carry full grammar error context needed by NLP, AI Feedback, and analytics.

## Boundary Objects & Contracts

- Update: `GrammarError`
  - Add required fields:
    - `category_id: str` (LanguageTool category.id)
    - `category_name: str` (LanguageTool category.name)
    - `context: str` (surrounding text snippet)
    - `context_offset: int` (offset within context)
  - Keep existing fields: `rule_id, message, short_message, offset, length, replacements, category, severity`.
- Unchanged: `GrammarAnalysis`, `EssayNlpCompletedV1` (continues to embed `GrammarAnalysis`).

## Shared Libraries

- `pydantic` (v2) for models (Rule 051)
- Tests via `pytest` (Rule 070)

## Implementation Steps

1. Modify `GrammarError` dataclass with the four required fields.
2. Update any default factories to avoid None (fields are required in prototyping).
3. Add/adjust unit tests under `libs/common_core/tests` to validate new fields serialization/deserialization.
4. Search and update references constructing `GrammarError` (NLP mock generators, skeletons) to include the new fields.

## Acceptance Tests

- Model round‑trip: creating `GrammarError` with all fields serializes and deserializes.
- Backwards builder usage updated in NLP tests to include new fields (no missing fields errors).

## Risks & Mitigation

- Breakage risk in services importing `GrammarError` — mitigated by updating NLP mock client in Subtask E.
- Schema drift — covered by centralizing contract in common_core and contract tests.

## Deliverables

- Updated `GrammarError` with context/category fields.
- Passing unit tests in `common_core`.
- Changelog entry in `CHANGELOG.md` summarizing the schema enrichment.

