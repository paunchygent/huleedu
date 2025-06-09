# Pre-Migration Task: Fix Critical Kafka Configuration Issues

## 🚨 CRITICAL PRE-REQUISITE for PHASE_1.3_KAFKA_CLIENT_MIGRATION

**Status**: 🔴 **BLOCKING** - Environment consistency fixes required  
**Priority**: P0 - Service library has critical bootstrap server issue  
**Estimated Effort**: 0.5 days  

## 🎯 Objective

Fix critical bootstrap server configuration inconsistency that breaks containerized deployment. Remove premature optimization configurations and use service library defaults.

## 📊 Critical Issues Analysis

### CRITICAL: Environment Configuration Inconsistency

| **Service** | **Current Bootstrap Servers** | **Status** | **Impact** |
|-------------|------------------------------|------------|------------|
| spell_checker_service | "kafka:9092" | ✅ **Correct** | Works in containers |
| batch_orchestrator_service | "kafka:9092" | ✅ **Correct** | Works in containers |
| essay_lifecycle_service | "kafka:9092" | ✅ **Correct** | Works in containers |
| **cj_assessment_service** | **"localhost:9092"** | ❌ **BROKEN** | **Cannot connect in containers** |
| file_service | "kafka:9092" | ✅ **Correct** | Works in containers |
| content_service | "kafka:9092" | ✅ **Correct** | Works in containers |

### REMOVE: Premature Optimization Configurations

| **Configuration** | **Spell Checker** | **Decision** | **Rationale** |
|-------------------|-------------------|--------------|---------------|
| `max_poll_records` | 500 | 🗑️ **Remove** | Kafka default (~500) is fine for prototype |
| `max_poll_interval_ms` | 300000 | 🗑️ **Remove** | Default timeout works for prototype |
| `session_timeout_ms` | 30000 | 🗑️ **Remove** | Service library default is adequate |
| `heartbeat_interval_ms` | 10000 | 🗑️ **Remove** | Service library default is adequate |

## 🔧 Required Changes (Minimal)

### 1. Fix CJ Assessment Service Bootstrap Configuration

**File**: `services/cj_assessment_service/config.py`

```python
# BEFORE (BROKEN in containers)
KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"

# AFTER (Consistent with all other services)  
KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
```

### 2. Service Library Already Supports Everything We Need

**No changes required to `huleedu-service-libs`** - the current implementation has:
- ✅ Configurable `bootstrap_servers` parameter
- ✅ Consumer group and client_id support  
- ✅ Sensible Kafka defaults for all timing parameters
- ✅ Manual commit support (`enable_auto_commit=False`)
- ✅ Proper error handling and logging
```

## 🔍 Simplified Migration Patterns

### All Services: Use Service Library Defaults

```python
# BEFORE (Over-engineered custom configuration)
consumer = AIOKafkaConsumer(
    input_topic,
    bootstrap_servers=bootstrap_servers,
    group_id=consumer_group_id,
    client_id=consumer_client_id,
    enable_auto_commit=False,
    auto_offset_reset="earliest",
    max_poll_records=500,  # 🗑️ Remove - use defaults
    max_poll_interval_ms=300000,  # 🗑️ Remove - use defaults  
    session_timeout_ms=30000,  # 🗑️ Remove - use defaults
    heartbeat_interval_ms=10000,  # 🗑️ Remove - use defaults
)

# AFTER (Clean service library usage)
from huleedu_service_libs.kafka_client import consume_events

async for msg in consume_events(
    topics=input_topic,
    
    client_id=consumer_client_id,
    bootstrap_servers=bootstrap_servers,
    enable_auto_commit=False,
    auto_offset_reset="earliest"
):
    # Same message processing logic - zero changes needed
```

## ✅ Simple Migration Checklist

### Critical Fix Only
- [ ] **CJ Assessment**: Fix bootstrap servers from "localhost:9092" to "kafka:9092"

### Validation (Keep Essential Groups)
- [ ] **BOS**: Consumer group "batch-orchestrator-group" preserved
- [ ] **ELS**: Consumer group "essay-lifecycle-service-group-v1.0" preserved  
- [ ] **Spell Checker**: Consumer group "spellchecker-service-group-v1.1" preserved
- [ ] **CJ Assessment**: Consumer group "cj_assessment_consumer_group" preserved

## 🚧 Migration Sequence

1. **Fix CJ Assessment bootstrap config** (This task - 0.5 days)
2. **Execute PHASE_1.3_KAFKA_CLIENT_MIGRATION** using service library defaults
3. **Remove optimization configurations** from all services during migration

## 📚 References

- **Service Library Source**: `services/libs/huleedu_service_libs/kafka_client.py` (already sufficient)
- **Migration Task**: `Documentation/TASKS/PHASE_1.3_KAFKA_CLIENT_MIGRATION.md`

---

**Simple fix before clean migration - no complex enhancements needed.** 