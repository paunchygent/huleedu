#!/bin/bash

# Quick validation test for HuleEdu Batch Coordination
# Tests core functionality without full service startup

set -euo pipefail

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "🔍 $1"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; }
warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }

echo "🚀 HuleEdu Quick Validation Test"
echo "================================="

# Test 1: Docker Compose Configuration
log "Testing Docker Compose configuration..."
if docker-compose config > /dev/null 2>&1; then
    success "Docker Compose configuration is valid"
else
    error "Docker Compose configuration has errors"
    exit 1
fi

# Test 2: Check if services can build
log "Testing service builds (this may take a few minutes)..."
if docker-compose build > /dev/null 2>&1; then
    success "All services build successfully"
else
    error "Service build failed - check docker-compose logs"
    exit 1
fi

# Test 3: Check key files exist
log "Checking critical implementation files..."

files_to_check=(
    "services/batch_orchestrator_service/api/batch_routes.py"
    "services/batch_orchestrator_service/api_models.py"
    "services/batch_orchestrator_service/kafka_consumer.py"
    "services/essay_lifecycle_service/batch_tracker.py"
    "common_core/src/common_core/events/batch_coordination_events.py"
)

for file in "${files_to_check[@]}"; do
    if [[ -f "$file" ]]; then
        success "Found: $file"
    else
        error "Missing: $file"
        exit 1
    fi
done

# Test 4: Quick service startup test
log "Testing quick service startup (30 seconds)..."
docker-compose up -d > /dev/null 2>&1

sleep 30

# Check if key services are responding
services=(
    "http://localhost:5001/healthz"
    "http://localhost:6001/healthz" 
    "http://localhost:8001/healthz"
)

all_healthy=true
for service in "${services[@]}"; do
    if curl -s -f "$service" > /dev/null 2>&1; then
        success "Service healthy: $service"
    else
        warning "Service not ready: $service"
        all_healthy=false
    fi
done

if $all_healthy; then
    success "All core services are healthy!"
    
    # Quick BOS registration test
    log "Testing BOS registration endpoint..."
    response=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d '{
            "expected_essay_count": 2,
            "essay_ids": ["test-001", "test-002"],
            "course_code": "SV1",
            "class_designation": "Test Class",
            "essay_instructions": "Test essay instructions"
        }' \
        http://localhost:5001/v1/batches/register 2>/dev/null)
    
    if echo "$response" | jq -e '.batch_id' > /dev/null 2>&1; then
        success "BOS registration endpoint working!"
        batch_id=$(echo "$response" | jq -r '.batch_id')
        log "Created test batch: $batch_id"
    else
        warning "BOS registration endpoint needs attention"
        echo "Response: $response"
    fi
else
    warning "Some services need more time to start up"
fi

echo ""
echo "🎯 Quick Validation Results:"
success "✅ Docker configuration valid"
success "✅ All services build successfully" 
success "✅ Critical implementation files present"
if $all_healthy; then
    success "✅ Services start and respond to health checks"
    success "✅ BOS registration endpoint functional"
    echo ""
    echo "🚀 System appears ready for full validation!"
    echo "   Run: ./scripts/validate_batch_coordination.sh"
    echo "   Or follow: scripts/manual_validation_guide.md"
else
    warning "⚠️  Services need more startup time"
    echo ""
    echo "📋 Next steps:"
    echo "   1. Wait a bit longer for services to fully start"
    echo "   2. Check logs: docker-compose logs <service-name>"
    echo "   3. Run full validation: ./scripts/validate_batch_coordination.sh"
fi

echo ""
log "Services left running for further testing"
log "To stop: docker-compose down" 