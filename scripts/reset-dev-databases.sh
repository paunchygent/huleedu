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