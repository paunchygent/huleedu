#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}PDM Segmentation Fault Diagnostic Tool${NC}"
echo "========================================"
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed or not in PATH${NC}"
    exit 1
fi

# Create log directory
LOG_DIR="pdm_diagnostic_logs"
mkdir -p "$LOG_DIR"

# Results tracking
RESULTS_FILE="$LOG_DIR/results.txt"
echo "" > "$RESULTS_FILE"

# Function to run a test
run_test() {
    local test_name=$1
    local dockerfile=$2
    local tag=$3
    local description=$4
    
    echo -e "\n${YELLOW}Running Test: $test_name${NC}"
    echo "Description: $description"
    echo "Building with: $dockerfile"
    
    local start_time=$(date +%s)
    local log_file="$LOG_DIR/${test_name}_build.log"
    
    # Run Docker build
    if docker build --no-cache -f "$dockerfile" -t "$tag" . > "$log_file" 2>&1; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        
        # Get image size
        local size=$(docker images --format "{{.Size}}" "$tag" | head -1)
        
        echo -e "${GREEN}✅ $test_name PASSED${NC} (${duration}s, Image: $size)"
        echo "$test_name|PASSED|$duration|$size" >> "$RESULTS_FILE"
        
        # Test if the container can start
        echo "Testing container startup..."
        if docker run --rm -d --name "${tag}_test" "$tag" > /dev/null 2>&1; then
            docker stop "${tag}_test" > /dev/null 2>&1 || true
            echo -e "${GREEN}✅ Container starts successfully${NC}"
        else
            echo -e "${YELLOW}⚠️  Container failed to start${NC}"
        fi
    else
        echo -e "${RED}❌ $test_name FAILED${NC}"
        echo "$test_name|FAILED|0|0" >> "$RESULTS_FILE"
        echo "Last 20 lines of error log:"
        tail -20 "$log_file"
    fi
}

# Create test Dockerfiles
echo "Creating test Dockerfiles..."

# Test 1: --no-lock approach (maintains current pattern)
cat > services/file_service/Dockerfile.test1 << 'EOF'
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PDM_USE_VENV=false \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    FILE_SERVICE_LOG_LEVEL=INFO \
    FILE_SERVICE_HTTP_PORT=7001 \
    FILE_SERVICE_PROMETHEUS_PORT=9092 \
    FILE_SERVICE_HOST=0.0.0.0

WORKDIR /app

# Install dependencies with memory optimization
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir pdm

COPY libs/common_core/ /app/libs/common_core/
COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/
COPY services/file_service/ /app/services/file_service/

WORKDIR /app/services/file_service

# Use --no-lock to skip lockfile generation
RUN pdm install --prod --no-lock

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE ${FILE_SERVICE_HTTP_PORT}
EXPOSE ${FILE_SERVICE_PROMETHEUS_PORT}

CMD ["pdm", "run", "start"]
EOF

# Test 2: Pin PDM version
cat > services/file_service/Dockerfile.test2 << 'EOF'
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PDM_USE_VENV=false \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    FILE_SERVICE_LOG_LEVEL=INFO \
    FILE_SERVICE_HTTP_PORT=7001 \
    FILE_SERVICE_PROMETHEUS_PORT=9092 \
    FILE_SERVICE_HOST=0.0.0.0

WORKDIR /app

# Pin to a stable PDM version
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir pdm==2.12.4

COPY libs/common_core/ /app/libs/common_core/
COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/
COPY services/file_service/ /app/services/file_service/

WORKDIR /app/services/file_service
RUN pdm install --prod

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE ${FILE_SERVICE_HTTP_PORT}
EXPOSE ${FILE_SERVICE_PROMETHEUS_PORT}

CMD ["pdm", "run", "start"]
EOF

# Test 3: Export to pip (production optimization)
cat > services/file_service/Dockerfile.test3 << 'EOF'
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    FILE_SERVICE_LOG_LEVEL=INFO \
    FILE_SERVICE_HTTP_PORT=7001 \
    FILE_SERVICE_PROMETHEUS_PORT=9092 \
    FILE_SERVICE_HOST=0.0.0.0

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY libs/common_core/ /app/libs/common_core/
COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/
COPY services/file_service/ /app/services/file_service/

WORKDIR /app/services/file_service

