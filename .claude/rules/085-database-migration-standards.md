---
description: Database migration standards for HuleEdu microservices
globs: 
alwaysApply: true
---
# 085: Database Migration Standards

## 1. Pre-Migration Analysis (MANDATORY)

**Before ANY migration, MUST check state:**
```bash
cd services/<service> && ../../.venv/bin/alembic current
docker exec huleedu_<service>_db psql -U ${HULEEDU_DB_USER} -d <db> -c "\dt"
```

## 2. State Scenarios

**Schema exists, no tracking:** `../../.venv/bin/alembic stamp <revision>` then `../../.venv/bin/alembic upgrade head`
**Clean state:** Direct `../../.venv/bin/alembic upgrade head`

## 3. Migration Commands (REQUIRED)

**Use monorepo venv directly from service directory:**
```bash
cd services/<service>
../../.venv/bin/alembic upgrade head
../../.venv/bin/alembic current
../../.venv/bin/alembic stamp <revision>
../../.venv/bin/alembic revision --autogenerate -m "description"
```

### Recommended Dev Reset Workflow
- Use `pdm run db-reset` (wrapper for `scripts/reset-dev-databases.sh`) when you need a clean slate across all dev databases.
- The script autodiscovers Alembic-enabled services, stops the matching `<service>_db` containers, deletes the `*_db_data` volumes, restarts fresh Postgres instances, waits for `pg_isready`, and runs `../../.venv/bin/alembic upgrade head` per service.
- **Destructive:** drops every dev database; do not run if you need to preserve local data.

## 4. Automated Safety Checks (MANDATORY)

- **Service-level smoke test:** every service MUST provide an automated check (CI or
  local script) that provisions an ephemeral PostgreSQL instance (TestContainers or
  docker-compose) and runs `../../.venv/bin/alembic upgrade head`. This regression test
  guards against enum/type duplication and other DDL conflicts before migrations merge.
- **Enum creation policy:** prefer SQLAlchemy-managed enums over ad-hoc `CREATE TYPE`
  statements. Use `postgresql.ENUM(..., name="<enum_name>")` and let Alembic emit the
  DDL, or set `create_type=False` when the enum already exists. Manual
  `op.execute("CREATE TYPE ...")` MUST be accompanied by `create_type=False` on any
  `postgresql.ENUM` columns referencing the type to avoid duplicate creation errors.

## 5. Prohibited Practices

**FORBIDDEN:**
- PDM service-specific commands (`pdm run -p services/<service>`)
- Service-specific venv usage
- PYTHONPATH hacks
- Manual SQL schema changes
- Applying migrations without state analysis
- Absolute imports in alembic/env.py

## 6. Post-Migration Verification

**MUST verify after migration:**
```bash
cd services/<service> && ../../.venv/bin/alembic current

# Database Access Pattern (IMPORTANT - Environment variables are NOT available in shell by default)
# Option 1: Load environment first
source /Users/olofs_mba/Documents/Repos/huledu-reboot/.env
docker exec huleedu_<service>_db psql -U $HULEEDU_DB_USER -d <db_name> -c "\d <table>"

# Option 2: Use hardcoded user (from .env file)
docker exec huleedu_<service>_db psql -U huleedu_user -d <db_name> -c "\d <table>"
```

**Database Name Mapping:**
| Service | Container Name | Database Name | Port |
|---------|---------------|---------------|------|
| `cj_assessment_service` | `huleedu_cj_assessment_db` | `huleedu_cj_assessment` | 5434 |
| `class_management_service` | `huleedu_class_management_db` | `huleedu_class_management` | 5435 |
| `essay_lifecycle_service` | `huleedu_essay_lifecycle_db` | `huleedu_essay_lifecycle` | 5433 |
| `batch_orchestrator_service` | `huleedu_batch_orchestrator_db` | `huleedu_batch_orchestrator` | 5438 |
| `result_aggregator_service` | `huleedu_result_aggregator_db` | `huleedu_result_aggregator` | 5436 |
| `spellchecker_service` | `huleedu_spellchecker_db` | `huleedu_spellchecker` | 5437 |
| `file_service` | `huleedu_file_service_db` | `huleedu_file_service` | 5439 |
| `nlp_service` | `huleedu_nlp_db` | `huleedu_nlp` | 5440 |
| `email_service` | `huleedu_email_db` | `huleedu_email` | 5443 |

## 7. Secure Configuration Pattern (MANDATORY)

**All service config.py files MUST implement secure credential loading:**

```python
# Required imports at top of config.py
from dotenv import find_dotenv, load_dotenv

# Load .env file from repository root, regardless of current working directory
load_dotenv(find_dotenv(".env"))

# In database_url property
@property
def database_url(self) -> str:
    """Return the PostgreSQL database URL for both runtime and migrations."""
    import os

    # Check for environment variable first (Docker environment)
    env_url = os.getenv("SERVICE_DATABASE_URL")
    if env_url:
        return env_url

    # Fallback to local development configuration (loaded from .env via dotenv)
    db_user = os.getenv("HULEEDU_DB_USER")
    db_password = os.getenv("HULEEDU_DB_PASSWORD")
    
    if not db_user or not db_password:
        raise ValueError(
            "Missing required database credentials. Please ensure HULEEDU_DB_USER and "
            "HULEEDU_DB_PASSWORD are set in your .env file."
        )
    
    return f"postgresql+asyncpg://{db_user}:{db_password}@localhost:{port}/{database}"
```

**Security Requirements:**
- **NO hardcoded secrets** - Only example placeholder values allowed
- **Automatic .env discovery** - Works from any working directory
- **Clear error messages** - Guide developers to proper configuration
- **Environment precedence** - Docker can override with specific URLs

## 8. Operational Services (VERIFIED)

**All 8 Alembic-enabled services are fully operational with secure configuration:**

| Service | Database Port | Status | Security Status |
|---------|---------------|--------|-----------------|
| `cj_assessment_service` | 5434 | ✅ OPERATIONAL | ✅ SECURE |
| `class_management_service` | 5435 | ✅ OPERATIONAL | ✅ SECURE |
| `essay_lifecycle_service` | 5433 | ✅ OPERATIONAL | ✅ SECURE |
| `batch_orchestrator_service` | 5438 | ✅ OPERATIONAL | ✅ SECURE |
| `result_aggregator_service` | 5436 | ✅ OPERATIONAL | ✅ SECURE |
| `spellchecker_service` | 5437 | ✅ OPERATIONAL | ✅ SECURE |
| `nlp_service` | 5440 | ✅ OPERATIONAL | ✅ SECURE |
| `email_service` | 5443 | ⚠️ SETUP | ⚠️ SETUP |

**Integration verified:** All services successfully execute `../../.venv/bin/alembic current`
**Security verified:** No hardcoded secrets in any configuration files

---
**Understand state before changing. Use established tools. Never hardcode secrets.**
