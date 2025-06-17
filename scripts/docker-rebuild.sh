#!/bin/bash

# Docker Rebuild Script
# Performs a complete rebuild of the Docker Compose environment
# Usage: ./scripts/docker-rebuild.sh [--reset]

set -e  # Exit on any error

echo "🐳 Starting Docker environment rebuild..."

# Check if --reset flag is provided
RESET_VOLUMES=false
if [[ "$1" == "--reset" ]]; then
    RESET_VOLUMES=true
    echo "⚠️  RESET MODE: Will remove volumes (all data will be lost!)"
fi

# Step 1: Stop and remove containers, networks, and orphans
echo "📦 Stopping and removing containers..."
if [[ "$RESET_VOLUMES" == "true" ]]; then
    docker compose down --remove-orphans --volumes
    echo "🗑️  Removed volumes (data reset)"
else
    docker compose down --remove-orphans
fi

# Step 2: Build images
echo "🔨 Building Docker images..."
docker compose build

# Step 3: Start services
echo "🚀 Starting services..."
docker compose up -d

# Step 4: Show status
echo "✅ Docker rebuild complete!"
echo ""
echo "📊 Service status:"
docker compose ps

echo ""
echo "📝 To view logs: pdm run docker-logs"
echo "📝 To stop services: pdm run docker-down" 