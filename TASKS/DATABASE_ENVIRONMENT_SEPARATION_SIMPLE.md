# Database Environment Separation - Development/Production Toggle

## Context & Problem Statement

**Current State**: The HuleEdu monorepo uses individual PostgreSQL containers per microservice (DDD compliance), but lacks clear separation between development and production database environments.

**Validated Current Architecture**:
- ✅ Individual PostgreSQL containers per service (`docker-compose.infrastructure.yml`)
- ✅ Service-specific databases: `huleedu_batch_orchestrator`, `huleedu_class_management`, etc.
- ✅ Environment-aware service configuration using `Environment` enum (DEVELOPMENT, STAGING, PRODUCTION, TESTING)
- ✅ Development workflow with hot-reload (`docker-compose.dev.yml`)
- ✅ Existing environment variable pattern: `HULEEDU_DB_USER`, `HULEEDU_DB_PASSWORD`

**Problem**: Need clean separation between development (Docker containers) and production (external databases) without over-engineering.

## Solution: Two-Tier Database Architecture

### **Development Environment** (Current Docker Setup)
- **Purpose**: Local development, testing, service interaction validation
- **Infrastructure**: Docker PostgreSQL containers (existing setup)
- **Data**: Disposable, seedable, resetable

### **Production Environment** (External Deployment)  
- **Purpose**: Live application data
- **Infrastructure**: Managed PostgreSQL (AWS RDS, Google Cloud SQL, etc.)
- **Data**: Persistent, backed up, monitored

## Implementation Plan

### Phase 1: Enhance Current Development Setup (2 hours)

#### 1.1 Update Environment Configuration

**File**: `env.example`
```bash
# Add to existing env.example (preserve current variables)

# =============================================================================  
# Database Environment Toggle
# =============================================================================
HULEEDU_ENVIRONMENT=development  # development | production

# Production Database Configuration (when HULEEDU_ENVIRONMENT=production)
HULEEDU_PROD_DB_HOST=your-production-db-host
HULEEDU_PROD_DB_PORT=5432
HULEEDU_PROD_DB_PASSWORD=your-secure-production-password
```

#### 1.2 Update Service Configuration Pattern

**Template** for each service's `config.py` (Example: `services/class_management_service/config.py`):

```python
@property
def DATABASE_URL(self) -> str:
    """Return the PostgreSQL database URL for both runtime and migrations.
    
    Environment-aware database connection:
    - DEVELOPMENT: Docker container (localhost with unique port)
    - PRODUCTION: External managed database
    """
    import os
    
    # Check for explicit override first (Docker environment, manual config)
    env_url = os.getenv("CLASS_MANAGEMENT_SERVICE_DATABASE_URL") 
    if env_url:
        return env_url
        
    # Environment-based configuration
    environment = os.getenv("HULEEDU_ENVIRONMENT", "development").lower()
    
    if environment == "production":
        # Production: External managed database
        prod_host = os.getenv("HULEEDU_PROD_DB_HOST")
        prod_port = os.getenv("HULEEDU_PROD_DB_PORT", "5432")
        prod_password = os.getenv("HULEEDU_PROD_DB_PASSWORD") 
        
        if not all([prod_host, prod_password]):
            raise ValueError(
                "Production environment requires HULEEDU_PROD_DB_HOST and "
                "HULEEDU_PROD_DB_PASSWORD environment variables"
            )
            
        return (
            f"postgresql+asyncpg://{self._db_user}:{prod_password}@"
            f"{prod_host}:{prod_port}/huleedu_class_management"
        )
    else:
        # Development: Docker container (existing pattern)
        db_user = os.getenv("HULEEDU_DB_USER")
        db_password = os.getenv("HULEEDU_DB_PASSWORD") 
        
        if not db_user or not db_password:
            raise ValueError(
                "Missing required database credentials. Please ensure HULEEDU_DB_USER and "
                "HULEEDU_DB_PASSWORD are set in your .env file."
            )
            
        return (
            f"postgresql+asyncpg://{db_user}:{db_password}@localhost:5435/huleedu_class_management"
        )

@property        
def _db_user(self) -> str:
    """Database user for production connections."""
    return os.getenv("HULEEDU_DB_USER", "huleedu_user")
```

