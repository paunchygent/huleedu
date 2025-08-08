# ⏺ Start-of-Conversation Prompt: Critical Outbox Pattern Migration - Remaining Services

## ULTRATHINK: BREAKING CHANGE - SERVICES CURRENTLY INCOMPATIBLE WITH SHARED LIBRARY

**CRITICAL CONTEXT**: The shared library transactional outbox implementation has been updated to use an explicit `topic` column instead of embedding topic in JSON. **Support for the old pattern has been completely removed**. Three services are currently broken and will fail at runtime when the relay worker tries to access `event.topic` property.

## ULTRATHINK: MANDATORY READING ORDER - READ ALL BEFORE STARTING

### 1. Project Architecture Rules (Read These First):
- `.cursor/rules/000-rule-index.mdc` (full rule index)
- `.cursor/rules/042.1-transactional-outbox-pattern.mdc` (TRUE OUTBOX PATTERN - CRITICAL)
- `.cursor/rules/085-database-migration-standards.mdc` (migration standards to follow)
- `.cursor/rules/015-project-structure-standards.mdc` (project structure)
- `.cursor/rules/050-python-coding-standards.mdc` (Python standards)
- `.cursor/rules/030-event-driven-architecture-eda-standards.mdc` (event architecture)

### 2. Shared Library Current State (BREAKING CHANGES):
- `libs/huleedu_service_libs/src/huleedu_service_libs/outbox/models.py` (line 92-96: requires explicit topic column)
- `libs/huleedu_service_libs/src/huleedu_service_libs/outbox/repository.py` (line 200: expects topic parameter)
- `libs/huleedu_service_libs/src/huleedu_service_libs/outbox/relay.py` (line 275: accesses event.topic directly)
- `libs/huleedu_service_libs/src/huleedu_service_libs/outbox/protocols.py` (line 57-59: OutboxEvent requires topic property)

### 3. Successfully Migrated Reference Implementation (BOS):
- `services/batch_orchestrator_service/alembic/versions/20250808_0400_b602bb2e74f4_add_explicit_topic_column_to_event_.py` (migration template)
- `services/batch_orchestrator_service/models_db.py` (lines 307-311: topic field, lines 342-354: updated indexes)
- `services/batch_orchestrator_service/implementations/outbox_manager.py` (line 93: NO topic embedding)

### 4. Task Documentation:
- `TASKS/20250108_outbox_topic_migration_remaining_services.md` (detailed migration steps)

## ULTRATHINK: WHAT HAS BEEN COMPLETED

### Successfully Migrated Services (DO NOT TOUCH):
1. **batch_orchestrator_service** ✅
   - Migration applied: `20250808_0400_b602bb2e74f4`
   - Model has explicit topic field
   - OutboxManager cleaned (removed line 96: `serialized_data["topic"] = topic`)
   - Tests updated with topic property

2. **file_service** ✅ - Already had correct pattern
3. **result_aggregator_service** ✅ - Already had correct pattern
4. **cj_assessment_service** ✅ - Already had correct pattern

### Shared Library Updates Applied:
- ✅ OutboxEvent protocol has `topic` property
- ✅ OutboxEventImpl exposes `topic` from database column
- ✅ Repository no longer embeds topic in JSON
- ✅ Relay worker reads from `event.topic` property (NO FALLBACK)

## ULTRATHINK: CURRENT BROKEN STATE - THREE SERVICES NEED IMMEDIATE MIGRATION

### 1. class_management_service ❌ BROKEN
**Current State:**
- `services/class_management_service/models_db.py`: EventOutbox class MISSING topic field
- `services/class_management_service/implementations/outbox_manager.py:95`: STILL HAS `serialized_data["topic"] = topic`
- Database: NO topic column exists
- **Runtime Failure**: Relay worker will crash with AttributeError accessing `event.topic`

### 2. essay_lifecycle_service ❌ BROKEN
**Current State:**
- `services/essay_lifecycle_service/models_db.py`: EventOutbox class MISSING topic field
- `services/essay_lifecycle_service/implementations/outbox_manager.py`: STILL embeds topic in JSON
- Database: NO topic column exists
- **Runtime Failure**: Relay worker will crash with AttributeError accessing `event.topic`

### 3. nlp_service ❌ BROKEN
**Current State:**
- `services/nlp_service/models_db.py`: EventOutbox class MISSING topic field
- `services/nlp_service/implementations/outbox_manager.py`: STILL embeds topic in JSON
- Database: NO topic column exists
- **Runtime Failure**: Relay worker will crash with AttributeError accessing `event.topic`

## ULTRATHINK: DATABASE INFORMATION AND MIGRATION STANDARDS

### Database Names and Ports (FROM RULE 085):
| Service | Container Name | Database Name | Port |
|---------|---------------|---------------|------|
| `class_management_service` | `huleedu_class_management_db` | `huledu_class_management` | 5435 |
| `essay_lifecycle_service` | `huleedu_essay_lifecycle_db` | `huledu_essay_lifecycle` | 5433 |
| `nlp_service` | `huleedu_nlp_db` | `huledu_nlp` | 5439 |

### Migration Standards (RULE 085 - MANDATORY):
1. **Pre-Migration Analysis**: ALWAYS check current state first
2. **Use monorepo venv directly**: `../../.venv/bin/alembic` (NOT pdm run)
3. **Verify after migration**: Check both alembic state and database schema

## ULTRATHINK: EXACT MIGRATION PATTERN TO APPLY

### For Each Service, You Must:

