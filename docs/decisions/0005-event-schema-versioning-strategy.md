---
type: decision
id: ADR-0005
status: proposed
created: 2025-11-27
last_updated: 2025-11-27
---

# ADR-0005: Event Schema Versioning Strategy

## Status
Proposed (Aspirational Policy - Infrastructure Not Yet Implemented)

## Implementation Status
- **V1/V2 suffix pattern**: Currently in use in Pydantic class names
- **JSON Schema directory**: NOT YET CREATED - schemas are in Pydantic only
- **CI validation script**: NOT YET IMPLEMENTED
- **Contract tests**: Partial coverage in `tests/contract/`

## Context
The HuleEdu platform uses event-driven architecture with Kafka for inter-service communication. Event schemas are currently defined as Pydantic models in `libs/common_core/src/common_core/events/`, but there is no formal governance or versioning strategy. This creates risks:

1. **Breaking Changes**: Adding required fields or removing fields breaks existing consumers
2. **Deployment Coupling**: Service deployments are tightly coupled due to schema changes
3. **Compatibility Testing**: No automated validation that schema changes are backward compatible
4. **Production Incidents**: Schema mismatches cause silent failures or deserialization errors
5. **Documentation Drift**: No single source of truth for event schema history

Current state:
- Event schemas defined in Pydantic classes (common_core/events/)
- Version suffix in event names (V1, V2) but no formal policy
- No schema registry or validation tooling
- Manual review of event contract changes in PRs
- Event consumers assume schema stability

The platform needs formal schema governance to enable safe, independent service deployments while maintaining event contract integrity.

## Decision
Implement **additive-only schema evolution** with automated CI validation:

### 1. Schema Evolution Policy
**ALLOWED** (Backward Compatible):
- Adding new optional fields (with defaults)
- Adding new event types
- Relaxing field constraints (e.g., making required field optional)
- Adding enum values (if consumers handle unknown values gracefully)
- Documentation updates

**FORBIDDEN** (Breaking Changes):
- Removing fields
- Renaming fields
- Changing field types
- Making optional fields required
- Removing enum values
- Narrowing field constraints

**BREAKING CHANGE PROCEDURE**:
- Create new event version (e.g., BatchCreatedV2)
- Dual-publish from producer during transition (publish both V1 and V2)
- Migrate consumers incrementally to V2
- Deprecate V1 after all consumers migrated
- Remove V1 after deprecation period (minimum 2 sprints)

### 2. Schema Storage and Validation (PROPOSED - Not Yet Implemented)
**Schema Directory**: `libs/common_core/schemas/events/` (to be created)
```
events/
  batch_created_v1.json
  batch_created_v2.json
  essay_spellcheck_completed_v1.json
  ...
```

**JSON Schema Format**: Use JSON Schema Draft 7 for compatibility with validation tools
- Note: Pydantic v2 uses `model_json_schema()` method (not `schema_json_of()`)
- Manually maintained for precision when needed
- Versioned alongside Pydantic definitions

### 3. CI Validation Pipeline (PROPOSED - Not Yet Implemented)
**Script**: `scripts/validate_event_schemas.py` (to be created)

Checks:
1. **Schema-to-Pydantic Consistency**: Validate sample payloads against JSON schemas
2. **Breaking Change Detection**: Compare new schema to previous version, fail on breaking changes
3. **Version Bump Enforcement**: Require version increment (V1 → V2) if breaking changes detected
4. **Sample Payload Validation**: Use fixtures from `tests/contract/` to validate real-world payloads

**CI Gate**: Block PRs with breaking changes unless event name version is incremented

**Command**:
```bash
pdm run validate-schemas  # Runs in CI and locally
```

### 4. Contract Testing Expansion
Enhance `tests/contract/` to:
- Generate sample payloads for all events
- Validate against JSON schemas automatically
- Test forward compatibility (old consumer, new schema)
- Test backward compatibility (new consumer, old schema)

### 5. Developer Workflow
When modifying event schemas:
1. Make change in Pydantic model
2. Run `pdm run validate-schemas` locally
3. If breaking change: increment version suffix (V1 → V2) and create new schema file
4. Add migration plan to PR description (dual-publish timeline, consumer migration checklist)
5. CI validates and blocks if version not incremented for breaking change

## Consequences

### Positive
- **Safe Deployments**: Services can deploy independently without fear of breaking event consumers
- **Automated Safety**: CI catches breaking changes before they reach production
- **Clear Evolution Path**: Versioning policy provides explicit process for schema changes
- **Documentation**: JSON schemas serve as machine-readable contract documentation
- **Testing Confidence**: Contract tests validate compatibility across versions
- **Operational Visibility**: Breaking changes are explicit and tracked via version numbers

### Negative
- **Schema Duplication**: Maintain both Pydantic models and JSON schemas (mitigated by generation)
- **Version Proliferation**: Multiple event versions exist during migration periods
- **Dual-Publishing Overhead**: Producers must emit multiple event versions during transitions
- **Validation Performance**: CI schema validation adds ~30 seconds to pipeline
- **Developer Discipline Required**: Must run validation before committing event changes

## Alternatives Considered

1. **Confluent Schema Registry**: Use external schema registry service with Avro
   - Rejected: Adds infrastructure dependency (Schema Registry service)
   - Would provide better tooling but significant operational overhead
   - Can migrate later if schema count grows significantly (>100 event types)

2. **Protobuf for Events**: Switch from JSON to Protobuf for event serialization
   - Rejected: Major migration effort with minimal benefit
   - Pydantic + JSON is simpler for Python-heavy services
   - Protobuf backward compatibility is similar to our additive-only policy

3. **Semantic Versioning for Events**: Use SemVer (1.0.0, 1.1.0, 2.0.0) instead of V1/V2
   - Rejected: Overkill for event versioning; major version (V1, V2) is sufficient
   - SemVer implies richer compatibility semantics than needed

4. **No Schema Enforcement**: Continue manual code review without automation
   - Rejected: Doesn't scale; human review misses subtle breaking changes
   - Production incidents prove current approach is insufficient

5. **Allow Breaking Changes Freely**: Don't restrict schema evolution
   - Rejected: Defeats purpose of event-driven decoupling
   - Forces coordinated service deployments, negating microservices benefits

## Related ADRs
- ADR-0003: Multi-Tenancy Data Isolation Strategy (tenant_id added to EventEnvelope)
- ADR-0006: Pipeline Completion State Management (new pipeline events)

## References
- TASKS/assessment/event-schema-governance-and-ci-plan.md
- .claude/rules/051-event-contract-standards.md
- libs/common_core/src/common_core/events/ (current event definitions)
- libs/common_core/src/common_core/event_enums.py (topic registry)
