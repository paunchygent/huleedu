# Event System

## Contracts
- All Kafka events use `EventEnvelope`
- Topics generated with `topic_name()` utility
- Large payloads: use `StorageReferenceMetadata`

## Locations
- Event contracts: `libs/common_core/src/common_core/`
- Topic enums: `libs/common_core/src/common_core/event_enums.py`
- Error models: `libs/common_core/src/common_core/error_enums.py`

## Error Handling
Centralized patterns in:
- `libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/`

**Detailed**: `.agent/rules/051-event-contract-standards.md`
