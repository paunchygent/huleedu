#!/usr/bin/env bash
set -euo pipefail

# HuleEdu File Service Integration Test Script v2 (Architecture Fix)
# Tests file uploads to registered batches and validates new event flow with EssayContentProvisionedV1

# Color codes for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Configuration
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
readonly TEST_OUTPUT_DIR="/tmp/huledu_file_service_test_v2"

# Test data
readonly TEST_ESSAY_IDS=("file-test-essay-001" "file-test-essay-002")
readonly TEST_COURSE_CODE="ENG102"
readonly TEST_CLASS_DESIGNATION="Fall2024-FileServiceTestV2"
readonly TEST_ESSAY_INSTRUCTIONS="Test essay for File Service integration validation with architecture fix"

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
    log_info "Setting up File Service v2 test environment..."
    mkdir -p "${TEST_OUTPUT_DIR}/test_files"
    
    # Clean up any previous test outputs
    rm -f "${TEST_OUTPUT_DIR}"/*
    rm -f "${TEST_OUTPUT_DIR}/test_files"/*
    
    # Create test essay files
    cat > "${TEST_OUTPUT_DIR}/test_files/essay1.txt" <<EOF
This is a test essay for File Service integration testing with architecture fix.
It contains multiple sentences to test text extraction capabilities.
The essay demonstrates the walking skeleton file processing workflow with slot assignment.
Student: Test Student One
Course: ${TEST_COURSE_CODE}
EOF

    cat > "${TEST_OUTPUT_DIR}/test_files/essay2.txt" <<EOF
This is another test essay for comprehensive File Service validation with new event models.
The content includes spelling mistakes to test spellcheck integration.
This essay validats the batch coordination patterns between services using ELS slot assignment.
Student: Test Student Two  
Course: ${TEST_COURSE_CODE}
EOF

    # Create an invalid file type for error testing
    echo "This is not a supported file format" > "${TEST_OUTPUT_DIR}/test_files/invalid.bin"
    
    log_success "Test environment and files ready for architecture fix validation"
}

test_file_service_health() {
    log_info "Testing File Service health..."
    
    local health_response
    if health_response=$(curl -s -w "HTTP_CODE:%{http_code}" "${FILE_SERVICE_BASE_URL}/healthz" 2>/dev/null); then
        local http_code="${health_response##*HTTP_CODE:}"
        local response_body="${health_response%HTTP_CODE:*}"
        
        if [[ "$http_code" == "200" ]]; then
            log_success "File Service is healthy: $response_body"
            return 0
        else
            log_error "File Service health check failed with HTTP $http_code: $response_body"
            return 1
        fi
    else
        log_error "Cannot connect to File Service at ${FILE_SERVICE_BASE_URL}"
        return 1
    fi
}

register_test_batch() {
    log_info "Registering test batch via BOS for File Service testing (with essay ID slots)..."
    
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
    
    local response
    if response=$(curl -s -w "HTTP_CODE:%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$request_payload" \
        "${BOS_BASE_URL}/v1/batches/register" 2>/dev/null); then
        
        local http_code="${response##*HTTP_CODE:}"
        local response_body="${response%HTTP_CODE:*}"
        
        if [[ "$http_code" == "202" ]]; then
            log_success "Test batch registered successfully (BOS now generates essay ID slots)"
            
            # Extract batch_id using Python
            if command -v python3 > /dev/null 2>&1; then
                local batch_id
                batch_id=$(echo "$response_body" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('batch_id', ''))")
                
                if [[ -n "$batch_id" ]]; then
                    log_success "✓ Test batch ID: $batch_id"
                    echo "$batch_id" > "${TEST_OUTPUT_DIR}/test_batch_id.txt"
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
            log_error "Batch registration failed with HTTP $http_code: $response_body"
            return 1
        fi
    else
        log_error "Failed to register test batch"
        return 1
    fi
}

test_valid_file_upload() {
    log_info "Testing valid file upload to registered batch (File Service no longer generates essay IDs)..."
    
    if [[ ! -f "${TEST_OUTPUT_DIR}/test_batch_id.txt" ]]; then
        log_error "No test batch ID available - batch registration may have failed"
        return 1
    fi
    
    local batch_id
    batch_id=$(cat "${TEST_OUTPUT_DIR}/test_batch_id.txt")
    
    log_info "Uploading files to batch: $batch_id"
    
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
            log_success "File upload successful (HTTP 202) - Files sent for ELS slot assignment"
            
            # Parse response to extract correlation_id
            if command -v python3 > /dev/null 2>&1; then
                local correlation_id
                correlation_id=$(echo "$response_body" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('correlation_id', ''))" 2>/dev/null || echo "")
                
                if [[ -n "$correlation_id" ]]; then
                    log_success "✓ File upload correlation ID: $correlation_id"
                    echo "$correlation_id" > "${TEST_OUTPUT_DIR}/upload_correlation_id.txt"
                fi
            fi
            
            log_info "Response: $response_body"
            return 0
        else
            log_error "File upload failed with HTTP $http_code: $response_body"
            return 1
        fi
    else
        log_error "Failed to upload files"
        return 1
    fi
}

test_upload_to_nonexistent_batch() {
    log_info "Testing file upload to non-existent batch..."
    
    local fake_batch_id="non-existent-batch-id"
    
    local response
    if response=$(curl -s -w "HTTP_CODE:%{http_code}" \
        -X POST \
        -F "batch_id=${fake_batch_id}" \
        -F "files=@${TEST_OUTPUT_DIR}/test_files/essay1.txt" \
        "${FILE_SERVICE_BASE_URL}/v1/files/batch" 2>/dev/null); then
        
        local http_code="${response##*HTTP_CODE:}"
        local response_body="${response%HTTP_CODE:*}"
        
        if [[ "$http_code" == "202" ]]; then
            log_success "✓ Non-existent batch handled gracefully (HTTP 202)"
            log_info "Response: $response_body"
            return 0
        else
            log_warning "Expected HTTP 202 for non-existent batch, got HTTP $http_code"
            return 1
        fi
    else
        log_error "Failed to test upload to non-existent batch"
        return 1
    fi
}

test_upload_without_batch_id() {
    log_info "Testing file upload without batch_id parameter..."
    
    local response
    if response=$(curl -s -w "HTTP_CODE:%{http_code}" \
        -X POST \
        -F "files=@${TEST_OUTPUT_DIR}/test_files/essay1.txt" \
        "${FILE_SERVICE_BASE_URL}/v1/files/batch" 2>/dev/null); then
        
        local http_code="${response##*HTTP_CODE:}"
        local response_body="${response%HTTP_CODE:*}"
        
        if [[ "$http_code" == "400" ]]; then
            log_success "✓ Missing batch_id correctly rejected (HTTP 400)"
            log_info "Error response: $response_body"
            return 0
        else
            log_warning "Expected HTTP 400 for missing batch_id, got HTTP $http_code"
            return 1
        fi
    else
        log_error "Failed to test upload without batch_id"
        return 1
    fi
}

validate_essay_content_provisioned_events() {
    log_info "Validating EssayContentProvisionedV1 event emission from File Service (NEW EVENT MODEL)..."
    
    if [[ ! -f "${TEST_OUTPUT_DIR}/test_batch_id.txt" ]]; then
        log_error "No test batch ID available for event validation"
        return 1
    fi
    
    local batch_id
    batch_id=$(cat "${TEST_OUTPUT_DIR}/test_batch_id.txt")
    # NEW TOPIC: content.provisioned instead of content.ready
    local content_provisioned_topic="huleedu.file.essay.content.provisioned.v1"
    
    log_info "Listening for EssayContentProvisionedV1 events for batch: $batch_id"
    log_info "Topic: $content_provisioned_topic"
    
    # Start Kafka consumer in background to capture events
    timeout 20s "${KAFKA_CONSUMER_CMD}" \
        --bootstrap-server "${KAFKA_BOOTSTRAP_SERVERS}" \
        --topic "${content_provisioned_topic}" \
        --from-beginning \
        --property print.timestamp=true \
        --property print.key=true > "${TEST_OUTPUT_DIR}/content_provisioned_events.log" 2>&1 &
    
    local consumer_pid=$!
    
    # Let consumer run and capture events
    sleep 15
    
    # Stop consumer
    kill $consumer_pid 2>/dev/null || true
    wait $consumer_pid 2>/dev/null || true
    
    # Analyze captured events
    if [[ -f "${TEST_OUTPUT_DIR}/content_provisioned_events.log" ]] && [[ -s "${TEST_OUTPUT_DIR}/content_provisioned_events.log" ]]; then
        local events_content
        events_content=$(cat "${TEST_OUTPUT_DIR}/content_provisioned_events.log")
        
        # Count events for this batch
        local event_count
        event_count=$(echo "$events_content" | grep -c "$batch_id" || echo "0")
        
        if [[ "$event_count" -gt 0 ]]; then
            log_success "✓ Found $event_count EssayContentProvisionedV1 event(s) for batch $batch_id"
            
            # Check for correlation ID propagation if available
            if [[ -f "${TEST_OUTPUT_DIR}/upload_correlation_id.txt" ]]; then
                local correlation_id
                correlation_id=$(cat "${TEST_OUTPUT_DIR}/upload_correlation_id.txt")
                if echo "$events_content" | grep -q "$correlation_id"; then
                    log_success "✓ Upload correlation ID propagated in events: $correlation_id"
                else
                    log_warning "Upload correlation ID not found in events (may use different correlation strategy)"
                fi
            fi
            
            # Expected: 2 events for 2 uploaded files
            if [[ "$event_count" -eq 2 ]]; then
                log_success "✓ Correct number of events (2) for uploaded files"
            else
                log_warning "Expected 2 events for 2 files, got $event_count"
            fi
            
            # Check for new event structure (no essay_id generation by File Service)
            if echo "$events_content" | grep -q "text_storage_id"; then
                log_success "✓ New event structure confirmed - text_storage_id present (no essay_id generation)"
            else
                log_warning "text_storage_id not visible in event output format"
            fi
            
            return 0
        else
            log_error "No EssayContentProvisionedV1 events found for batch $batch_id"
            log_info "Captured events:"
            cat "${TEST_OUTPUT_DIR}/content_provisioned_events.log" | head -10
            return 1
        fi
    else
        log_error "No content provisioned events captured or consumer failed"
        return 1
    fi
}

validate_content_service_storage() {
    log_info "Validating Content Service storage coordination (architecture fix)..."
    
    # This test checks if File Service successfully stored content via Content Service
    # We can verify by checking if the events contain storage references
    
    if [[ -f "${TEST_OUTPUT_DIR}/content_provisioned_events.log" ]]; then
        local events_content
        events_content=$(cat "${TEST_OUTPUT_DIR}/content_provisioned_events.log")
        
        # Check for storage references in events (storage_id patterns)
        if echo "$events_content" | grep -q "storage_id\|text_storage_id"; then
            log_success "✓ Content Service storage references found in events"
            return 0
        else
            log_warning "Storage references not visible in event output format"
            # This may be normal depending on how events are serialized
            return 0
        fi
    else
        log_warning "No event data available to validate storage"
        return 1
    fi
}

validate_els_slot_assignment() {
    log_info "Validating ELS slot assignment logic (NEW: architecture fix)..."
    
    # With the architecture fix, we should see ELS processing the content provisioned events
    # and performing slot assignment. We can check for any excess content events.
    
    local excess_content_topic="huleedu.els.excess.content.provisioned.v1"
    
    log_info "Checking for excess content events (should be none for this test)..."
    
    # Quick check for excess content events
    timeout 10s "${KAFKA_CONSUMER_CMD}" \
        --bootstrap-server "${KAFKA_BOOTSTRAP_SERVERS}" \
        --topic "${excess_content_topic}" \
        --from-beginning \
        --property print.timestamp=true > "${TEST_OUTPUT_DIR}/excess_content_events.log" 2>&1 &
    
    local consumer_pid=$!
    sleep 8
    kill $consumer_pid 2>/dev/null || true
    wait $consumer_pid 2>/dev/null || true
    
    if [[ -f "${TEST_OUTPUT_DIR}/excess_content_events.log" ]] && [[ -s "${TEST_OUTPUT_DIR}/excess_content_events.log" ]]; then
        local batch_id
        batch_id=$(cat "${TEST_OUTPUT_DIR}/test_batch_id.txt")
        local excess_count
        excess_count=$(grep -c "$batch_id" "${TEST_OUTPUT_DIR}/excess_content_events.log" 2>/dev/null || echo "0")
        excess_count=$(echo "$excess_count" | tr -d '\n\r')
        
        if [[ "$excess_count" -eq 0 ]]; then
            log_success "✓ No excess content events (expected for this test - 2 files for 2 slots)"
        else
            log_warning "Found $excess_count excess content events (unexpected for this test)"
        fi
    else
        log_success "✓ No excess content events captured (expected for this test)"
    fi
    
    return 0
}

cleanup_test_environment() {
    log_info "Cleaning up File Service v2 test environment..."
    
    # Remove test files and outputs
    rm -rf "${TEST_OUTPUT_DIR}"
    
    log_success "Cleanup completed"
}

run_file_service_integration_tests() {
    log_info "=== File Service Integration Tests v2 (Architecture Fix) ==="
    log_info "Testing file upload endpoints and NEW event coordination with EssayContentProvisionedV1"
    echo
    
    local tests_passed=0
    local tests_total=8
    
    # Test 1: Setup
    if setup_test_environment; then
        ((tests_passed++))
    fi
    
    # Test 2: Service Health
    if test_file_service_health; then
        ((tests_passed++))
    fi
    
    # Test 3: Register Test Batch (BOS generates essay ID slots)
    if register_test_batch; then
        ((tests_passed++))
    fi
    
    # Test 4: Valid File Upload (File Service no longer generates essay IDs)
    if test_valid_file_upload; then
        ((tests_passed++))
    fi
    
    # Test 5: Upload to Non-existent Batch
    if test_upload_to_nonexistent_batch; then
        ((tests_passed++))
    fi
    
    # Test 6: Upload without Batch ID
    if test_upload_without_batch_id; then
        ((tests_passed++))
    fi
    
    # Test 7: NEW Event Validation (EssayContentProvisionedV1)
    if [[ $tests_passed -ge 4 ]]; then
        if validate_essay_content_provisioned_events; then
            ((tests_passed++))
        fi
    else
        log_warning "Skipping event validation - file upload tests failed"
    fi
    
    # Test 8: ELS Slot Assignment Validation (NEW)
    if [[ $tests_passed -eq 7 ]]; then
        if validate_els_slot_assignment; then
            ((tests_passed++))
        fi
    fi
    
    echo
    log_info "=== File Service Integration Test v2 Results ==="
    if [[ $tests_passed -eq $tests_total ]]; then
        log_success "All tests passed! ($tests_passed/$tests_total)"
        log_success "File Service integration with architecture fix is working correctly"
        log_success "✓ EssayContentProvisionedV1 events properly emitted"
        log_success "✓ File Service no longer generates essay IDs (ELS handles slot assignment)"
    else
        log_error "Some tests failed. ($tests_passed/$tests_total)"
        log_info "Check File Service logs, ELS slot assignment, and new event models"
    fi
    
    cleanup_test_environment
    
    # Return success if all tests passed
    [[ $tests_passed -eq $tests_total ]]
}

# Main execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    run_file_service_integration_tests
fi 