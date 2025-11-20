#!/bin/bash

# HuleEdu Development Environment Script
# For DEVELOPMENT builds and operations (hot-reload enabled, debug mode)
# For production operations, use prod.sh
#
# IMPORTANT FOR AI ASSISTANTS:
# - This script manages DEVELOPMENT containers only
# - Uses docker-compose.yml + docker-compose.dev.yml
# - Builds from Dockerfile.dev with 'development' target
# - Enables hot-reload via volume mounts
# - Debug logging (LOG_LEVEL=DEBUG)
# - Use 'pdm run dev-*' commands for development
# - Use 'pdm run prod-*' commands for production

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

SCRIPT_DIR=$(cd -- "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
DEPS_IMAGE_TAG=""

# IMPORTANT: Source .env file to ensure docker-compose uses .env values
# This overrides any conflicting shell environment variables
if [ -f "$REPO_ROOT/.env" ]; then
    set -a  # automatically export all variables
    source "$REPO_ROOT/.env"
    set +a
fi

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_warning() {
    echo_warn "$1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo_dev() {
    echo -e "${CYAN}[DEV]${NC} $1"
}

compute_deps_hash() {
    python "$REPO_ROOT/scripts/compute_deps_hash.py"
}

ensure_deps_image() {
    local mode="$1"
    local deps_hash
    deps_hash=$(compute_deps_hash)
    DEPS_IMAGE_TAG="huledu-deps:${deps_hash}"
    export DEPS_IMAGE_TAG

    local needs_build=0
    if [ "$mode" = "clean" ]; then
        needs_build=1
    elif ! docker image inspect "$DEPS_IMAGE_TAG" >/dev/null 2>&1; then
        needs_build=1
    fi

    if [ $needs_build -eq 1 ]; then
        echo_info "Building shared dependency image ${DEPS_IMAGE_TAG}"
        local build_cmd=(docker build)
        if [ "$mode" = "clean" ]; then
            build_cmd+=(--no-cache)
        fi
        build_cmd+=(-f "$REPO_ROOT/Dockerfile.deps" -t "$DEPS_IMAGE_TAG" -t "huledu-deps:dev" "$REPO_ROOT")
        "${build_cmd[@]}"
    else
        echo_info "Using cached dependency image ${DEPS_IMAGE_TAG}"
    fi
}

# Build services for development with cache
build_dev() {
    local services=("$@")
    local display="all services"
    if [ ${#services[@]} -gt 0 ]; then
        display="${services[*]}"
    fi
    echo_dev "Building for DEVELOPMENT with cache: ${display}"
    echo_info "Using Dockerfile.dev with 'development' target"

    ensure_deps_image ""

    if [ ${#services[@]} -gt 0 ]; then
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml build --parallel "${services[@]}"
    else
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml build --parallel
    fi

    echo_dev "Development build complete!"
}

# Clean build for development (no cache)
build_clean_dev() {
    local services=("$@")
    local display="all services"
    if [ ${#services[@]} -gt 0 ]; then
        display="${services[*]}"
    fi
    echo_dev "Clean build for DEVELOPMENT (no cache): ${display}"
    echo_warn "This will take longer as all layers will be rebuilt"

    ensure_deps_image "clean"

    if [ ${#services[@]} -gt 0 ]; then
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml build --no-cache --parallel "${services[@]}"
    else
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml build --no-cache --parallel
    fi

    echo_dev "Clean development build complete!"
}

# Start development environment (builds if needed, then starts with hot-reload)
start_dev() {
    local services=("$@")
    local display="all services"
    if [ ${#services[@]} -gt 0 ]; then
        display="${services[*]}"
    fi
    echo_dev "Starting DEVELOPMENT environment: ${display}"
    echo_info "Hot-reload enabled via volume mounts"
    echo_info "Debug logging enabled"

    # Build first if needed
    echo_info "Checking for required builds..."
    ensure_deps_image ""
    if [ ${#services[@]} -gt 0 ]; then
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml build --parallel "${services[@]}"
    else
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml build --parallel
    fi

    # Then start
    echo_info "Starting containers..."
    if [ ${#services[@]} -gt 0 ]; then
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d "${services[@]}"
    else
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
    fi

    echo_dev "Development environment running!"
    echo_info "View logs: pdm run dev-logs ${display}"
    echo_info "Code changes will auto-reload"
}

# Start development environment without rebuilding (fast start)
start_dev_nobuild() {
    local services=("$@")
    local display="all services"
    if [ ${#services[@]} -gt 0 ]; then
        display="${services[*]}"
    fi
    echo_dev "Starting DEVELOPMENT environment (no rebuild): ${display}"
    echo_info "Hot-reload enabled via volume mounts"
    echo_info "Debug logging enabled"
    echo_warning "Skipping build - using existing images"

    # Start without building
    echo_info "Starting containers..."
    if [ ${#services[@]} -gt 0 ]; then
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --no-build "${services[@]}"
    else
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --no-build
    fi

    echo_dev "Development environment running!"
    echo_info "View logs: pdm run dev-logs ${display}"
    echo_info "Code changes will auto-reload"
    echo_info "If images are missing, use: pdm run dev-build-start"
}

# Stop development containers
stop_dev() {
    local services=("$@")
    local display="all containers"
    if [ ${#services[@]} -gt 0 ]; then
        display="${services[*]}"
    fi
    echo_dev "Stopping DEVELOPMENT containers: ${display}"

    if [ ${#services[@]} -gt 0 ]; then
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml stop "${services[@]}"
    else
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml stop
    fi

    echo_dev "Development containers stopped"
}

# Restart development containers
restart_dev() {
    local services=("$@")
    local display="all containers"
    if [ ${#services[@]} -gt 0 ]; then
        display="${services[*]}"
    fi
    echo_dev "Restarting DEVELOPMENT containers: ${display}"

    if [ ${#services[@]} -gt 0 ]; then
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml restart "${services[@]}"
    else
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml restart
    fi

    echo_dev "Development containers restarted"
}

# Force recreate development SERVICE containers only (excludes databases)
# Use this when environment variables changed - databases won't be reset
recreate_dev() {
    local services=("$@")
    local display="all service containers"
    if [ ${#services[@]} -gt 0 ]; then
        display="${services[*]}"
    fi
    echo_dev "Force recreating DEVELOPMENT service containers (databases excluded): ${display}"
    echo_warn "This will recreate service containers to pick up configuration changes"
    echo_info "Use this when docker-compose.yml environment variables changed"
    echo_info "Databases will NOT be reset - use 'pdm run dev-db-recreate' to reset databases"

    # Database services to exclude from recreation
    local db_services=(
        "batch_orchestrator_db"
        "essay_lifecycle_db"
        "cj_assessment_db"
        "class_management_db"
        "file_service_db"
        "content_service_db"
        "redis"
        "spellchecker_db"
        "result_aggregator_db"
        "nlp_db"
        "batch_conductor_db"
        "identity_db"
        "email_db"
        "entitlements_db"
        "zookeeper"
        "kafka"
    )

    if [ ${#services[@]} -gt 0 ]; then
        # User specified services - recreate only those
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate --no-build "${services[@]}"
    else
        # Get all service names and exclude databases
        local all_services=$(docker-compose -f docker-compose.yml -f docker-compose.dev.yml config --services)
        local services_to_recreate=()

        for service in $all_services; do
            local is_db=false
            for db_service in "${db_services[@]}"; do
                if [ "$service" = "$db_service" ]; then
                    is_db=true
                    break
                fi
            done

            if [ "$is_db" = false ]; then
                services_to_recreate+=("$service")
            fi
        done

        if [ ${#services_to_recreate[@]} -gt 0 ]; then
            docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate --no-build "${services_to_recreate[@]}"
        else
            echo_warn "No service containers found to recreate"
        fi
    fi

    echo_dev "Development service containers recreated"
    echo_info "Containers will use updated environment variables"
    echo_info "Database data preserved"
}

# Force recreate database containers (resets data)
recreate_db_dev() {
    local services=("$@")
    local display="all database containers"
    if [ ${#services[@]} -gt 0 ]; then
        display="${services[*]}"
    fi
    echo_dev "Force recreating DEVELOPMENT database containers: ${display}"
    echo_warn "⚠️  WARNING: This will RESET database data!"
    echo_info "Use this only when you need to reset database state"

    # Database services
    local db_services=(
        "batch_orchestrator_db"
        "essay_lifecycle_db"
        "cj_assessment_db"
        "class_management_db"
        "file_service_db"
        "content_service_db"
        "redis"
        "spellchecker_db"
        "result_aggregator_db"
        "nlp_db"
        "batch_conductor_db"
        "identity_db"
        "email_db"
        "entitlements_db"
    )

    if [ ${#services[@]} -gt 0 ]; then
        # User specified services - recreate only those
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate --no-build "${services[@]}"
    else
        # Recreate all database services
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate --no-build "${db_services[@]}"
    fi

    echo_dev "Development database containers recreated"
    echo_warn "Database data has been reset"
}

# Remove development containers (preserves images)
remove_dev() {
    local services=("$@")
    local display="all containers"
    if [ ${#services[@]} -gt 0 ]; then
        display="${services[*]}"
    fi
    echo_dev "Removing DEVELOPMENT containers: ${display}"
    echo_warn "This will remove containers but preserve images"

    if [ ${#services[@]} -gt 0 ]; then
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml rm -f "${services[@]}"
    else
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml rm -f
    fi

    echo_dev "Development containers removed"
}

# View development logs
logs_dev() {
    local services=("$@")
    local display="all services"
    if [ ${#services[@]} -gt 0 ]; then
        display="${services[*]}"
    fi
    echo_dev "Following DEVELOPMENT logs: ${display}"
    echo_info "Press Ctrl+C to exit"

    if [ ${#services[@]} -gt 0 ]; then
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f --tail=50 "${services[@]}"
    else
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f --tail=50
    fi
}

# Show development container status
ps_dev() {
    local services=("$@")
    local display="all services"
    if [ ${#services[@]} -gt 0 ]; then
        display="${services[*]}"
    fi
    echo_dev "Container status (DEVELOPMENT): ${display}"

    if [ ${#services[@]} -gt 0 ]; then
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps "${services[@]}"
    else
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps
    fi
}

# Check what needs rebuilding
check_changes() {
    echo_info "Checking what might need rebuilding..."

    if git rev-parse --git-dir > /dev/null 2>&1; then
        local changed_files=$(git diff --name-only HEAD~1 HEAD 2>/dev/null || echo "")

        if [ -z "$changed_files" ]; then
            echo_info "No changes in last commit"
            return
        fi

        echo_info "Files changed in last commit:"

        if echo "$changed_files" | grep -q "libs/common_core\|libs/huleedu_service_libs\|libs/huleedu_nlp_shared"; then
            echo_warn "  → Shared libraries changed - rebuild all services recommended"
        fi

        if echo "$changed_files" | grep -q "docker-compose\|Dockerfile"; then
            echo_warn "  → Docker configuration changed - rebuild affected services"
        fi

        for service_dir in services/*/; do
            service_name=$(basename "$service_dir")
            if echo "$changed_files" | grep -q "services/$service_name/"; then
                echo_warn "  → $service_name has changes"
            fi
        done
    else
        echo_warn "Not in a git repository - cannot detect changes"
    fi
}

# Show help
show_help() {
    echo "HuleEdu Development Environment Script"
    echo ""
    echo "This script manages DEVELOPMENT containers with hot-reload and debug features."
    echo "For production operations, use prod.sh"
    echo ""
    echo "Usage: $0 <command> [services]"
    echo ""
    echo "Commands:"
    echo "  build [services]         Build with cache (uses Dockerfile.dev)"
    echo "  build-clean [services]   Build without cache"
    echo "  start [services]         Build with cache + start with hot-reload"
    echo "  start-nobuild [services] Start with hot-reload (no rebuild, fast)"
    echo "  stop [services]          Stop containers"
    echo "  restart [services]       Restart containers (does NOT pick up env changes)"
    echo "  recreate [services]      Force recreate SERVICE containers only (preserves databases)"
    echo "  recreate-db [services]   Force recreate DATABASE containers (⚠️  RESETS DATA)"
    echo "  remove [services]        Remove containers (keeps images)"
    echo "  logs [services]          Follow logs (Ctrl+C to exit)"
    echo "  ps [services]            Show container status"
    echo "  check                    Check what needs rebuilding"
    echo ""
    echo "Examples:"
    echo "  $0 build nlp_service              # Build NLP service for dev"
    echo "  $0 start                          # Start all services in dev mode"
    echo "  $0 start nlp_service file_service # Start specific services"
    echo "  $0 logs nlp_service               # View NLP service logs"
    echo "  $0 build-clean                    # Rebuild everything from scratch"
    echo ""
    echo "PDM Shortcuts:"
    echo "  pdm run dev-build [services]       # Same as: $0 build [services]"
    echo "  pdm run dev-start [services]       # Same as: $0 start-nobuild [services] (fast)"
    echo "  pdm run dev-build-start [services] # Same as: $0 start [services] (with rebuild)"
    echo "  pdm run dev-logs [services]        # Same as: $0 logs [services]"
}

# Main command routing
case "$1" in
    "build")
        build_dev "${@:2}"
        ;;
    "build-clean")
        build_clean_dev "${@:2}"
        ;;
    "build-deps-clean")
        echo_dev "Building shared DEPS image with --no-cache"
        ensure_deps_image "clean"
        echo_success "Dependency image built successfully"
        ;;
    "start")
        start_dev "${@:2}"
        ;;
    "start-nobuild")
        start_dev_nobuild "${@:2}"
        ;;
    "stop")
        stop_dev "${@:2}"
        ;;
    "restart")
        restart_dev "${@:2}"
        ;;
    "recreate")
        recreate_dev "${@:2}"
        ;;
    "recreate-db")
        recreate_db_dev "${@:2}"
        ;;
    "remove")
        remove_dev "${@:2}"
        ;;
    "logs")
        logs_dev "${@:2}"
        ;;
    "ps")
        ps_dev "${@:2}"
        ;;
    "check")
        check_changes
        ;;
    "help"|"--help"|"-h"|"")
        show_help
        ;;
    *)
        echo_error "Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
