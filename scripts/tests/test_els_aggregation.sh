#!/usr/bin/env bash
set -euo pipefail

# HuleEdu ELS Aggregation Logic Test Script
# Tests Essay Lifecycle Service batch aggregation and BatchEssaysReady event emission

# Color codes for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Configuration
readonly ELS_API_HOST="localhost"
readonly ELS_API_PORT="6001"
readonly ELS_API_BASE_URL="http://${ELS_API_HOST}:${ELS_API_PORT}"
readonly FILE_SERVICE_HOST="localhost"
readonly FILE_SERVICE_PORT="7001"
readonly FILE_SERVICE_BASE_URL="http://${FILE_SERVICE_HOST}:${FILE_SERVICE_PORT}"
readonly BOS_HOST="localhost"
readonly BOS_PORT="5001"
readonly BOS_BASE_URL="http://${BOS_HOST}:${BOS_PORT}"
readonly KAFKA_HOST="localhost"
readonly KAFKA_PORT="9093"
readonly KAFKA_BOOTSTRAP_SERVERS="${KAFKA_HOST}:${KAFKA_PORT}"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly TEST_OUTPUT_DIR="/tmp/huledu_els_aggregation_test"

# Test data
readonly TEST_ESSAY_IDS=("els-test-essay-001" "els-test-essay-002" "els-test-essay-003")
readonly TEST_COURSE_CODE="ENG103"
readonly TEST_CLASS_DESIGNATION="Fall2024-ELSAggregationTest"
readonly TEST_ESSAY_INSTRUCTIONS="Test essays for ELS aggregation validation"

