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