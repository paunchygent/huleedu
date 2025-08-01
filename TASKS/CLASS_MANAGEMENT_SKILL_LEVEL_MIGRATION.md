# Class Management skill_level Field Migration Plan

## 🎯 OBJECTIVE
Complete the skill_level field migration in Class Management service by eliminating the deprecated database field and updating all references to use modern field patterns, achieving 100% compliance with architectural mandates.

## 🚨 LEGACY FIELD IDENTIFIED

### Database Schema Violation
**File**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/class_management_service/models_db.py`
**Line**: 58

```python
# DEPRECATED FIELD (to be removed)
skill_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
```

### Architectural Violations
- **CLAUDE.local.md**: Violates "NO backwards compatibility in database fields" mandate
- **Rule 010**: Deprecated field represents legacy pattern maintenance
- **Database bloat**: Unused field consuming storage and adding complexity

## 🏗️ MODERN REPLACEMENT ARCHITECTURE

### Current State Analysis
- ✅ **Modern Implementation**: `common_core.domain_enums.get_course_level(course_code)` fully operational
- ✅ **Business Logic**: Course-code-based skill level determination implemented
- ❌ **Legacy Field**: Database still contains deprecated `skill_level` column
- ❌ **Mixed Usage**: Some code still references old database field

### Target Architecture
- **Before**: Database-stored static skill_level integer field
- **After**: Dynamic skill level derived from course_code via domain enums
- **Benefits**: Single source of truth, automatic skill level management, no data duplication

## 📋 IMPLEMENTATION PLAN

### Phase 1: Database Schema Migration (Day 1 Morning)

#### 1. Create Alembic Migration
```bash
cd services/class_management_service
../../.venv/bin/alembic revision -m "Remove deprecated skill_level field"
```

#### 2. Migration Implementation
```python
def upgrade() -> None:
    """Remove deprecated skill_level field now handled by domain enums."""
    op.drop_column('courses', 'skill_level')

def downgrade() -> None:
    """Restore deprecated skill_level field for rollback safety."""
    op.add_column('courses', sa.Column('skill_level', sa.Integer(), nullable=False, server_default='1'))
```

### Phase 2: Database Model Updates (Day 1 Afternoon)

#### 3. Update Database Model
**File**: `/services/class_management_service/models_db.py`
**Action**: Remove skill_level field definition
```python
# REMOVE LINE 58:
skill_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
```

### Phase 3: Business Logic Modernization (Day 1 Evening)

#### 4. Update Mock Implementation
**File**: `/services/class_management_service/implementations/class_repository_mock_impl.py`
**Line**: 46
**Action**: Remove skill_level parameter, use domain enum function
```python
# BEFORE:
course = Course(
    id=course_id,
    course_code=course_code,
    name=course_name,
    language=language,
    skill_level=1,  # ← REMOVE THIS
)

# AFTER:
from common_core.domain_enums import get_course_level
course = Course(
    id=course_id,
    course_code=course_code,
    name=course_name,
    language=language,
    # skill_level derived automatically via get_course_level(course_code)
)
```

### Phase 4: Test Suite Updates (Day 2 Morning)

#### 5. Update Integration Tests
**File**: `/services/class_management_service/tests/test_repository_integration.py`
**Line**: 62
**Action**: Remove skill_level from SQL INSERT statements
```sql
-- BEFORE:
INSERT INTO courses (id, course_code, name, language, skill_level) VALUES
('course-1', 'ENG1', 'English Level 1', 'English', 1),
('course-2', 'ENG2', 'English Level 2', 'English', 2);

-- AFTER:
INSERT INTO courses (id, course_code, name, language) VALUES
('course-1', 'ENG1', 'English Level 1', 'English'),
('course-2', 'ENG2', 'English Level 2', 'English');
```

#### 6. Update Performance Tests
**File**: `/services/class_management_service/tests/performance/conftest.py**
**Line**: 437
**Action**: Remove skill_level from performance test data
```sql
-- BEFORE:
INSERT INTO courses (id, course_code, name, language, skill_level) VALUES

-- AFTER:
INSERT INTO courses (id, course_code, name, language) VALUES
```

### Phase 5: Validation and Compliance (Day 2 Afternoon)

#### 7. Execute Migration
```bash
cd services/class_management_service
../../.venv/bin/alembic upgrade head
```

#### 8. Run Quality Checks
```bash
# From repository root
pdm run lint-all
pdm run typecheck-all
pdm run test-all
```

#### 9. Rebuild Service
```bash
docker compose build --no-cache class-management-service
```

## 📊 COMPLETE SCOPE ANALYSIS

### Files Requiring Modification (4 total)

#### Critical Changes (2 files)
1. **Database Model**: `models_db.py` - Remove field definition
2. **Migration**: New Alembic migration - Drop database column

#### Business Logic Updates (1 file)
3. **Mock Repository**: `class_repository_mock_impl.py` - Remove skill_level parameter

#### Test Updates (2 files)
4. **Integration Tests**: `test_repository_integration.py` - Update SQL statements
5. **Performance Tests**: `conftest.py` - Update test data creation

### Historical Migration Files (Preserved)
- `20250706_0001_initial_schema.py` - Keep for migration history
- `20250708_0002_seed_courses.py` - Keep for migration history (contains skill_level references but needed for rollback)

## ✅ VALIDATION CRITERIA

### Pre-Migration Validation
- [ ] Domain enum function `get_course_level()` fully operational
- [ ] No active business logic depends on database skill_level field
- [ ] All course code mappings verified in domain enums
- [ ] Backup strategy for rollback safety established

### Post-Migration Validation
- [ ] Database schema contains no skill_level column
- [ ] All business logic uses `get_course_level(course_code)` function
- [ ] All tests pass with modern patterns
- [ ] API responses exclude deprecated field
- [ ] Course skill levels determined dynamically from course codes
- [ ] No references to skill_level field in entire codebase

### Compliance Verification
- [ ] ✅ CLAUDE.local.md: "NO backwards compatibility in database fields" - 100% compliance
- [ ] ✅ Rule 010: Zero tolerance for legacy patterns - fully achieved
- [ ] ✅ Rule 020: No backwards compatibility mandates - strictly followed

## 🚀 SUCCESS METRICS

**Immediate Benefits**:
- 100% elimination of deprecated skill_level field
- Simplified database schema
- Dynamic skill level determination
- Full architectural compliance

**Long-term Benefits**:
- Single source of truth for skill levels
- Automatic skill level management via course codes
- Reduced data duplication
- Foundation for advanced course categorization

## 📅 IMPLEMENTATION ESTIMATE

**Total Effort**: 1-2 days (8-12 hours)
- **Day 1**: Database migration + business logic updates (6-8 hours)
- **Day 2**: Test updates + validation (2-4 hours)

**Risk Level**: LOW
- Isolated to Class Management service only
- Modern replacement already fully implemented
- Clear rollback path available through Alembic
- Minimal cross-service dependencies

**Files Modified**: 4 total + 1 new migration
- **Database Changes**: 1 model file + 1 migration
- **Business Logic**: 1 implementation file
- **Test Updates**: 2 test files

This migration plan ensures immediate compliance with the "NO backwards compatibility" mandate while leveraging the existing robust domain enum infrastructure for dynamic skill level determination.