# Use PDM to export requirements, then use pip
RUN pip install --no-cache-dir pdm && \
    pdm export --prod -f requirements > requirements.txt && \
    pip uninstall -y pdm && \
    pip install --no-cache-dir -r requirements.txt && \
    rm requirements.txt

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE ${FILE_SERVICE_HTTP_PORT}
EXPOSE ${FILE_SERVICE_PROMETHEUS_PORT}

CMD ["hypercorn", "app:app", "--config", "python:hypercorn_config"]
EOF

# Test 4: Memory-limited build with current approach
cat > services/file_service/Dockerfile.test4 << 'EOF'
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PDM_USE_VENV=false \
    ENV_TYPE=docker \
    QUART_APP=app:app \
    QUART_ENV=production \
    FILE_SERVICE_LOG_LEVEL=INFO \
    FILE_SERVICE_HTTP_PORT=7001 \
    FILE_SERVICE_PROMETHEUS_PORT=9092 \
    FILE_SERVICE_HOST=0.0.0.0 \
    PYTHONMALLOC=malloc

WORKDIR /app

# Install with memory optimization flags
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir pdm

COPY libs/common_core/ /app/libs/common_core/
COPY libs/huleedu_service_libs/ /app/libs/huleedu_service_libs/
COPY services/file_service/ /app/services/file_service/

WORKDIR /app/services/file_service

# Try with memory limits
RUN ulimit -v 2097152 && pdm install --prod || \
    echo "Trying with --no-self flag..." && pdm install --prod --no-self

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE ${FILE_SERVICE_HTTP_PORT}
EXPOSE ${FILE_SERVICE_PROMETHEUS_PORT}

CMD ["pdm", "run", "start"]
EOF

echo -e "\n${BLUE}Starting diagnostic tests...${NC}"

# Run tests in recommended order
run_test "test1_no_lock" "services/file_service/Dockerfile.test1" "file_service_test1" \
    "PDM with --no-lock flag (maintains current pattern)"

run_test "test2_pinned_version" "services/file_service/Dockerfile.test2" "file_service_test2" \
    "PDM pinned to version 2.12.4"

run_test "test3_pip_export" "services/file_service/Dockerfile.test3" "file_service_test3" \
    "Export to pip for production"

run_test "test4_memory_limit" "services/file_service/Dockerfile.test4" "file_service_test4" \
    "Current approach with memory optimizations"

# Generate summary report
echo -e "\n${BLUE}========== DIAGNOSTIC SUMMARY ==========${NC}"
echo ""
echo "Test Results:"
while IFS='|' read -r test_name status duration size; do
    if [[ -n "$test_name" ]]; then
        if [[ $status == "PASSED" ]]; then
            echo -e "  $test_name: ${GREEN}$status${NC} (${duration}s, ${size})"
        else
            echo -e "  $test_name: ${RED}$status${NC}"
        fi
    fi
done < "$RESULTS_FILE"

# Check specific test results for recommendations
TEST1_PASSED=$(grep "test1_no_lock|PASSED" "$RESULTS_FILE" || echo "")
TEST2_PASSED=$(grep "test2_pinned_version|PASSED" "$RESULTS_FILE" || echo "")
TEST3_PASSED=$(grep "test3_pip_export|PASSED" "$RESULTS_FILE" || echo "")

# Recommendations
echo -e "\n${BLUE}RECOMMENDATIONS:${NC}"
if [[ -n "$TEST1_PASSED" ]]; then
    echo -e "${GREEN}✅ Recommended: Use --no-lock approach${NC}"
    echo "   - Maintains your established pattern (no pdm.lock in Docker)"
    echo "   - Avoids segmentation fault during lockfile generation"
    echo "   - Minimal change to existing workflow"
elif [[ -n "$TEST3_PASSED" ]]; then
    echo -e "${YELLOW}⚠️  Alternative: Use pip export approach${NC}"
    echo "   - More stable for production builds"
    echo "   - Smaller image size"
    echo "   - Requires changing CMD in Dockerfile"
elif [[ -n "$TEST2_PASSED" ]]; then
    echo -e "${YELLOW}⚠️  Fallback: Pin PDM version${NC}"
    echo "   - May need periodic updates"
    echo "   - Still generates lockfile (pattern change)"
else
    echo -e "${RED}❌ All approaches failed - investigate logs in $LOG_DIR${NC}"
fi

echo -e "\n${BLUE}Cleanup:${NC}"
echo "To remove test images: docker rmi file_service_test1 file_service_test2 file_service_test3 file_service_test4"
echo "To remove test Dockerfiles: rm services/file_service/Dockerfile.test*"
echo "Logs saved in: $LOG_DIR/"