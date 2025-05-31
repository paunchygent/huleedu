#!/bin/bash
# scripts/functional_tests.sh
# Replication methodology for HuleEdu microservices functional testing
# 
# This script replicates the functional testing approach used to identify
# service issues and verify end-to-end workflow functionality

set -e  # Exit on error

echo "=== HuleEdu Functional Testing ==="
echo "Testing microservices reachability and functionality..."
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test results tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Function to log test results
log_test() {
    local test_name="$1"
    local result="$2"
    local details="$3"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    if [ "$result" = "PASS" ]; then
        echo -e "${GREEN}✅ PASS${NC}: $test_name - $details"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${RED}❌ FAIL${NC}: $test_name - $details"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
}

# Test 1: Service Health Checks
echo "=== Test 1: Service Health Endpoints ==="

# Content Service
if response=$(curl -s -w "%{http_code}" http://localhost:8001/healthz); then
    status_code="${response: -3}"
    if [ "$status_code" = "200" ]; then
        log_test "Content Service Health" "PASS" "HTTP 200"
    else
        log_test "Content Service Health" "FAIL" "HTTP $status_code"
    fi
else
    log_test "Content Service Health" "FAIL" "UNREACHABLE"
fi

# Batch Orchestrator Service  
if response=$(curl -s -w "%{http_code}" http://localhost:5001/healthz); then
    status_code="${response: -3}"
    if [ "$status_code" = "200" ]; then
        log_test "Batch Orchestrator Service Health" "PASS" "HTTP 200"
    else
        log_test "Batch Orchestrator Service Health" "FAIL" "HTTP $status_code"
    fi
else
    log_test "Batch Orchestrator Service Health" "FAIL" "UNREACHABLE"
fi

# Essay Lifecycle Service
if response=$(curl -s -w "%{http_code}" http://localhost:6001/healthz); then
    status_code="${response: -3}"
    if [ "$status_code" = "200" ]; then
        log_test "Essay Lifecycle Service Health" "PASS" "HTTP 200"
    else
        log_test "Essay Lifecycle Service Health" "FAIL" "HTTP $status_code"
    fi
else
    log_test "Essay Lifecycle Service Health" "FAIL" "UNREACHABLE"
fi

echo ""

# Test 2: Infrastructure Connectivity
echo "=== Test 2: Infrastructure Connectivity ==="

# Kafka connectivity test
if nc -z localhost 9093 2>/dev/null; then
    log_test "Kafka Connectivity" "PASS" "TCP connection successful"
else
    log_test "Kafka Connectivity" "FAIL" "Cannot connect to port 9093"
fi

# Docker container status
echo ""
echo "=== Container Status ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "Docker not available"

echo ""

# Test 3: End-to-End Workflow Testing
echo "=== Test 3: End-to-End Workflow ==="

# Content Upload Test
TEST_TEXT="This is a tset essay with misstakes and errrors for functional testing."
echo "Testing content upload..."

if upload_response=$(echo "$TEST_TEXT" | curl -s -X POST http://localhost:8001/v1/content --data-binary @-); then
    if storage_id=$(echo "$upload_response" | jq -r '.storage_id' 2>/dev/null) && [ "$storage_id" != "null" ]; then
        log_test "Content Upload" "PASS" "Storage ID: $storage_id"
        
        # Content Retrieval Test
        if retrieved_text=$(curl -s "http://localhost:8001/v1/content/$storage_id"); then
            if [ "$retrieved_text" = "$TEST_TEXT" ]; then
                log_test "Content Retrieval" "PASS" "Text matches original"
            else
                log_test "Content Retrieval" "FAIL" "Text mismatch"
            fi
        else
            log_test "Content Retrieval" "FAIL" "Failed to retrieve content"
        fi
        
    else
        log_test "Content Upload" "FAIL" "No storage_id returned"
    fi
else
    log_test "Content Upload" "FAIL" "Upload request failed"
    storage_id=""
fi

# Spell Check Workflow Test
echo "Testing spell check workflow..."
if batch_response=$(curl -s -X POST http://localhost:5001/v1/batches/trigger-spellcheck-test \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"$TEST_TEXT\"}"); then
    
    if batch_id=$(echo "$batch_response" | jq -r '.batch_id' 2>/dev/null) && [ "$batch_id" != "null" ]; then
        log_test "Batch Spell Check Trigger" "PASS" "Batch ID: $batch_id"
        
        # Extract other workflow details
        correlation_id=$(echo "$batch_response" | jq -r '.correlation_id' 2>/dev/null)
        essay_id=$(echo "$batch_response" | jq -r '.essay_id' 2>/dev/null)
        event_id=$(echo "$batch_response" | jq -r '.event_id' 2>/dev/null)
        
        echo "  📋 Workflow Details:"
        echo "     Correlation ID: $correlation_id"
        echo "     Essay ID: $essay_id"
        echo "     Event ID: $event_id"
        
    else
        log_test "Batch Spell Check Trigger" "FAIL" "No batch_id returned"
    fi
else
    log_test "Batch Spell Check Trigger" "FAIL" "Request failed"
fi

echo ""

# Test 4: Metrics Endpoints (Known issue investigation)
echo "=== Test 4: Metrics Endpoints (Investigation) ==="

# Test metrics endpoints that are expected to return 404 (known issue)
for service in "Content Service:8001" "Batch Service:5001" "Essay Lifecycle:6001"; do
    service_name=$(echo "$service" | cut -d: -f1)
    port=$(echo "$service" | cut -d: -f2)
    
    if response=$(curl -s -w "%{http_code}" "http://localhost:$port/metrics"); then
        status_code="${response: -3}"
        if [ "$status_code" = "200" ]; then
            log_test "$service_name Metrics" "PASS" "HTTP 200"
        elif [ "$status_code" = "404" ]; then
            log_test "$service_name Metrics" "FAIL" "HTTP 404 (Known issue - Blueprint route registration)"
        else
            log_test "$service_name Metrics" "FAIL" "HTTP $status_code"
        fi
    else
        log_test "$service_name Metrics" "FAIL" "UNREACHABLE"
    fi
done

echo ""

# Test Summary
echo "=== Functional Testing Summary ==="
echo -e "Total Tests: $TOTAL_TESTS"
echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
echo -e "${RED}Failed: $FAILED_TESTS${NC}"

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠️  Some tests failed. Check the results above.${NC}"
    exit 1
fi 