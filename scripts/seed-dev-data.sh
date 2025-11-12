#!/bin/bash
# Seed development databases with test data

set -euo pipefail

if [ ! -f .env ]; then
  echo "❌ .env file not found. Please create it before seeding."
  exit 1
fi

source .env

echo "🌱 Seeding development databases with test data..."

# Ensure seed script directory exists for future additions
mkdir -p database/seed-scripts

echo "📘 Seeding Class Management Service courses..."
pdm run python scripts/seed_courses.py

echo "✅ Development database seeding complete"