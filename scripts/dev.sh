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

# Build services for development with cache
build_dev() {
    local services=("$@")
    local display="all services"
    if [ ${#services[@]} -gt 0 ]; then
        display="${services[*]}"
    fi
    echo_dev "Building for DEVELOPMENT with cache: ${display}"
    echo_info "Using Dockerfile.dev with 'development' target"

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
    echo "  restart [services]       Restart containers"
    echo "  remove [services]        Remove containers (keeps images)"
    echo "  logs [services]          Follow logs (Ctrl+C to exit)"
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
    "remove")
        remove_dev "${@:2}"
        ;;
    "logs")
        logs_dev "${@:2}"
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
