# ADR-001: Course Skill Level Architecture for Multi-Level Education

## Status
Proposed

## Context
The Class Management Service currently uses a `skill_level` integer field in the courses table that conflates course sequence numbers with actual difficulty levels. This creates problems when extending the platform to support multiple educational levels (gymnasium, grundskola, etc.):

1. **Namespace Conflicts**: Svenska 1 (SV1) in gymnasium vs Grade 7 Swedish in grundskola
2. **Misleading Semantics**: skill_level=3 for SV3 doesn't mean it's easier than skill_level=7 for ENG7
3. **Future Limitations**: No clear way to add courses from different educational systems

## Decision
Remove the arbitrary difficulty scoring and instead:

1. **Keep `skill_level` as deprecated** (for backwards compatibility)
2. **Add `education_level`** to distinguish educational contexts ('grundskola_upper', 'gymnasium')
3. **Use `sequence_number`** for progression within a course series (1, 2, 3)
4. **Track prerequisites** explicitly via course relationships

```sql
ALTER TABLE courses 
ADD COLUMN education_level VARCHAR(50),
ADD COLUMN sequence_number INTEGER,
ADD COLUMN prerequisite_course_code VARCHAR(20);
```

## Consequences

### Positive
- Clear separation of educational contexts
- No arbitrary difficulty metrics to maintain
- Natural progression tracking within each context
- Backwards compatible (existing skill_level remains)

### Negative
- Additional columns in courses table
- Migration needed to populate new fields
- UI updates required to use new fields

## Alternatives Considered

1. **Arbitrary difficulty_score (1-100)**: Rejected as it adds complexity without clear benefit
2. **Separate services per education level**: Rejected due to code duplication
3. **Complex skill taxonomy**: Rejected as over-engineering for current needs

## References
- Original discussion: Class Management Service database model analysis
- Related: SERVICE_FUTURE_ENHANCEMENTS/class_management_service_roadmap.md