**Services to Update** (apply same pattern):
- `services/class_management_service/config.py` (port 5435)
- `services/batch_orchestrator_service/config.py` (port 5438) 
- `services/essay_lifecycle_service/config.py` (port 5433)
- `services/cj_assessment_service/config.py` (port 5434)
- `services/file_service/config.py` (port 5439)
- `services/spellchecker_service/config.py` (port 5437)
- `services/result_aggregator_service/config.py` (port 5436)
- `services/nlp_service/config.py` (port 5440)

**Port Reference** (from `docker-compose.infrastructure.yml`):
```yaml
batch_orchestrator_db: "5438:5432"
essay_lifecycle_db: "5433:5432" 
cj_assessment_db: "5434:5432"
class_management_db: "5435:5432"
file_service_db: "5439:5432"
spellchecker_db: "5437:5432"
result_aggregator_db: "5436:5432"
nlp_db: "5440:5432"
```

#### 1.3 Create Development Database Management Scripts

**File**: `scripts/reset-dev-databases.sh`
```bash
#!/bin/bash
# Reset all development databases to clean state

set -e
source .env

echo "🗑️  Resetting development databases..."

# Stop services to prevent connection issues
docker compose down

# Remove database volumes  
docker volume rm -f $(docker volume ls -q | grep -E "(batch_orchestrator|essay_lifecycle|cj_assessment|class_management|file_service|spellchecker|result_aggregator|nlp)_db_data")

# Restart infrastructure
docker compose up -d batch_orchestrator_db essay_lifecycle_db cj_assessment_db class_management_db file_service_db spellchecker_db result_aggregator_db nlp_db

echo "⏳ Waiting for databases to be ready..."
sleep 10

# Run migrations for all services
services=("batch_orchestrator" "essay_lifecycle" "cj_assessment" "class_management" "file_service" "spellchecker" "result_aggregator" "nlp")

for service in "${services[@]}"; do
    if [ -d "services/${service}_service" ]; then
        echo "📄 Running migrations for ${service}_service..."
        (cd "services/${service}_service" && pdm run alembic upgrade head)
    fi
done

echo "✅ Development databases reset complete!"
echo "💡 Seed test data with: ./scripts/seed-dev-data.sh"
```

**File**: `scripts/seed-dev-data.sh`
```bash
#!/bin/bash
# Seed development databases with test data

set -e
source .env

echo "🌱 Seeding development databases with test data..."

# Create seed data script directory if it doesn't exist
mkdir -p database/seed-scripts

# TODO: Implement service-specific seed scripts
echo "📝 TODO: Create seed scripts in database/seed-scripts/"
echo "   - database/seed-scripts/seed_class_management.py" 
echo "   - database/seed-scripts/seed_batch_orchestrator.py"
echo "   - etc."

echo "✅ Development database seeding ready for implementation"
```

### Phase 2: Production Deployment Preparation (1 hour)

#### 2.1 Production Environment Validation

**File**: `scripts/validate-production-config.sh`
```bash
#!/bin/bash
# Validate production database configuration

set -e

if [ "$HULEEDU_ENVIRONMENT" != "production" ]; then
    echo "❌ HULEEDU_ENVIRONMENT must be set to 'production'"
    exit 1
fi

# Check required production variables
required_vars=(
    "HULEEDU_PROD_DB_HOST" 
    "HULEEDU_PROD_DB_PASSWORD"
    "HULEEDU_DB_USER"
)

missing_vars=()
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -ne 0 ]; then
    echo "❌ Missing required production environment variables:"
    printf '   - %s\n' "${missing_vars[@]}"
    exit 1
fi

echo "✅ Production configuration validated"
echo "🔗 Database host: $HULEEDU_PROD_DB_HOST"
echo "👤 Database user: $HULEEDU_DB_USER"
```

