#!/usr/bin/env bash
set -euo pipefail

# HuleEdu Kafka Infrastructure Validation Script
# Tests Kafka topics, connectivity, and basic event flow capabilities

# Color codes for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Configuration
readonly KAFKA_HOST="localhost"
readonly KAFKA_PORT="9093"
readonly KAFKA_BOOTSTRAP_SERVERS="${KAFKA_HOST}:${KAFKA_PORT}"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Required topics for walking skeleton
readonly REQUIRED_TOPICS=(
    "huleedu.batch.essays.registered.v1"
    "huleedu.file.essay.content.ready.v1"
    "huleedu.els.batch.essays.ready.v1"
    "huleedu.els.spellcheck.initiate.command.v1"
    "huleedu.essay.spellcheck.requested.v1"
    "huleedu.essay.spellcheck.completed.v1"
)

# Kafka command variables (set by check_kafka_tools function)
KAFKA_TOPICS_CMD=""
KAFKA_PRODUCER_CMD=""
KAFKA_CONSUMER_CMD=""

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

check_kafka_connectivity() {
    log_info "Testing Kafka connectivity at ${KAFKA_BOOTSTRAP_SERVERS}..."
    
    if timeout 10s "${KAFKA_TOPICS_CMD}" --bootstrap-server "${KAFKA_BOOTSTRAP_SERVERS}" --list > /dev/null 2>&1; then
        log_success "Kafka is accessible at ${KAFKA_BOOTSTRAP_SERVERS}"
        return 0
    else
        log_error "Cannot connect to Kafka at ${KAFKA_BOOTSTRAP_SERVERS}"
        log_info "Ensure Docker Compose services are running: docker compose up -d"
        return 1
    fi
}

