---
description: Systematic approach for debugging HuleEdu Docker containers and services
globs: 
alwaysApply: false
---
# 046: Docker Container Debugging Protocol

## Container Discovery (ALWAYS FIRST)
```bash
# 1. Find ALL containers (services + databases)
docker ps | grep huleedu

# 2. Service patterns:
# - Combined: {service}_service (spellchecker, cj_assessment, batch_orchestrator)  
# - Split: {service}_api + {service}_worker (essay_lifecycle)
# - Database: huleedu_{service}_db
```

## Service Logs Access
```bash
# Check container exists FIRST
docker ps | grep <service_pattern>

# Then access logs
docker logs huleedu_<container_name> --tail 50
docker logs huleedu_<container_name> 2>&1 | grep -E "error|failed|exception"
docker logs huleedu_<container_name> 2>&1 | grep "<correlation_id>"
```

## Database Access Pattern
```bash
# Database container: huleedu_{service}_db
# Database name: huleedu_{service}
# User: huleedu_user

docker exec huleedu_{service}_db psql -U huleedu_user -d huleedu_{service} -c "SQL"

# Examples:
docker exec huleedu_spellchecker_db psql -U huleedu_user -d huleedu_spellchecker -c "\dt"
docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment -c "SELECT * FROM event_outbox"
```

## Service Container Mapping
| Service | Container(s) | Database |
|---------|-------------|----------|
| batch_orchestrator | huleedu_batch_orchestrator_service | huleedu_batch_orchestrator_db |
| essay_lifecycle | huleedu_essay_lifecycle_api, huleedu_essay_lifecycle_worker | huleedu_essay_lifecycle_db |
| spellchecker | huleedu_spellchecker_service | huleedu_spellchecker_db |
| cj_assessment | huleedu_cj_assessment_service | huleedu_cj_assessment_db |
| class_management | huleedu_class_management_service | huleedu_class_management_db |
| file_service | huleedu_file_service | huleedu_file_service_db |
| content_service | huleedu_content_service | huleedu_content_db |
| result_aggregator | huleedu_result_aggregator_service | huleedu_result_aggregator_db |

## Development Workflow Commands
```bash
# Start development environment with hot-reload
./scripts/dev-workflow.sh dev <service_name>

# Check what services need rebuilding
./scripts/dev-workflow.sh check

# Build development version with cache optimization
./scripts/dev-workflow.sh build dev <service_name>

# Incremental build (all services)
./scripts/dev-workflow.sh incremental

# Start services with development compose
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up <service_name>
```

## Debug Workflow
1. **ALWAYS** use `docker ps | grep huleedu` first
2. **VERIFY** container name before accessing logs
3. **CHECK** service architecture (combined vs split)
4. **USE** correlation IDs to trace across services
5. **ACCESS** databases with standard pattern above
6. **USE** development commands for optimized builds (no --no-cache needed)

## 4. Container Log Debugging Best Practices

### 4.1. DO's for Container Logs
- **Start broad, then narrow**: Get recent logs first, then search
  ```bash
  # GOOD - see what's actually happening
  docker logs <container_name> --tail 200 2>&1 | grep -i processing
  ```
- **Use `--since` for time-based filtering**:
  ```bash
  docker logs <container_name> --since 1m 2>&1 | tail -50
  ```
- **Always redirect stderr**: Use `2>&1` to capture all output
- **Check container is running first**:
  ```bash
  docker ps | grep <service_name>
  ```

### 4.2. DON'Ts for Container Logs  
- **Don't grep for overly specific strings** that might not exist:
  ```bash
  # BAD - returns nothing even when events exist
  docker logs <container> | grep "exact string that may not appear"
  ```
- **Don't assume no output means no activity** - the log level might be wrong
- **Don't pipe grep to grep** - use regex patterns instead:
  ```bash
  # BAD
  docker logs <container> | grep ERROR | grep specific_error
  # GOOD
  docker logs <container> 2>&1 | grep -E "ERROR.*specific|specific.*ERROR"
  ```

### 4.3. Kafka Consumer Debugging
- **Check consumer group status**:
  ```bash
  docker exec huleedu_kafka /opt/bitnami/kafka/bin/kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 --group <group_name> --describe
  ```
- **Look for LAG values** - 0 means all messages consumed
- **Check if consumer is in the group** - missing means not connected
