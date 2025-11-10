#!/usr/bin/env bash
#
# Pre-flight validation script for ENG5 NP runner (execute mode).
#
# This script validates the environment before running pdm run eng5-np-run --mode execute.
# It checks Docker services, Kafka connectivity, admin API access, source files, and output directory.
#
# Usage:
#   bash scripts/eng5_np_preflight.sh
#
# Exit codes:
#   0 - All checks passed
#   1 - One or more checks failed
#

set -uo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track overall status
CHECKS_PASSED=0
CHECKS_FAILED=0

# Helper functions
print_check() {
    echo -e "${YELLOW}[CHECK]${NC} $1"
}

print_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((CHECKS_PASSED++))
}

print_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((CHECKS_FAILED++))
}

print_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

# Check 1: Docker services running
print_check "Docker services (CJ Assessment Service)"
if docker compose -f docker-compose.yml -f docker-compose.dev.yml ps cj_assessment_service 2>/dev/null | grep -q huleedu_cj_assessment_service; then
    print_pass "CJ Assessment Service container is running"
else
    print_fail "CJ Assessment Service container not found. Run: pdm run dev-start cj_assessment_service"
fi

# Check 2: Kafka reachable
print_check "Kafka broker connectivity"
# Source .env to get Kafka bootstrap server (if needed)
if [ -f .env ]; then
    # shellcheck disable=SC1091
    source .env 2>/dev/null || true
fi

# Try to list topics using kafka-topics.sh with --bootstrap-server
if docker exec huleedu_kafka kafka-topics.sh --bootstrap-server localhost:9092 --list &>/dev/null; then
    print_pass "Kafka broker is reachable and responsive"
else
    print_fail "Kafka broker not reachable. Check if Kafka container is running: docker compose -f docker-compose.yml -f docker-compose.dev.yml ps kafka"
fi

# Check 3: CJ Admin API and token validation
print_check "CJ Admin API access (token validation)"
# This requires the admin CLI tool to be available
if command -v pdm &>/dev/null; then
    if pdm run cj-admin --help &>/dev/null; then
        print_pass "CJ admin CLI tool is available"
        print_info "    To validate token, run: pdm run cj-admin list-instructions"
    else
        print_fail "CJ admin CLI tool not available. Check pyproject.toml scripts section"
    fi
else
    print_fail "PDM not found. Install PDM: https://pdm.fming.dev"
fi

# Check 4: Source files present
print_check "ENG5 NP source files"
# ENG5 NP dataset lives under test_uploads with spaces in path; keep everything quoted when used
ROLE_MODELS_ROOT="test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016"

# Expected files
FILES_TO_CHECK=(
    "${ROLE_MODELS_ROOT}/eng5_np_vt_2017_essay_instruction.md"
    "${ROLE_MODELS_ROOT}/llm_prompt_cj_assessment_eng5.md"
)

MISSING_FILES=0
for file in "${FILES_TO_CHECK[@]}"; do
    if [ -f "$file" ]; then
        print_info "    Found: $file"
    else
        print_fail "    Missing: $file"
        ((MISSING_FILES++))
    fi
done

# Check for anchor and student directories
ANCHORS_DIR="${ROLE_MODELS_ROOT}/anchor_essays"
STUDENTS_DIR="${ROLE_MODELS_ROOT}/student_essays"

if [ -d "$ANCHORS_DIR" ] && [ "$(find "$ANCHORS_DIR" -type f \( -name "*.docx" -o -name "*.txt" \) | wc -l)" -gt 0 ]; then
    ANCHOR_COUNT=$(find "$ANCHORS_DIR" -type f \( -name "*.docx" -o -name "*.txt" \) | wc -l)
    print_info "    Found $ANCHOR_COUNT anchor essay files in $ANCHORS_DIR"
else
    print_fail "    No anchor essays found in $ANCHORS_DIR"
    ((MISSING_FILES++))
fi

if [ -d "$STUDENTS_DIR" ] && [ "$(find "$STUDENTS_DIR" -type f \( -name "*.docx" -o -name "*.txt" \) | wc -l)" -gt 0 ]; then
    STUDENT_COUNT=$(find "$STUDENTS_DIR" -type f \( -name "*.docx" -o -name "*.txt" \) | wc -l)
    print_info "    Found $STUDENT_COUNT student essay files in $STUDENTS_DIR"
else
    print_fail "    No student essays found in $STUDENTS_DIR"
    ((MISSING_FILES++))
fi

if [ $MISSING_FILES -eq 0 ]; then
    print_pass "All required source files present"
else
    print_fail "Missing $MISSING_FILES required source file(s)"
fi

# Check 5: Output directory writable
print_check "Output directory"
OUTPUT_DIR=".claude/research/data/eng5_np_2016"

if [ -d "$OUTPUT_DIR" ]; then
    if [ -w "$OUTPUT_DIR" ]; then
        print_pass "Output directory $OUTPUT_DIR is writable"
    else
        print_fail "Output directory $OUTPUT_DIR exists but is not writable"
    fi
else
    print_info "    Output directory $OUTPUT_DIR does not exist. Creating..."
    if mkdir -p "$OUTPUT_DIR" 2>/dev/null; then
        print_pass "Created output directory $OUTPUT_DIR"
    else
        print_fail "Failed to create output directory $OUTPUT_DIR"
    fi
fi

# Check 6: Python environment and dependencies
print_check "Python environment and runner dependencies"
if pdm run python -c "import scripts.cj_experiments_runners.eng5_np.cli" &>/dev/null; then
    print_pass "ENG5 NP runner module is importable"
else
    print_fail "ENG5 NP runner module cannot be imported. Run: pdm install"
fi

# Summary
echo ""
echo "========================================="
echo "Pre-flight Check Summary"
echo "========================================="
echo -e "Checks passed: ${GREEN}${CHECKS_PASSED}${NC}"
echo -e "Checks failed: ${RED}${CHECKS_FAILED}${NC}"
echo ""

if [ $CHECKS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All pre-flight checks passed!${NC}"
    echo ""
    echo "You can now run:"
    echo "  pdm run eng5-np-run --mode execute --batch-id <your-batch-id>"
    exit 0
else
    echo -e "${RED}✗ Pre-flight checks failed!${NC}"
    echo ""
    echo "Please fix the issues above before running execute mode."
    exit 1
fi