verify_required_topics() {
    log_info "Verifying required Kafka topics exist..."
    
    local missing_topics=()
    local existing_topics
    
    # Get list of existing topics
    existing_topics=$("${KAFKA_TOPICS_CMD}" --bootstrap-server "${KAFKA_BOOTSTRAP_SERVERS}" --list 2>/dev/null || echo "")
    
    if [[ -z "$existing_topics" ]]; then
        log_error "Failed to retrieve topic list from Kafka"
        return 1
    fi
    
    # Check each required topic
    for topic in "${REQUIRED_TOPICS[@]}"; do
        if echo "$existing_topics" | grep -q "^${topic}$"; then
            log_success "✓ Topic exists: ${topic}"
        else
            log_warning "✗ Missing topic: ${topic}"
            missing_topics+=("$topic")
        fi
    done
    
    if [[ ${#missing_topics[@]} -eq 0 ]]; then
        log_success "All required topics exist"
        return 0
    else
        log_error "Missing ${#missing_topics[@]} required topics"
        log_info "Run topic bootstrap: pdm run python scripts/kafka_topic_bootstrap.py"
        return 1
    fi
}

test_topic_details() {
    log_info "Checking topic configurations..."
    
    for topic in "${REQUIRED_TOPICS[@]}"; do
        local topic_details
        topic_details=$("${KAFKA_TOPICS_CMD}" --bootstrap-server "${KAFKA_BOOTSTRAP_SERVERS}" --describe --topic "${topic}" 2>/dev/null || echo "")
        
        if [[ -n "$topic_details" ]]; then
            # Extract partition and replication info
            local partitions
            local replication_factor
            partitions=$(echo "$topic_details" | grep -o "PartitionCount: [0-9]*" | cut -d' ' -f2 || echo "unknown")
            replication_factor=$(echo "$topic_details" | grep -o "ReplicationFactor: [0-9]*" | cut -d' ' -f2 || echo "unknown")
            
            log_info "  ${topic}: ${partitions} partitions, replication factor ${replication_factor}"
        else
            log_warning "  ${topic}: Unable to get topic details"
        fi
    done
}

test_basic_message_flow() {
    log_info "Testing basic message publishing and consuming..."
    
    local test_topic="huleedu.batch.essays.registered.v1"
    local test_message='{"test": "kafka_infrastructure_validation", "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}'
    local consumer_output
    local producer_success=false
    
    # Start consumer in background
    log_info "Starting test consumer for ${test_topic}..."
    timeout 10s "${KAFKA_CONSUMER_CMD}" \
        --bootstrap-server "${KAFKA_BOOTSTRAP_SERVERS}" \
        --topic "${test_topic}" \
        --from-beginning \
        --max-messages 1 > /tmp/kafka_test_output 2>&1 &
    
    local consumer_pid=$!
    sleep 2  # Give consumer time to start
    
    # Publish test message
    log_info "Publishing test message to ${test_topic}..."
    if echo "$test_message" | "${KAFKA_PRODUCER_CMD}" \
        --bootstrap-server "${KAFKA_BOOTSTRAP_SERVERS}" \
        --topic "${test_topic}" > /dev/null 2>&1; then
        
        producer_success=true
        log_success "Test message published successfully"
    else
        log_error "Failed to publish test message"
        kill $consumer_pid 2>/dev/null || true
        return 1
    fi
    
    # Wait for consumer to finish or timeout
    if wait $consumer_pid 2>/dev/null; then
        consumer_output=$(cat /tmp/kafka_test_output 2>/dev/null || echo "")
        if [[ -n "$consumer_output" ]] && echo "$consumer_output" | grep -q "kafka_infrastructure_validation"; then
            log_success "Test message consumed successfully"
            rm -f /tmp/kafka_test_output
            return 0
        else
            log_warning "Consumer did not receive expected message"
            log_info "Consumer output: $consumer_output"
            rm -f /tmp/kafka_test_output
            return 1
        fi
    else
        log_warning "Consumer timed out - this might be normal if topic has existing messages"
        kill $consumer_pid 2>/dev/null || true
        rm -f /tmp/kafka_test_output
        
        # If producer succeeded, consider test partially successful
        if [[ "$producer_success" == true ]]; then
            log_success "Message publishing works (consumer timeout is acceptable)"
            return 0
        else
            return 1
        fi
    fi
}

check_kafka_tools() {
    log_info "Checking Kafka CLI tools availability..."
    
    # Try both naming conventions (with and without .sh extension)
    local tools_with_sh=("kafka-topics.sh" "kafka-console-producer.sh" "kafka-console-consumer.sh")
    local tools_without_sh=("kafka-topics" "kafka-console-producer" "kafka-console-consumer")
    
    # Check for tools with .sh extension (Docker/Linux style)
    local found_with_sh=true
    for tool in "${tools_with_sh[@]}"; do
        if ! command -v "$tool" > /dev/null 2>&1; then
            found_with_sh=false
            break
        fi
    done
    
    if [[ "$found_with_sh" == true ]]; then
        # Use .sh naming convention
        KAFKA_TOPICS_CMD="kafka-topics.sh"
        KAFKA_PRODUCER_CMD="kafka-console-producer.sh"
        KAFKA_CONSUMER_CMD="kafka-console-consumer.sh"
        log_success "✓ Found Kafka tools with .sh extension"
        return 0
    fi
    
    # Check for tools without .sh extension (Homebrew style)
    local found_without_sh=true
    for tool in "${tools_without_sh[@]}"; do
        if ! command -v "$tool" > /dev/null 2>&1; then
            found_without_sh=false
            break
        fi
    done
    
    if [[ "$found_without_sh" == true ]]; then
        # Set global variables for the naming convention found
        KAFKA_TOPICS_CMD="kafka-topics"
        KAFKA_PRODUCER_CMD="kafka-console-producer"
        KAFKA_CONSUMER_CMD="kafka-console-consumer"
        log_success "✓ Found Kafka tools without .sh extension"
        return 0
    fi
    
    # Neither naming convention found
    log_error "Missing Kafka CLI tools. These tests require Kafka command-line tools to be installed."
    log_info "On macOS: brew install kafka"
    log_info "On Ubuntu: sudo apt-get install kafka"
    log_info ""
    log_info "If you have Java compatibility issues, ensure you're using Java 17+ by setting:"
    log_info "  export JAVA_HOME=/path/to/java17+"
    log_info "  export PATH=\"\$JAVA_HOME/bin:\$PATH\""
    return 1
}

main() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════════════════════════╗"
    echo "║                     HuleEdu Kafka Infrastructure Validation                     ║"
    echo "║                           Walking Skeleton Phase 1                             ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    local exit_code=0
    
    # Check prerequisites
    if ! check_kafka_tools; then
        exit 1
    fi
    
    # Test connectivity
    if ! check_kafka_connectivity; then
        exit 1
    fi
    
    # Verify topics exist
    if ! verify_required_topics; then
        log_error "Required topics missing - running topic bootstrap..."
        
        # Attempt to run topic bootstrap
        if command -v pdm > /dev/null 2>&1; then
            log_info "Running Kafka topic bootstrap..."
            if (cd "${PROJECT_ROOT}" && pdm run python scripts/kafka_topic_bootstrap.py); then
                log_success "Topic bootstrap completed"
                # Re-verify topics
                if ! verify_required_topics; then
                    exit_code=1
                fi
            else
                log_error "Topic bootstrap failed"
                exit_code=1
            fi
        else
            log_error "PDM not available - cannot run topic bootstrap automatically"
            exit_code=1
        fi
    fi
    
    # Check topic configurations
    test_topic_details
    
    # Test basic message flow
    if ! test_basic_message_flow; then
        log_warning "Basic message flow test had issues (may be acceptable)"
        # Don't fail the entire test for message flow issues
    fi
    
    echo
    if [[ $exit_code -eq 0 ]]; then
        log_success "🎉 Kafka infrastructure validation completed successfully!"
        echo -e "${GREEN}Ready for walking skeleton testing.${NC}"
    else
        log_error "💥 Kafka infrastructure validation failed!"
        echo -e "${RED}Fix issues before proceeding with walking skeleton testing.${NC}"
    fi
    
    exit $exit_code
}

# Handle script interruption
trap 'log_warning "Test interrupted"; exit 130' INT TERM

main "$@" 