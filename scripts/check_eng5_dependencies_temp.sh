#!/bin/bash

echo "=== Checking Infrastructure Services ==="
echo -n "Kafka: "
docker ps --filter "name=huleedu_kafka" --filter "status=running" --format "{{.Status}}" || echo "NOT RUNNING"

echo -n "Zookeeper: "
docker ps --filter "name=huleedu_zookeeper" --filter "status=running" --format "{{.Status}}" || echo "NOT RUNNING"

echo -n "Redis: "
docker ps --filter "name=huleedu_redis" --filter "status=running" --format "{{.Status}}" || echo "NOT RUNNING"

echo -e "\n=== Checking Database Services ==="
for db in content_service cj_assessment essay_lifecycle batch_orchestrator result_aggregator; do
  echo -n "${db}_db: "
  docker ps --filter "name=huleedu_${db}_db" --filter "status=running" --format "{{.Status}}" || echo "NOT RUNNING"
done

echo -e "\n=== Checking Application Services ==="
services=(
  "content_service:8001"
  "essay_lifecycle_service:8002"
  "cj_assessment_service:9095"
  "llm_provider_service:9097"
  "result_aggregator:4003"
  "batch_orchestrator_service:9096"
)

all_healthy=true
for svc in "${services[@]}"; do
  name="${svc%:*}"
  port="${svc#*:}"
  echo -n "${name}: "

  # Check container running
  if ! docker ps --filter "name=huleedu_${name}" --filter "status=running" -q > /dev/null 2>&1; then
    echo "❌ NOT RUNNING"
    all_healthy=false
    continue
  fi

  # Check HTTP health endpoint
  if curl -sf "http://localhost:${port}/healthz" > /dev/null 2>&1; then
    echo "✅ HEALTHY (port ${port})"
  else
    echo "⚠️  RUNNING but health check failed"
    all_healthy=false
  fi
done

echo -e "\n=== Checking Kafka Topics ==="
docker exec huleedu_kafka kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | \
  grep -E "(els|cj|llm|assessment)" | head -10

if [ "$all_healthy" = true ]; then
  echo -e "\n✅ ALL REQUIRED SERVICES ARE HEALTHY"
  exit 0
else
  echo -e "\n❌ SOME SERVICES ARE NOT HEALTHY"
  exit 1
fi
