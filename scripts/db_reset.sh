#!/bin/bash
#
# Comprehensive Database Reset Script for HuleEdu Development
#
# This script:
# 1. Stops all services
# 2. Removes all database volumes
# 3. Recreates databases
# 4. Applies all migrations
# 5. Seeds reference data
#

set -e  # Exit on error

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "🔄 HuleEdu Database Reset Script"
echo "=================================="
echo "⚠️  WARNING: This will DELETE all database data!"
echo ""
read -p "Are you sure you want to continue? (yes/no): " -n 3 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]es$ ]]; then
    echo "❌ Aborted"
    exit 1
fi

cd "$PROJECT_ROOT"

echo ""
echo "1️⃣  Stopping all services..."
echo "----------------------------"
pdm run down || true

echo ""
echo "2️⃣  Removing database volumes..."
echo "--------------------------------"
# Remove all HuleEdu database volumes
docker volume ls | grep huleedu | awk '{print $2}' | xargs -r docker volume rm 2>/dev/null || true
echo "✅ Database volumes removed"

echo ""
echo "3️⃣  Starting databases only..."
echo "------------------------------"
# Start only the database containers
docker compose up -d \
    huleedu_batch_orchestrator_db \
    huleedu_class_management_db \
    huleedu_essay_lifecycle_db \
    huleedu_cj_assessment_db \
    huleedu_result_aggregator_db \
    huleedu_spellchecker_db \
    huleedu_file_service_db \
    huleedu_nlp_db \
    redis \
    kafka

echo "⏳ Waiting for databases to be ready..."
sleep 10

echo ""
echo "4️⃣  Initializing all databases..."
echo "---------------------------------"
# Run the comprehensive initialization script
pdm run python scripts/init_all_databases.py

if [ $? -eq 0 ]; then
    echo ""
    echo "5️⃣  Starting all services..."
    echo "---------------------------"
    pdm run up
    
    echo ""
    echo "✅ Database reset complete!"
    echo ""
    echo "All databases have been:"
    echo "  • Recreated from scratch"
    echo "  • Migrated to latest schema"
    echo "  • Seeded with reference data"
    echo ""
    echo "Services are now running and ready for development/testing."
else
    echo ""
    echo "❌ Database initialization failed!"
    echo "Please check the logs above for details."
    exit 1
fi