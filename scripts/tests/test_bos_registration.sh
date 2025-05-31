#!/usr/bin/env bash
set -euo pipefail

# HuleEdu BOS Registration Flow Test Script
# Tests batch registration endpoint and event emission validation

# Color codes for output  
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Configuration
readonly BOS_HOST="localhost"
readonly BOS_PORT="5001"
readonly BOS_BASE_URL="http://${BOS_HOST}:${BOS_PORT}"
readonly KAFKA_HOST="localhost"
readonly KAFKA_PORT="9093"
readonly KAFKA_BOOTSTRAP_SERVERS="${KAFKA_HOST}:${KAFKA_PORT}"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly TEST_OUTPUT_DIR="/tmp/huledu_bos_test"

# Test data
readonly TEST_ESSAY_IDS=("essay-test-001" "essay-test-002")
readonly TEST_COURSE_CODE="ENG101"
readonly TEST_CLASS_DESIGNATION="Fall2024-TestBatch"
readonly TEST_ESSAY_INSTRUCTIONS="Write a test essay for walking skeleton validation"

# Kafka command (assuming kafka-topics without .sh, adjust if needed)
KAFKA_CONSUMER_CMD="kafka-console-consumer"

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

setup_test_environment() {
    log_info "Setting up test environment..."
    mkdir -p "${TEST_OUTPUT_DIR}"
    
    # Clean up any previous test outputs
    rm -f "${TEST_OUTPUT_DIR}"/*
    
    log_success "Test environment ready"
}

test_bos_health() {
    log_info "Testing BOS service health..."
    
    local health_response
    if health_response=$(curl -s -w "HTTP_CODE:%{http_code}" "${BOS_BASE_URL}/healthz" 2>/dev/null); then
        local http_code="${health_response##*HTTP_CODE:}"
        local response_body="${health_response%HTTP_CODE:*}"
        
        if [[ "$http_code" == "200" ]]; then
            log_success "BOS service is healthy: $response_body"
            return 0
        else
            log_error "BOS health check failed with HTTP $http_code: $response_body"
            return 1
        fi
    else
        log_error "Cannot connect to BOS service at ${BOS_BASE_URL}"
        return 1
    fi
}

test_valid_batch_registration() {
    log_info "Testing valid batch registration..."
    
    local correlation_id="test-correlation-$(date +%s)"
    local request_payload=$(cat <<EOF
{
    "expected_essay_count": ${#TEST_ESSAY_IDS[@]},
    "essay_ids": ["${TEST_ESSAY_IDS[0]}", "${TEST_ESSAY_IDS[1]}"],
    "course_code": "${TEST_COURSE_CODE}",
    "class_designation": "${TEST_CLASS_DESIGNATION}",
    "essay_instructions": "${TEST_ESSAY_INSTRUCTIONS}"
}
EOF
)
    
    log_info "Sending registration request..."
    local response
    if response=$(curl -s -w "HTTP_CODE:%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$request_payload" \
        "${BOS_BASE_URL}/v1/batches/register" 2>/dev/null); then
        
        local http_code="${response##*HTTP_CODE:}"
        local response_body="${response%HTTP_CODE:*}"
        
        if [[ "$http_code" == "202" ]]; then
            log_success "Batch registration successful (HTTP 202)"
            
            # Parse response to extract batch_id and correlation_id
            local batch_id
            local returned_correlation_id
            
            # Using Python for JSON parsing (more reliable than bash)
            if command -v python3 > /dev/null 2>&1; then
                batch_id=$(echo "$response_body" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('batch_id', ''))")
                returned_correlation_id=$(echo "$response_body" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('correlation_id', ''))")
                
                if [[ -n "$batch_id" && -n "$returned_correlation_id" ]]; then
                    log_success "✓ Batch ID received: $batch_id"
                    log_success "✓ Correlation ID received: $returned_correlation_id"
                    
                    # Store for event validation
                    echo "$batch_id" > "${TEST_OUTPUT_DIR}/batch_id.txt"
                    echo "$returned_correlation_id" > "${TEST_OUTPUT_DIR}/correlation_id.txt"
                    return 0
                else
                    log_error "Missing batch_id or correlation_id in response: $response_body"
                    return 1
                fi
            else
                log_warning "Python3 not available for JSON parsing, storing raw response"
                echo "$response_body" > "${TEST_OUTPUT_DIR}/registration_response.json"
                return 0
            fi
        else
            log_error "Batch registration failed with HTTP $http_code: $response_body"
            return 1
        fi
    else
        log_error "Failed to send registration request to BOS"
        return 1
    fi
}

test_invalid_batch_registration() {
    log_info "Testing invalid batch registration (missing required fields)..."
    
    local invalid_payload='{"expected_essay_count": 0}'  # Missing required fields
    
    local response
    if response=$(curl -s -w "HTTP_CODE:%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$invalid_payload" \
        "${BOS_BASE_URL}/v1/batches/register" 2>/dev/null); then
        
        local http_code="${response##*HTTP_CODE:}"
        local response_body="${response%HTTP_CODE:*}"
        
        if [[ "$http_code" == "400" ]]; then
            log_success "✓ Invalid registration correctly rejected (HTTP 400)"
            log_info "Error response: $response_body"
            return 0
        else
            log_warning "Expected HTTP 400 for invalid request, got HTTP $http_code"
            return 1
        fi
    else
        log_error "Failed to send invalid registration request"
        return 1
    fi
}

validate_batch_essays_registered_event() {
    log_info "Validating BatchEssaysRegistered event emission..."
    
    if [[ ! -f "${TEST_OUTPUT_DIR}/batch_id.txt" ]]; then
        log_error "No batch_id found from previous test - cannot validate events"
        return 1
    fi
    
    local batch_id
    batch_id=$(cat "${TEST_OUTPUT_DIR}/batch_id.txt")
    local batch_topic="huleedu.batch.essays.registered.v1"
    
    log_info "Listening for BatchEssaysRegistered event for batch: $batch_id"
    
    # Start Kafka consumer in background to capture events
    timeout 15s "${KAFKA_CONSUMER_CMD}" \
        --bootstrap-server "${KAFKA_BOOTSTRAP_SERVERS}" \
        --topic "${batch_topic}" \
        --from-beginning \
        --property print.timestamp=true \
        --property print.key=true > "${TEST_OUTPUT_DIR}/kafka_events.log" 2>&1 &
    
    local consumer_pid=$!
    
    # Let consumer run and capture events
    sleep 12
    
    # Stop consumer
    kill $consumer_pid 2>/dev/null || true
    wait $consumer_pid 2>/dev/null || true
    
    # Analyze captured events
    if [[ -f "${TEST_OUTPUT_DIR}/kafka_events.log" ]] && [[ -s "${TEST_OUTPUT_DIR}/kafka_events.log" ]]; then
        local events_content
        events_content=$(cat "${TEST_OUTPUT_DIR}/kafka_events.log")
        
        if echo "$events_content" | grep -q "$batch_id"; then
            log_success "✓ BatchEssaysRegistered event found for batch $batch_id"
            
            # Check for correlation ID if available
            if [[ -f "${TEST_OUTPUT_DIR}/correlation_id.txt" ]]; then
                local correlation_id
                correlation_id=$(cat "${TEST_OUTPUT_DIR}/correlation_id.txt")
                if echo "$events_content" | grep -q "$correlation_id"; then
                    log_success "✓ Correlation ID propagated in Kafka event: $correlation_id"
                else
                    log_warning "Correlation ID not found in Kafka events (might use different format)"
                fi
            fi
            return 0
        else
            log_error "BatchEssaysRegistered event not found for batch $batch_id"
            log_info "Captured events:"
            cat "${TEST_OUTPUT_DIR}/kafka_events.log" | head -20
            return 1
        fi
    else
        log_error "No Kafka events captured or consumer failed"
        return 1
    fi
}

cleanup_test_environment() {
    log_info "Cleaning up test environment..."
    
    # Remove test files
    rm -rf "${TEST_OUTPUT_DIR}"
    
    log_success "Cleanup completed"
}

run_bos_registration_tests() {
    log_info "=== BOS Registration Flow Tests ==="
    log_info "Testing Batch Orchestrator Service registration and event emission"
    echo
    
    local tests_passed=0
    local tests_total=4
    
    # Test 1: Setup
    if setup_test_environment; then
        ((tests_passed++))
    fi
    
    # Test 2: Service Health
    if test_bos_health; then
        ((tests_passed++))
    fi
    
    # Test 3: Valid Registration
    if test_valid_batch_registration; then
        ((tests_passed++))
    fi
    
    # Test 4: Invalid Registration
    if test_invalid_batch_registration; then
        ((tests_passed++))
    fi
    
    # Test 5: Event Validation (if previous tests passed)
    if [[ $tests_passed -eq $tests_total ]]; then
        if validate_batch_essays_registered_event; then
            ((tests_passed++))
        fi
        ((tests_total++))
    fi
    
    echo
    log_info "=== BOS Registration Test Results ==="
    if [[ $tests_passed -eq $tests_total ]]; then
        log_success "All tests passed! ($tests_passed/$tests_total)"
        log_success "BOS registration flow is working correctly"
    else
        log_error "Some tests failed. ($tests_passed/$tests_total)"
        log_info "Check service logs and Kafka connectivity"
    fi
    
    cleanup_test_environment
    
    # Return success if all tests passed
    [[ $tests_passed -eq $tests_total ]]
}

# Main execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    run_bos_registration_tests
fi 