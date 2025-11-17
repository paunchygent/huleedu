---
id: 'TASK-052A-CONTRACT-UPDATE-COMMON-CORE'
title: 'TASK-052A — Common Core Contracts Update ✅ COMPLETED'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'architecture'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-09-09'
last_updated: '2025-11-17'
related: []
labels: []
---
# TASK-052A — Common Core Contracts Update ✅ COMPLETED

## Implementation Summary

Enhanced `GrammarError` in `libs/common_core/src/common_core/events/nlp_events.py:181-199` with context fields:

```python
# Added fields (lines 192-199)
category_id: str = Field(description="Language Tool category identifier (e.g., 'GRAMMAR', 'PUNCTUATION')")
category_name: str = Field(description="Human-readable category name (e.g., 'Grammar', 'Punctuation')")  
context: str = Field(description="Surrounding text snippet for error context")
context_offset: int = Field(description="Character offset of error within the context snippet")
```

- **Tests**: 7 unit tests in `libs/common_core/tests/unit/test_grammar_models.py` (all passing)
- **NLP mocks updated**: `services/nlp_service/implementations/language_tool_client_impl.py:148-187`
- **CHANGELOG**: Added under `[Unreleased]` section

**Remaining**: None - fully integrated, ready for Language Tool Service consumption.