# Kafka command
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
    log_info "Setting up ELS aggregation test environment..."
    mkdir -p "${TEST_OUTPUT_DIR}/test_files"
    
    # Clean up any previous test outputs
    rm -f "${TEST_OUTPUT_DIR}"/*
    rm -f "${TEST_OUTPUT_DIR}/test_files"/*
    
    # Create test essay files for aggregation testing
    for i in {1..3}; do
        cat > "${TEST_OUTPUT_DIR}/test_files/essay${i}.txt" <<EOF
This is test essay number ${i} for ELS aggregation validation.
The essay is designed to test the count-based batch coordination pattern.
ELS should aggregate these essays and emit BatchEssaysReady when complete.
Student: Test Student ${i}
Course: ${TEST_COURSE_CODE}
Content ID: ${i}
EOF
    done
    
    log_success "Test environment and files ready"
}

test_els_api_health() {
    log_info "Testing ELS API health..."
    
    local health_response
    if health_response=$(curl -s -w "HTTP_CODE:%{http_code}" "${ELS_API_BASE_URL}/healthz" 2>/dev/null); then
        local http_code="${health_response##*HTTP_CODE:}"
        local response_body="${health_response%HTTP_CODE:*}"
        
        if [[ "$http_code" == "200" ]]; then
            log_success "ELS API is healthy: $response_body"
            return 0
        else
            log_error "ELS API health check failed with HTTP $http_code: $response_body"
            return 1
        fi
    else
        log_error "Cannot connect to ELS API at ${ELS_API_BASE_URL}"
        return 1
    fi
}

register_complete_batch() {
    log_info "Registering complete batch for aggregation testing..."
    
    local request_payload=$(cat <<EOF
{
    "expected_essay_count": ${#TEST_ESSAY_IDS[@]},
    "essay_ids": ["${TEST_ESSAY_IDS[0]}", "${TEST_ESSAY_IDS[1]}", "${TEST_ESSAY_IDS[2]}"],
    "course_code": "${TEST_COURSE_CODE}",
    "class_designation": "${TEST_CLASS_DESIGNATION}",
    "essay_instructions": "${TEST_ESSAY_INSTRUCTIONS}"
}
EOF
)
    
    local response
    if response=$(curl -s -w "HTTP_CODE:%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$request_payload" \
        "${BOS_BASE_URL}/v1/batches/register" 2>/dev/null); then
        
        local http_code="${response##*HTTP_CODE:}"
        local response_body="${response%HTTP_CODE:*}"
        
        if [[ "$http_code" == "202" ]]; then
            log_success "Complete batch registered successfully"
            
            # Extract batch_id using Python
            if command -v python3 > /dev/null 2>&1; then
                local batch_id
                batch_id=$(echo "$response_body" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('batch_id', ''))")
                
                if [[ -n "$batch_id" ]]; then
                    log_success "✓ Complete batch ID: $batch_id"
                    echo "$batch_id" > "${TEST_OUTPUT_DIR}/complete_batch_id.txt"
                    return 0
                else
                    log_error "No batch_id in registration response"
                    return 1
                fi
            else
                log_warning "Python3 not available for JSON parsing"
                return 1
            fi
        else
            log_error "Complete batch registration failed with HTTP $http_code: $response_body"
            return 1
        fi
    else
        log_error "Failed to register complete batch"
        return 1
    fi
}

register_partial_batch() {
    log_info "Registering partial batch for timeout testing..."
    
    # Register batch expecting 3 essays, but we'll only upload 2
    local partial_essay_ids=("els-partial-essay-001" "els-partial-essay-002" "els-partial-essay-003")
    local request_payload=$(cat <<EOF
{
    "expected_essay_count": 3,
    "essay_ids": ["${partial_essay_ids[0]}", "${partial_essay_ids[1]}", "${partial_essay_ids[2]}"],
    "course_code": "${TEST_COURSE_CODE}",
    "class_designation": "${TEST_CLASS_DESIGNATION}-Partial",
    "essay_instructions": "${TEST_ESSAY_INSTRUCTIONS} (partial upload test)"
}
EOF
)
    
    local response
    if response=$(curl -s -w "HTTP_CODE:%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$request_payload" \
        "${BOS_BASE_URL}/v1/batches/register" 2>/dev/null); then
        
        local http_code="${response##*HTTP_CODE:}"
        local response_body="${response%HTTP_CODE:*}"
        
        if [[ "$http_code" == "202" ]]; then
            log_success "Partial batch registered successfully"
            
            # Extract batch_id using Python
            if command -v python3 > /dev/null 2>&1; then
                local batch_id
                batch_id=$(echo "$response_body" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('batch_id', ''))")
                
                if [[ -n "$batch_id" ]]; then
                    log_success "✓ Partial batch ID: $batch_id"
                    echo "$batch_id" > "${TEST_OUTPUT_DIR}/partial_batch_id.txt"
                    return 0
                else
                    log_error "No batch_id in partial registration response"
                    return 1
                fi
            else
                log_warning "Python3 not available for JSON parsing"
                return 1
            fi
        else
            log_error "Partial batch registration failed with HTTP $http_code: $response_body"
            return 1
        fi
    else
        log_error "Failed to register partial batch"
        return 1
    fi
}

upload_complete_batch_files() {
    log_info "Uploading all files for complete batch aggregation test..."
    
    if [[ ! -f "${TEST_OUTPUT_DIR}/complete_batch_id.txt" ]]; then
        log_error "No complete batch ID available"
        return 1
    fi
    
    local batch_id
    batch_id=$(cat "${TEST_OUTPUT_DIR}/complete_batch_id.txt")
    
    log_info "Uploading 3 files to complete batch: $batch_id"
    
    local response
    if response=$(curl -s -w "HTTP_CODE:%{http_code}" \
        -X POST \
        -F "batch_id=${batch_id}" \
        -F "files=@${TEST_OUTPUT_DIR}/test_files/essay1.txt" \
        -F "files=@${TEST_OUTPUT_DIR}/test_files/essay2.txt" \
        -F "files=@${TEST_OUTPUT_DIR}/test_files/essay3.txt" \
        "${FILE_SERVICE_BASE_URL}/v1/files/batch" 2>/dev/null); then
        
        local http_code="${response##*HTTP_CODE:}"
        local response_body="${response%HTTP_CODE:*}"
        
        if [[ "$http_code" == "202" ]]; then
            log_success "Complete batch file upload successful (HTTP 202)"
            log_info "Response: $response_body"
            return 0
        else
            log_error "Complete batch file upload failed with HTTP $http_code: $response_body"
            return 1
        fi
    else
        log_error "Failed to upload files for complete batch"
        return 1
    fi
}

upload_partial_batch_files() {
    log_info "Uploading partial files for incomplete batch test..."
    
    if [[ ! -f "${TEST_OUTPUT_DIR}/partial_batch_id.txt" ]]; then
        log_error "No partial batch ID available"
        return 1
    fi
    
    local batch_id
    batch_id=$(cat "${TEST_OUTPUT_DIR}/partial_batch_id.txt")
    
    log_info "Uploading only 2 of 3 expected files to partial batch: $batch_id"
    
    local response
    if response=$(curl -s -w "HTTP_CODE:%{http_code}" \
        -X POST \
        -F "batch_id=${batch_id}" \
        -F "files=@${TEST_OUTPUT_DIR}/test_files/essay1.txt" \
        -F "files=@${TEST_OUTPUT_DIR}/test_files/essay2.txt" \
        "${FILE_SERVICE_BASE_URL}/v1/files/batch" 2>/dev/null); then
        
        local http_code="${response##*HTTP_CODE:}"
        local response_body="${response%HTTP_CODE:*}"
        
        if [[ "$http_code" == "202" ]]; then
            log_success "Partial batch file upload successful (HTTP 202)"
            log_info "Response: $response_body"
            return 0
        else
            log_error "Partial batch file upload failed with HTTP $http_code: $response_body"
            return 1
        fi
    else
        log_error "Failed to upload files for partial batch"
        return 1
    fi
}

validate_complete_batch_aggregation() {
    log_info "Validating complete batch aggregation and BatchEssaysReady emission..."
    
    if [[ ! -f "${TEST_OUTPUT_DIR}/complete_batch_id.txt" ]]; then
        log_error "No complete batch ID available for aggregation validation"
        return 1
    fi
    
    local batch_id
    batch_id=$(cat "${TEST_OUTPUT_DIR}/complete_batch_id.txt")
    local batch_ready_topic="huleedu.els.batch.essays.ready.v1"
    
    log_info "Listening for BatchEssaysReady event for complete batch: $batch_id"
    
    # Start Kafka consumer in background to capture BatchEssaysReady events
    timeout 30s "${KAFKA_CONSUMER_CMD}" \
        --bootstrap-server "${KAFKA_BOOTSTRAP_SERVERS}" \
        --topic "${batch_ready_topic}" \
        --from-beginning \
        --property print.timestamp=true \
        --property print.key=true > "${TEST_OUTPUT_DIR}/batch_ready_events.log" 2>&1 &
    
    local consumer_pid=$!
    
    # Let consumer run and capture events
    sleep 25
    
    # Stop consumer
    kill $consumer_pid 2>/dev/null || true
    wait $consumer_pid 2>/dev/null || true
    
    # Analyze captured events
    if [[ -f "${TEST_OUTPUT_DIR}/batch_ready_events.log" ]] && [[ -s "${TEST_OUTPUT_DIR}/batch_ready_events.log" ]]; then
        local events_content
        events_content=$(cat "${TEST_OUTPUT_DIR}/batch_ready_events.log")
        
        if echo "$events_content" | grep -q "$batch_id"; then
            log_success "✓ BatchEssaysReady event found for complete batch $batch_id"
            
            # Check for proper essay count in the event
            local ready_count
            ready_count=$(echo "$events_content" | grep -o '"total_count":[0-9]*' | head -1 | cut -d':' -f2 || echo "0")
            
            if [[ "$ready_count" == "3" ]]; then
                log_success "✓ Correct essay count (3) in BatchEssaysReady event"
            else
                log_warning "Expected total_count of 3, found: $ready_count"
            fi
            
            return 0
        else
            log_error "BatchEssaysReady event not found for complete batch $batch_id"
            log_info "Captured events:"
            cat "${TEST_OUTPUT_DIR}/batch_ready_events.log" | head -10
            return 1
        fi
    else
        log_error "No BatchEssaysReady events captured or consumer failed"
        return 1
    fi
}

validate_partial_batch_handling() {
    log_info "Validating partial batch handling (should NOT emit BatchEssaysReady)..."
    
    if [[ ! -f "${TEST_OUTPUT_DIR}/partial_batch_id.txt" ]]; then
        log_error "No partial batch ID available for validation"
        return 1
    fi
    
    local batch_id
    batch_id=$(cat "${TEST_OUTPUT_DIR}/partial_batch_id.txt")
    
    log_info "Checking that incomplete batch $batch_id does NOT trigger BatchEssaysReady"
    
    # Check if any BatchEssaysReady events exist for the partial batch
    if [[ -f "${TEST_OUTPUT_DIR}/batch_ready_events.log" ]]; then
        local events_content
        events_content=$(cat "${TEST_OUTPUT_DIR}/batch_ready_events.log")
        
        if echo "$events_content" | grep -q "$batch_id"; then
            log_error "Unexpected BatchEssaysReady event found for incomplete batch $batch_id"
            return 1
        else
            log_success "✓ No premature BatchEssaysReady event for incomplete batch"
            return 0
        fi
    else
        log_success "✓ No BatchEssaysReady events captured for incomplete batch"
        return 0
    fi
}

validate_bos_consumption() {
    log_info "Validating BOS consumption of BatchEssaysReady events..."
    
    # This test checks BOS logs for evidence of consuming BatchEssaysReady events
    # In a production environment, we'd check BOS service logs
    # For walking skeleton, we verify the event was properly formatted for BOS consumption
    
    if [[ -f "${TEST_OUTPUT_DIR}/batch_ready_events.log" ]] && [[ -s "${TEST_OUTPUT_DIR}/batch_ready_events.log" ]]; then
        local events_content
        events_content=$(cat "${TEST_OUTPUT_DIR}/batch_ready_events.log")
        
        # Check for proper event structure expected by BOS
        if echo "$events_content" | grep -q "batch_id\|ready_essay_ids"; then
            log_success "✓ BatchEssaysReady events contain expected BOS consumption fields"
            return 0
        else
            log_warning "BatchEssaysReady events may not contain expected BOS fields"
            return 1
        fi
    else
        log_warning "No BatchEssaysReady events available to validate BOS consumption"
        return 1
    fi
}

monitor_essay_content_ready_flow() {
    log_info "Monitoring EssayContentReady → BatchEssaysReady event flow..."
    
    local content_ready_topic="huleedu.file.essay.content.ready.v1"
    
    log_info "Briefly monitoring EssayContentReady events to validate aggregation flow"
    
    # Monitor EssayContentReady events for short time to confirm they are being processed
    timeout 10s "${KAFKA_CONSUMER_CMD}" \
        --bootstrap-server "${KAFKA_BOOTSTRAP_SERVERS}" \
        --topic "${content_ready_topic}" \
        --from-beginning \
        --max-messages 5 > "${TEST_OUTPUT_DIR}/content_ready_flow.log" 2>&1 &
    
    local consumer_pid=$!
    sleep 8
    kill $consumer_pid 2>/dev/null || true
    wait $consumer_pid 2>/dev/null || true
    
    if [[ -f "${TEST_OUTPUT_DIR}/content_ready_flow.log" ]] && [[ -s "${TEST_OUTPUT_DIR}/content_ready_flow.log" ]]; then
        local event_count
        event_count=$(wc -l < "${TEST_OUTPUT_DIR}/content_ready_flow.log" 2>/dev/null || echo "0")
        
        if [[ "$event_count" -gt 0 ]]; then
            log_success "✓ EssayContentReady events detected ($event_count events)"
            log_info "ELS is receiving and processing essay readiness signals"
            return 0
        else
            log_warning "No EssayContentReady events detected"
            return 1
        fi
    else
        log_warning "Could not monitor EssayContentReady events"
        return 1
    fi
}

cleanup_test_environment() {
    log_info "Cleaning up ELS aggregation test environment..."
    
    # Remove test files and outputs
    rm -rf "${TEST_OUTPUT_DIR}"
    
    log_success "Cleanup completed"
}

run_els_aggregation_tests() {
    log_info "=== ELS Aggregation Logic Tests ==="
    log_info "Testing Essay Lifecycle Service batch aggregation and completion detection"
    echo
    
    local tests_passed=0
    local tests_total=8
    
    # Test 1: Setup
    if setup_test_environment; then
        ((tests_passed++))
    fi
    
    # Test 2: ELS API Health
    if test_els_api_health; then
        ((tests_passed++))
    fi
    
    # Test 3: Register Complete Batch
    if register_complete_batch; then
        ((tests_passed++))
    fi
    
    # Test 4: Register Partial Batch
    if register_partial_batch; then
        ((tests_passed++))
    fi
    
    # Test 5: Upload Complete Batch Files
    if upload_complete_batch_files; then
        ((tests_passed++))
    fi
    
    # Test 6: Upload Partial Batch Files
    if upload_partial_batch_files; then
        ((tests_passed++))
    fi
    
    # Test 7: Monitor Content Ready Flow
    if monitor_essay_content_ready_flow; then
        ((tests_passed++))
    fi
    
    # Test 8: Validate Complete Batch Aggregation
    if validate_complete_batch_aggregation; then
        ((tests_passed++))
    fi
    
    # Test 9: Validate Partial Batch Handling (if aggregation test passed)
    if [[ $tests_passed -eq $tests_total ]]; then
        if validate_partial_batch_handling; then
            ((tests_passed++))
        fi
        ((tests_total++))
    fi
    
    # Test 10: Validate BOS Consumption (if events captured)
    if [[ $tests_passed -eq $tests_total ]]; then
        if validate_bos_consumption; then
            ((tests_passed++))
        fi
        ((tests_total++))
    fi
    
    echo
    log_info "=== ELS Aggregation Test Results ==="
    if [[ $tests_passed -eq $tests_total ]]; then
        log_success "All tests passed! ($tests_passed/$tests_total)"
        log_success "ELS aggregation logic is working correctly"
    else
        log_error "Some tests failed. ($tests_passed/$tests_total)"
        log_info "Check ELS worker logs, Kafka event flow, and service coordination"
    fi
    
    cleanup_test_environment
    
    # Return success if all tests passed
    [[ $tests_passed -eq $tests_total ]]
}

# Main execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    run_els_aggregation_tests
fi 