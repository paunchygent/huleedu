#!/bin/bash

# HuleEdu Production Environment Script
# For PRODUCTION builds and operations (optimized, no debug)
# For development operations with hot-reload, use dev.sh
#
# IMPORTANT FOR AI ASSISTANTS:
# - This script manages PRODUCTION containers only
# - Uses docker-compose.yml only (no dev overrides)
# - Builds from Dockerfile with 'production' target
# - NO hot-reload - rebuild required for changes
# - Info logging only (LOG_LEVEL=INFO)
# - Optimized for performance
# - Use 'pdm run prod-*' commands for production
# - Use 'pdm run dev-*' commands for development

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo_prod() {
    echo -e "${BLUE}[PROD]${NC} $1"
}

# Build services for production with cache
build_prod() {
    local services="$1"
    echo_prod "Building for PRODUCTION with cache: ${services:-all services}"
    echo_info "Using Dockerfile with 'production' target"
    echo_info "Optimizations enabled, debug features disabled"

    docker-compose build --parallel $services

    echo_prod "Production build complete!"
}

# Clean build for production (no cache)
build_clean_prod() {
    local services="$1"
    echo_prod "Clean build for PRODUCTION (no cache): ${services:-all services}"
    echo_warn "This will take longer as all layers will be rebuilt"

    docker-compose build --no-cache --parallel $services

    echo_prod "Clean production build complete!"
}

# Start production environment
start_prod() {
    local services="$1"
    echo_prod "Starting PRODUCTION environment: ${services:-all services}"
    echo_info "Running optimized containers"
    echo_warn "No hot-reload - rebuild required for code changes"

    # Build first if needed
    echo_info "Checking for required builds..."
    docker-compose build --parallel $services

    # Then start
    echo_info "Starting containers..."
    docker-compose up -d $services

    echo_prod "Production environment running!"
    echo_info "View logs: pdm run prod-logs ${services}"
}

# Stop production containers
stop_prod() {
    local services="$1"
    echo_prod "Stopping PRODUCTION containers: ${services:-all}"

    docker-compose stop $services

    echo_prod "Production containers stopped"
}

# Restart production containers
restart_prod() {
    local services="$1"
    echo_prod "Restarting PRODUCTION containers: ${services:-all}"
    echo_warn "This performs a graceful restart"

    docker-compose restart $services

    echo_prod "Production containers restarted"
}

# Remove production containers (preserves images)
remove_prod() {
    local services="$1"
    echo_prod "Removing PRODUCTION containers: ${services:-all}"
    echo_warn "This will remove containers but preserve images"

    docker-compose rm -f $services

    echo_prod "Production containers removed"
}

# View production logs
logs_prod() {
    local services="$1"
    echo_prod "Following PRODUCTION logs: ${services:-all services}"
    echo_info "Press Ctrl+C to exit"

    docker-compose logs -f --tail=50 $services
}

# Health check for production
health_check() {
    echo_prod "Checking health of production services..."

    # List all running containers
    local running=$(docker-compose ps --services --filter "status=running")

    if [ -z "$running" ]; then
        echo_error "No services are running"
        exit 1
    fi

    echo_info "Running services:"
    for service in $running; do
        # Try to get health status if available
        local health=$(docker inspect huleedu_${service} 2>/dev/null | grep -o '"Status":"[^"]*"' | head -1 | cut -d'"' -f4)
        if [ -n "$health" ]; then
            if [ "$health" = "healthy" ]; then
                echo_info "  ✓ $service (healthy)"
            else
                echo_warn "  ! $service ($health)"
            fi
        else
            echo_info "  ? $service (no health check)"
        fi
    done
}

# Deploy production (build + start + verify)
deploy_prod() {
    local services="$1"
    echo_prod "Deploying PRODUCTION: ${services:-all services}"
    echo_info "This will build, start, and verify services"

    # Build
    echo_info "Step 1/3: Building services..."
    build_prod "$services"

    # Start
    echo_info "Step 2/3: Starting services..."
    docker-compose up -d $services

    # Give services time to initialize
    echo_info "Step 3/3: Waiting for services to stabilize..."
    sleep 5

    # Health check
    health_check

    echo_prod "Deployment complete!"
}

# Show help
show_help() {
    echo "HuleEdu Production Environment Script"
    echo ""
    echo "This script manages PRODUCTION containers (optimized, no debug)."
    echo "For development with hot-reload, use dev.sh"
    echo ""
    echo "Usage: $0 <command> [services]"
    echo ""
    echo "Commands:"
    echo "  build [services]         Build with cache (uses Dockerfile)"
    echo "  build-clean [services]   Build without cache"
    echo "  start [services]         Build if needed + start"
    echo "  stop [services]          Stop containers"
    echo "  restart [services]       Graceful restart"
    echo "  remove [services]        Remove containers (keeps images)"
    echo "  logs [services]          Follow logs (Ctrl+C to exit)"
    echo "  health                   Check service health"
    echo "  deploy [services]        Full deploy (build + start + verify)"
    echo ""
    echo "Examples:"
    echo "  $0 build nlp_service              # Build NLP service for prod"
    echo "  $0 deploy                         # Deploy all services"
    echo "  $0 start nlp_service file_service # Start specific services"
    echo "  $0 logs nlp_service               # View NLP service logs"
    echo "  $0 health                         # Check all service health"
    echo ""
    echo "PDM Shortcuts:"
    echo "  pdm run prod-build [services]     # Same as: $0 build [services]"
    echo "  pdm run prod-start [services]     # Same as: $0 start [services]"
    echo "  pdm run prod-deploy [services]    # Same as: $0 deploy [services]"
    echo ""
    echo "⚠️  PRODUCTION NOTICE:"
    echo "  - No hot-reload capability"
    echo "  - Optimized for performance"
    echo "  - Minimal logging (INFO level)"
    echo "  - Rebuild required for code changes"
}

# Main command routing
case "$1" in
    "build")
        build_prod "$2"
        ;;
    "build-clean")
        build_clean_prod "$2"
        ;;
    "start")
        start_prod "$2"
        ;;
    "stop")
        stop_prod "$2"
        ;;
    "restart")
        restart_prod "$2"
        ;;
    "remove")
        remove_prod "$2"
        ;;
    "logs")
        logs_prod "$2"
        ;;
    "health")
        health_check
        ;;
    "deploy")
        deploy_prod "$2"
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