#!/usr/bin/env bash
#
# OTEL Trace Context Validation Script
# Validates that OpenTelemetry trace_id and span_id appear correctly in Docker logs
#
# Usage:
#   ./validate_otel_trace_context.sh [service_name]
#   ./validate_otel_trace_context.sh              # Validates all priority services
#   ./validate_otel_trace_context.sh cj_assessment # Validates specific service
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Priority services to validate (all services with logger timing fix applied)
# Note: Container names match actual docker-compose service names
# - essay_lifecycle: split into _api and _worker containers
PRIORITY_SERVICES=(
    "batch_conductor_service"
    "batch_orchestrator_service"
    "content_service"
    "identity_service"
    "file_service"
    "class_management_service"
    "email_service"
    "llm_provider_service"
    "entitlements_service"
    "websocket_service"
    "language_tool_service"
    "result_aggregator_service"
    "essay_lifecycle_api"
    "essay_lifecycle_worker"
    "nlp_service"
    "cj_assessment_service"
    "api_gateway_service"
    "spellchecker_service"
)

# Results storage (simple variables)
RESULTS_FILE="/tmp/otel_validation_results_$$.txt"
trap "rm -f ${RESULTS_FILE}" EXIT

validate_service_trace_context() {
    local service_name=$1
    local container_name="huleedu_${service_name}"

    echo -e "${BLUE}=== Validating ${service_name} ===${NC}"

    # Check container exists and is running
    if ! docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
        echo -e "${YELLOW}⚠ Container ${container_name} not running${NC}"
        echo "${service_name}|NO|N/A|N/A|N/A|N/A|SKIP" >> "${RESULTS_FILE}"
        return 1
    fi

    # Get total log lines
    local total_lines=$(docker logs "${container_name}" 2>&1 | wc -l | tr -d ' ')

    # Extract logs with trace context (filter JSON lines first, then take last 500)
    local logs_with_trace=$(docker logs "${container_name}" 2>&1 | \
        grep -a '^{' | tail -500 | \
        jq -r 'select(.trace_id) | {timestamp, event, trace_id, span_id, correlation_id}' 2>/dev/null || echo "")

    if [[ -z "${logs_with_trace}" ]]; then
        echo -e "${YELLOW}⚠ No logs with trace_id found${NC}"
        echo -e "${YELLOW}  This may be expected if no traced operations have occurred yet${NC}"
        echo "${service_name}|YES|NO|NO|N/A|0%|WARN" >> "${RESULTS_FILE}"
        echo ""
        return 0
    fi

    # Count logs with trace context (filter JSON lines first, then take last 500)
    local trace_count=$(docker logs "${container_name}" 2>&1 | \
        grep -a '^{' | tail -500 | \
        jq -r 'select(.trace_id)' 2>/dev/null | wc -l | tr -d ' ')

    # Calculate percentage (of last 500 lines checked)
    local checked_lines=500
    if [[ ${total_lines} -lt 500 ]]; then
        checked_lines=${total_lines}
    fi
    local percent=0
    if [[ ${checked_lines} -gt 0 ]]; then
        percent=$((trace_count * 100 / checked_lines))
    fi

    # Validate format (trace_id: 32-char hex, span_id: 16-char hex)
    local sample_trace_id=$(docker logs "${container_name}" 2>&1 | \
        grep -a '^{' | tail -200 | \
        jq -r '.trace_id // empty' 2>/dev/null | grep -v '^$' | head -1)

    local sample_span_id=$(docker logs "${container_name}" 2>&1 | \
        grep -a '^{' | tail -200 | \
        jq -r '.span_id // empty' 2>/dev/null | grep -v '^$' | head -1)

    local has_span_id="NO"
    local format_valid="N/A"
    local overall_status="FAIL"

    if [[ -n "${sample_trace_id}" ]] && [[ -n "${sample_span_id}" ]]; then
        has_span_id="YES"

        # Validate trace_id format (32 hex chars)
        local trace_format_valid=false
        if [[ ${#sample_trace_id} -eq 32 ]] && [[ "${sample_trace_id}" =~ ^[0-9a-f]{32}$ ]]; then
            trace_format_valid=true
        else
            echo -e "${RED}✗ Invalid trace_id format: ${sample_trace_id} (length: ${#sample_trace_id})${NC}"
        fi

        # Validate span_id format (16 hex chars)
        local span_format_valid=false
        if [[ ${#sample_span_id} -eq 16 ]] && [[ "${sample_span_id}" =~ ^[0-9a-f]{16}$ ]]; then
            span_format_valid=true
        else
            echo -e "${RED}✗ Invalid span_id format: ${sample_span_id} (length: ${#sample_span_id})${NC}"
        fi

        # Overall format validation
        if ${trace_format_valid} && ${span_format_valid}; then
            format_valid="YES"
            echo -e "${GREEN}✓ Format valid: trace_id (32-char hex), span_id (16-char hex)${NC}"
            overall_status="PASS"
        else
            format_valid="NO"
            overall_status="FAIL"
        fi

        # Show sample log entry
        echo -e "${BLUE}Sample log with trace context:${NC}"
        docker logs "${container_name}" --tail 100 2>&1 | \
            grep -a '^{' | \
            jq -r 'select(.trace_id) | {timestamp, event, trace_id, span_id}' 2>/dev/null | \
            head -3 | sed 's/^/  /' || true

        # Store sample trace_id for cross-service validation
        echo "${service_name}_trace_id=${sample_trace_id}" >> "${RESULTS_FILE}.traces"

    else
        has_span_id="PARTIAL"
        format_valid="UNKNOWN"
        overall_status="WARN"
        echo -e "${YELLOW}⚠ Could not extract both trace_id and span_id${NC}"
    fi

    # Save results
    echo "${service_name}|YES|YES|${has_span_id}|${format_valid}|${percent}%|${overall_status}" >> "${RESULTS_FILE}"

    # Print status
    if [[ "${overall_status}" == "PASS" ]]; then
        echo -e "${GREEN}✓ Service validation passed (${trace_count}/${checked_lines} logs have trace context)${NC}"
    elif [[ "${overall_status}" == "WARN" ]]; then
        echo -e "${YELLOW}⚠ Service has partial trace context${NC}"
    else
        echo -e "${RED}✗ Service validation failed${NC}"
    fi

    echo ""
}

validate_cross_service_tracing() {
    echo -e "${BLUE}=== Cross-Service Trace Validation ===${NC}"

    if [[ ! -f "${RESULTS_FILE}.traces" ]]; then
        echo -e "${YELLOW}⚠ No trace_id found to validate cross-service tracing${NC}"
        echo ""
        return 0
    fi

    # Get first trace_id
    local reference_trace_id=$(head -1 "${RESULTS_FILE}.traces" | cut -d= -f2)
    local reference_service=$(head -1 "${RESULTS_FILE}.traces" | cut -d= -f1 | sed 's/_trace_id//')

    if [[ -z "${reference_trace_id}" ]]; then
        echo -e "${YELLOW}⚠ No trace_id found to validate cross-service tracing${NC}"
        echo ""
        return 0
    fi

    echo -e "Using trace_id from ${reference_service}: ${reference_trace_id}"
    echo ""

    # Search for this trace_id in other running services
    local found_count=0
    for service in "${PRIORITY_SERVICES[@]}"; do
        local container_name="huleedu_${service}"

        if ! docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
            continue
        fi

        local matches=$(docker logs "${container_name}" 2>&1 | \
            grep -a '^{' | \
            jq -r "select(.trace_id == \"${reference_trace_id}\") | {service: .\"service.name\", event, timestamp}" 2>/dev/null || echo "")

        if [[ -n "${matches}" ]]; then
            found_count=$((found_count + 1))
            echo -e "${GREEN}✓ Found in ${service}:${NC}"
            echo "${matches}" | head -2 | sed 's/^/  /'
        fi
    done

    if [[ ${found_count} -gt 1 ]]; then
        echo -e "\n${GREEN}✓ Cross-service tracing validated (trace_id found in ${found_count} services)${NC}"
    elif [[ ${found_count} -eq 1 ]]; then
        echo -e "\n${YELLOW}⚠ Trace only found in single service (expected for isolated operations)${NC}"
    else
        echo -e "\n${YELLOW}⚠ Could not validate cross-service tracing${NC}"
    fi

    echo ""
}

validate_jaeger_correlation() {
    echo -e "${BLUE}=== Jaeger Correlation Validation ===${NC}"

    # Check if Jaeger is accessible
    if ! curl -sf http://localhost:16686/api/services >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠ Jaeger not accessible at localhost:16686${NC}"
        echo ""
        return 0
    fi

    echo -e "${GREEN}✓ Jaeger is accessible${NC}"

    if [[ ! -f "${RESULTS_FILE}.traces" ]]; then
        echo -e "${YELLOW}⚠ No trace_id available to check in Jaeger${NC}"
        echo ""
        return 0
    fi

    # Get first trace_id
    local sample_trace_id=$(head -1 "${RESULTS_FILE}.traces" | cut -d= -f2)

    if [[ -z "${sample_trace_id}" ]]; then
        echo -e "${YELLOW}⚠ No trace_id available to check in Jaeger${NC}"
        echo ""
        return 0
    fi

    echo -e "Checking trace_id in Jaeger: ${sample_trace_id}"

    # Query Jaeger for this trace
    local jaeger_trace=$(curl -sf "http://localhost:16686/api/traces/${sample_trace_id}" 2>/dev/null | \
        jq -r '.data[0].traceID // "NOT_FOUND"' 2>/dev/null || echo "ERROR")

    if [[ "${jaeger_trace}" == "NOT_FOUND" ]] || [[ "${jaeger_trace}" == "ERROR" ]]; then
        echo -e "${YELLOW}⚠ Trace not found in Jaeger (may be too recent or already exported)${NC}"
    else
        echo -e "${GREEN}✓ Trace exists in Jaeger: ${jaeger_trace}${NC}"
    fi

    echo ""
}

print_validation_matrix() {
    echo -e "${BLUE}=== Validation Matrix ===${NC}"
    echo ""
    printf "| %-30s | %-17s | %-16s | %-15s | %-12s | %-14s | %-6s |\n" \
        "Service" "Container Running" "Logs Have trace_id" "Logs Have span_id" "Format Valid" "% With Context" "Status"
    printf "|%.0s-" {1..140}
    echo "|"

    if [[ -f "${RESULTS_FILE}" ]]; then
        while IFS='|' read -r service running has_trace has_span format_valid percent status; do
            # Color status
            local status_colored="${status}"
            case "${status}" in
                PASS) status_colored="${GREEN}${status}${NC}" ;;
                WARN) status_colored="${YELLOW}${status}${NC}" ;;
                FAIL) status_colored="${RED}${status}${NC}" ;;
                SKIP) status_colored="${YELLOW}${status}${NC}" ;;
            esac

            printf "| %-30s | %-17s | %-16s | %-15s | %-12s | %-14s | " \
                "${service}" "${running}" "${has_trace}" "${has_span}" "${format_valid}" "${percent}"
            echo -e "${status_colored} |"
        done < "${RESULTS_FILE}"
    fi

    echo ""
}

print_recommendations() {
    echo -e "${BLUE}=== Recommendations ===${NC}"
    echo ""

    if [[ ! -f "${RESULTS_FILE}" ]]; then
        echo -e "${YELLOW}⚠ No validation results available${NC}"
        echo ""
        return 0
    fi

    local all_pass=true
    local some_skip=false
    local some_fail=false

    while IFS='|' read -r service running has_trace has_span format_valid percent status; do
        if [[ "${status}" != "PASS" ]]; then
            all_pass=false
        fi
        if [[ "${status}" == "SKIP" ]]; then
            some_skip=true
        fi
        if [[ "${status}" == "FAIL" ]]; then
            some_fail=true
        fi
    done < "${RESULTS_FILE}"

    if ${all_pass}; then
        echo -e "${GREEN}✓ All validated services have correct OTEL trace context in logs${NC}"
        echo -e "  - trace_id format: 32-character hexadecimal"
        echo -e "  - span_id format: 16-character hexadecimal"
        echo -e "  - Fields appear in logs when spans are active"
    elif ${some_skip}; then
        echo -e "${YELLOW}⚠ Some services not running - start services to validate:${NC}"
        while IFS='|' read -r service running has_trace has_span format_valid percent status; do
            if [[ "${status}" == "SKIP" ]]; then
                echo -e "  pdm run dev-start ${service}"
            fi
        done < "${RESULTS_FILE}"
    fi

    if ${some_fail}; then
        echo -e "\n${RED}✗ Issues found:${NC}"
        while IFS='|' read -r service running has_trace has_span format_valid percent status; do
            if [[ "${status}" == "FAIL" ]] || [[ "${status}" == "WARN" ]]; then
                echo -e "  - ${service}: ${status}"
                if [[ "${has_trace}" == "NO" ]]; then
                    echo -e "    Action: Check that tracing is initialized in service startup"
                fi
                if [[ "${format_valid}" == "NO" ]]; then
                    echo -e "    Action: Verify add_trace_context processor is in structlog chain"
                fi
            fi
        done < "${RESULTS_FILE}"
    fi

    echo ""
}

main() {
    local target_service="${1:-}"

    echo -e "${BLUE}OTEL Trace Context Validation${NC}"
    echo -e "${BLUE}==============================${NC}"
    echo ""

    # Initialize results file
    > "${RESULTS_FILE}"
    > "${RESULTS_FILE}.traces"

    if [[ -n "${target_service}" ]]; then
        # Validate single service
        validate_service_trace_context "${target_service}"
    else
        # Validate all priority services
        for service in "${PRIORITY_SERVICES[@]}"; do
            validate_service_trace_context "${service}"
        done

        # Cross-service validation
        validate_cross_service_tracing

        # Jaeger correlation
        validate_jaeger_correlation

        # Print summary
        print_validation_matrix
        print_recommendations
    fi
}

main "$@"