#### 1. PRE-MIGRATION ANALYSIS (MANDATORY FROM RULE 085)
```bash
# Check current Alembic state
cd services/{service_name}
../../.venv/bin/alembic current

# Check database tables (use one of these approaches)
# Option 1: Source .env first
source /Users/olofs_mba/Documents/Repos/huledu-reboot/.env
docker exec huleedu_{service_short}_db psql -U $HULEEDU_DB_USER -d huledu_{service} -c "\dt"

# Option 2: Use hardcoded values
docker exec huleedu_{service_short}_db psql -U huleedu_user -d huledu_{service} -c "\dt"

# Check if event_outbox table exists and its structure
docker exec huleedu_{service_short}_db psql -U huleedu_user -d huledu_{service} -c "\d event_outbox"
```

#### 2. CREATE DATABASE MIGRATION
Navigate to service directory and create migration following BOS pattern and RULE 085:
```bash
cd services/{service_name}
../../.venv/bin/alembic revision -m "Add explicit topic column to event outbox"
```
Use the exact pattern from `services/batch_orchestrator_service/alembic/versions/20250808_0400_b602bb2e74f4_add_explicit_topic_column_to_event_.py`

Key migration steps:
1. Add nullable topic column
2. Extract from JSON: `UPDATE event_outbox SET topic = event_data->>'topic'`
3. Handle nulls with default: `'huleedu.{service}.unknown.v1'`
4. Make column NOT NULL
5. Add `ix_event_outbox_topic` index
6. Replace `ix_event_outbox_unpublished` with `ix_event_outbox_unpublished_topic`

#### 2. UPDATE EVENTOUTBOX MODEL
In `models_db.py`, add after `event_key` field:
```python
# Kafka targeting
topic: Mapped[str] = mapped_column(
    String(255),
    nullable=False,
    comment="Kafka topic to publish to",
)
```

Update `__table_args__` indexes to match BOS pattern (lines 342-366 in BOS models_db.py)

#### 3. CLEAN OUTBOXMANAGER
Find and REMOVE the line that embeds topic:
```python
serialized_data["topic"] = topic  # DELETE THIS LINE COMPLETELY
```
The repository call already passes topic as parameter - verify it looks like:
```python
await self.outbox_repository.add_event(
    aggregate_id=aggregate_id,
    aggregate_type=aggregate_type,
    event_type=event_type,
    event_data=serialized_data,  # Should NOT contain topic
    topic=topic,  # Passed as explicit parameter
    event_key=event_key,
)
```

#### 4. UPDATE ALL TESTS
Find all `FakeOutboxEvent` classes and:
- Add `topic: str` parameter to `__init__`
- Add `self._topic = topic` in constructor
- Add `@property def topic(self) -> str: return self._topic`
- Update all instantiations to include `topic="..."`
- Remove `"topic": "..."` from event_data dicts

#### 5. APPLY MIGRATION (FOLLOW RULE 085)
```bash
# Apply the migration using monorepo venv
cd services/{service_name}
../../.venv/bin/alembic upgrade head

# Verify migration was applied
../../.venv/bin/alembic current

# Verify database schema
docker exec huleedu_{service_short}_db psql -U huleedu_user -d huledu_{service} -c "\d event_outbox"
```

#### 6. TEST AND VERIFY
```bash
# Run type checking from root
cd ../..
pdm run typecheck-all

# Run integration tests
pdm run pytest services/{service_name}/tests/integration/test_outbox*.py -xvs

# Run all service tests
pdm run pytest services/{service_name}/tests/ -x
```

### Service-Specific Commands:

**For class_management_service:**
```bash
cd services/class_management_service
../../.venv/bin/alembic current
docker exec huleedu_class_management_db psql -U huleedu_user -d huledu_class_management -c "\d event_outbox"
```

**For essay_lifecycle_service:**
```bash
cd services/essay_lifecycle_service
../../.venv/bin/alembic current
docker exec huleedu_essay_lifecycle_db psql -U huleedu_user -d huledu_essay_lifecycle -c "\d event_outbox"
```

**For nlp_service:**
```bash
cd services/nlp_service
../../.venv/bin/alembic current
docker exec huleedu_nlp_db psql -U huleedu_user -d huledu_nlp -c "\d event_outbox"
```

## ULTRATHINK: SUCCESS CRITERIA

For EACH of the three services:
1. ✅ Database has explicit topic column with data migrated from JSON
2. ✅ Model EventOutbox class has topic field
3. ✅ OutboxManager does NOT embed topic in JSON (line removed)
4. ✅ Indexes updated for performance
5. ✅ All tests pass with FakeOutboxEvent having topic property
6. ✅ Type checking passes with no errors
7. ✅ Integration tests confirm events published correctly

## ULTRATHINK: CRITICAL UNDERSTANDING

**WHY THIS IS URGENT:**
- Relay worker in shared library now calls `event.topic` directly (line 275 in relay.py)
- No backward compatibility exists - old pattern support completely removed
- Services WILL CRASH at runtime when trying to publish events
- This is a BREAKING CHANGE that requires immediate action

**WHAT NOT TO DO:**
- Do NOT use agents - implement directly
- Do NOT modify already migrated services
- Do NOT add backward compatibility to shared library
- Do NOT embed topic in JSON anymore

**IMPLEMENTATION ORDER:**
1. Start with class_management_service (most critical)
2. Then essay_lifecycle_service
3. Finally nlp_service

## MANDATORY: Read ALL referenced rules and files above BEFORE starting implementation. The migration pattern from BOS is your gold standard. Follow it exactly.

BEGIN WITH: class_management_service migration.