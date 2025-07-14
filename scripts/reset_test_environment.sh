#!/bin/bash
# Reset test environment for clean E2E test runs

echo "🧹 Resetting test environment..."

# Stop all worker services
echo "📦 Stopping worker services..."
docker compose down essay_lifecycle_worker spellchecker_service cj_assessment_service result_aggregator_service

# Clear Redis completely
echo "🗑️ Clearing Redis..."
docker compose exec redis redis-cli FLUSHALL

# Delete all Kafka topics related to the test
echo "🗑️ Deleting Kafka topics..."
docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic huleedu.essay.spellcheck.completed.v1 || true
docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic huleedu.essay.spellcheck.requested.v1 || true
docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic huleedu.cj_assessment.completed.v1 || true
docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic huleedu.batch.essays.registered.v1 || true
docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic huleedu.file.essay.content.provisioned.v1 || true
docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic huleedu.els.batch.essays.ready.v1 || true
docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic huleedu.els.batch.phase.outcome.v1 || true
docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic huleedu.els.spellcheck.initiate.command.v1 || true
docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic huleedu.batch.cj_assessment.initiate.command.v1 || true

# Wait for deletion to complete
sleep 5

# Recreate topics
echo "✨ Recreating Kafka topics..."
docker compose up -d kafka_topic_setup
sleep 10

# Start all worker services
echo "🚀 Starting worker services..."
docker compose up -d essay_lifecycle_worker spellchecker_service cj_assessment_service result_aggregator_service


# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 15

echo "✅ Test environment reset complete!"