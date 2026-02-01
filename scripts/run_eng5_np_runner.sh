#!/usr/bin/env bash
#
# ENG5 NP Runner Orchestration Script
#
# This script ensures infrastructure services are running before executing
# the eng5_np_runner container. It handles cold-start scenarios where Kafka
# and other dependencies may not be available yet.
#
# Usage:
#   bash scripts/run_eng5_np_runner.sh [runner arguments...]
#   pdm run eng5-runner [runner arguments...]
#
# Examples:
#   bash scripts/run_eng5_np_runner.sh --mode plan --batch-id test-run
#   pdm run eng5-runner --mode execute --batch-id production-batch
#   pdm run eng5-runner --no-kafka --mode plan --batch-id dry-run
#
# Exit codes:
#   0 - Runner completed successfully
#   1 - Infrastructure or runner failed
#

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Script location
SCRIPT_DIR=$(cd -- "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

# Helper functions
echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo_runner() {
    echo -e "${CYAN}[ENG5-RUNNER]${NC} $1"
}

# Check if a service is running
is_service_running() {
    local service_name="$1"
    docker compose ps "$service_name" 2>/dev/null | grep -q "Up"
}

# Check if a service is healthy
is_service_healthy() {
    local service_name="$1"
    local status
    status=$(docker compose ps --format json "$service_name" 2>/dev/null | grep -o '"Health":"[^"]*"' | cut -d'"' -f4 || echo "")
    [ "$status" = "healthy" ]
}

# Wait for a service to be healthy
wait_for_healthy() {
    local service_name="$1"
    local timeout=${2:-60}
    local elapsed=0

    echo_info "Waiting for $service_name to be healthy (timeout: ${timeout}s)..."

    while [ $elapsed -lt $timeout ]; do
        if is_service_healthy "$service_name"; then
            echo_info "$service_name is healthy"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done

    echo_error "$service_name did not become healthy within ${timeout}s"
    return 1
}

# Ensure infrastructure services are running
ensure_infrastructure() {
    echo_runner "Checking infrastructure services..."

    local needs_start=0

    # Check kafka, redis
    for service in kafka redis; do
        if is_service_running "$service"; then
            echo_info "$service is already running"
        else
            echo_warn "$service is not running"
            needs_start=1
        fi
    done

    if [ $needs_start -eq 1 ]; then
        echo_runner "Starting infrastructure services..."
        docker compose -f docker-compose.yml up -d kafka redis

        # Wait for kafka to be healthy
        if ! wait_for_healthy kafka 60; then
            echo_error "Kafka failed to become healthy"
            return 1
        fi
    else
        echo_info "All infrastructure services are running"

        # Still verify kafka is healthy even if already running
        if ! is_service_healthy kafka; then
            echo_warn "Kafka is running but not healthy, waiting..."
            if ! wait_for_healthy kafka 60; then
                echo_error "Kafka is not healthy"
                return 1
            fi
        fi
    fi
}

# Ensure kafka_topic_setup has completed
ensure_topic_setup() {
    echo_runner "Checking Kafka topic setup..."

    # Check if kafka_topic_setup container exists and its exit status
    local container_name="huleedu_kafka_topic_setup"

    if docker ps -a --format '{{.Names}}' | grep -q "^${container_name}$"; then
        local exit_code
        exit_code=$(docker inspect "$container_name" --format='{{.State.ExitCode}}' 2>/dev/null || echo "")

        if [ "$exit_code" = "0" ]; then
            echo_info "Kafka topics already set up"
            return 0
        else
            echo_warn "Previous kafka_topic_setup failed (exit code: $exit_code), retrying..."
            docker rm -f "$container_name" 2>/dev/null || true
        fi
    fi

    # Run kafka_topic_setup
    echo_info "Running Kafka topic setup..."
    if ! docker compose -f docker-compose.yml up kafka_topic_setup 2>&1; then
        echo_error "Kafka topic setup failed"
        echo_info "Check logs with: docker logs $container_name"
        return 1
    fi

    # Verify it completed successfully
    local exit_code
    exit_code=$(docker inspect "$container_name" --format='{{.State.ExitCode}}' 2>/dev/null || echo "1")

    if [ "$exit_code" = "0" ]; then
        echo_info "Kafka topics successfully configured"
        return 0
    else
        echo_error "Kafka topic setup exited with code: $exit_code"
        echo_info "Check logs with: docker logs $container_name"
        return 1
    fi
}

# Ensure dependent services are running
ensure_dependent_services() {
    echo_runner "Checking dependent services..."

    local services_needed=(cj_assessment_service llm_provider_service)
    local needs_start=0

    for service in "${services_needed[@]}"; do
        if is_service_running "$service"; then
            echo_info "$service is already running"
        else
            echo_warn "$service is not running"
            needs_start=1
        fi
    done

    if [ $needs_start -eq 1 ]; then
        echo_runner "Starting dependent services..."
        docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d "${services_needed[@]}"

        # Wait for services to be healthy
        for service in "${services_needed[@]}"; do
            if ! wait_for_healthy "$service" 90; then
                echo_error "$service failed to become healthy"
                return 1
            fi
        done
    else
        echo_info "All dependent services are running"

        # Verify they are healthy
        for service in "${services_needed[@]}"; do
            if ! is_service_healthy "$service"; then
                echo_warn "$service is running but not healthy, waiting..."
                if ! wait_for_healthy "$service" 90; then
                    echo_error "$service is not healthy"
                    return 1
                fi
            fi
        done
    fi
}

# Main orchestration
main() {
    cd "$REPO_ROOT"

    echo_runner "Starting ENG5 NP Runner orchestration"
    echo_info "Arguments: $*"
    echo ""

    # Step 1: Ensure infrastructure is running
    if ! ensure_infrastructure; then
        echo_error "Failed to start infrastructure"
        exit 1
    fi
    echo ""

    # Step 2: Ensure Kafka topics are set up
    if ! ensure_topic_setup; then
        echo_error "Failed to set up Kafka topics"
        exit 1
    fi
    echo ""

    # Step 3: Ensure dependent services are running
    if ! ensure_dependent_services; then
        echo_error "Failed to start dependent services"
        exit 1
    fi
    echo ""

    # Step 4: Run the eng5_np_runner container
    echo_runner "Running eng5_np_runner container..."
    echo_info "Command: docker compose -f docker-compose.yml -f docker-compose.eng5-runner.yml run --rm eng5_np_runner $*"
    echo ""

    if docker compose -f docker-compose.yml -f docker-compose.eng5-runner.yml run --rm eng5_np_runner "$@"; then
        echo ""
        echo_runner "Runner completed successfully"
        exit 0
    else
        local exit_code=$?
        echo ""
        echo_error "Runner failed with exit code: $exit_code"
        exit $exit_code
    fi
}

# Run main with all arguments
main "$@"