#### 2.2 Production Migration Script

**File**: `scripts/migrate-production.sh`
```bash
#!/bin/bash
# Run production database migrations with safety checks

set -e

if [ "$HULEEDU_ENVIRONMENT" != "production" ]; then
    echo "❌ HULEEDU_ENVIRONMENT must be set to 'production'"
    exit 1
fi

echo "⚠️  PRODUCTION DATABASE MIGRATION"
echo "   This will modify production databases"
echo "   Host: $HULEEDU_PROD_DB_HOST"
echo ""
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "❌ Migration cancelled"
    exit 1
fi

# Validate production configuration
./scripts/validate-production-config.sh

# Run migrations for all services
services=("batch_orchestrator" "essay_lifecycle" "cj_assessment" "class_management" "file_service" "spellchecker" "result_aggregator" "nlp")

for service in "${services[@]}"; do
    if [ -d "services/${service}_service" ]; then
        echo "📄 Running PRODUCTION migrations for ${service}_service..."
        (cd "services/${service}_service" && pdm run alembic upgrade head)
    fi
done

echo "✅ Production migrations complete!"
```

## Usage Patterns

### Development Workflow (Current + Enhanced)

```bash
# 1. Standard development (no changes to existing workflow)
./scripts/dev-workflow.sh dev class_management_service

# 2. Reset development databases when needed
./scripts/reset-dev-databases.sh

# 3. Seed test data for development
./scripts/seed-dev-data.sh

# 4. Standard production build (existing)
docker compose build class_management_service
```

### Production Deployment (New)

```bash  
# 1. Set production environment
export HULEEDU_ENVIRONMENT=production
export HULEEDU_PROD_DB_HOST=your-db-host.com
export HULEEDU_PROD_DB_PASSWORD=secure-password

# 2. Validate configuration  
./scripts/validate-production-config.sh

# 3. Run production migrations
./scripts/migrate-production.sh

# 4. Deploy services (existing patterns apply)
docker compose build --no-cache
# Deploy to your infrastructure (K8s, Docker Swarm, etc.)
```

## Validation Checklist

### Development Environment
- [ ] All services connect to correct Docker database containers
- [ ] Environment variable `HULEEDU_ENVIRONMENT=development` works
- [ ] Hot-reload continues working with existing `docker-compose.dev.yml`
- [ ] Database reset script successfully recreates clean state
- [ ] All existing development workflows continue unchanged

### Production Environment  
- [ ] Services connect to external production databases when `HULEEDU_ENVIRONMENT=production`
- [ ] Production validation script catches missing configuration
- [ ] Migration script requires explicit confirmation for safety
- [ ] Service configuration throws clear error messages for missing production variables

## Implementation Notes

### Service-Specific Database Ports
Each service uses a unique port for development Docker containers:
- `batch_orchestrator_service`: localhost:5438
- `essay_lifecycle_service`: localhost:5433
- `cj_assessment_service`: localhost:5434  
- `class_management_service`: localhost:5435
- `file_service`: localhost:5439
- `spellchecker_service`: localhost:5437
- `result_aggregator_service`: localhost:5436
- `nlp_service`: localhost:5440

### Configuration Override Hierarchy
1. **Explicit override**: `{SERVICE}_DATABASE_URL` environment variable
2. **Environment-based**: `HULEEDU_ENVIRONMENT` drives connection logic
3. **Fallback**: Error with clear message if configuration incomplete

### Minimal Change Principle
- ✅ Leverages existing `Environment` enum and service configuration patterns  
- ✅ Preserves all current development workflows
- ✅ No changes to Docker infrastructure
- ✅ No changes to existing database naming or port allocation
- ✅ Maintains microservice-per-database DDD compliance

## Time Estimate: 3 hours total
- Phase 1 (Development Enhancement): 2 hours
- Phase 2 (Production Preparation): 1 hour

**Dependencies**: None - builds on existing validated architecture
**Testing**: Test environment switching with sample service to validate configuration logic before rolling out to all services