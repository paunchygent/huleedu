#!/bin/bash

# HuleEdu Development Workflow Script
# Optimizes Docker builds and provides hot-reload development

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Function to build services with optimized caching
build_with_cache() {
    local services="$1"
    echo_info "Building services with cache optimization: $services"
    
    # First, build only dependency layers (these cache well)
    echo_info "Step 1: Building dependency layers..."
    docker-compose build --parallel $services
    
    echo_info "Build complete! Services: $services"
}

# Function to build single service for development  
build_dev_service() {
    local service="$1"
    echo_info "Building $service for development..."
    
    # Build development version
    docker-compose -f docker-compose.yml -f docker-compose.dev.yml build $service
    
    echo_info "Development build complete for $service"
}

# Function to start development environment
start_dev() {
    local services="$1"
    echo_info "Starting development environment with hot-reload..."
    
    # Use development compose with volume mounts
    docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d $services
    
    echo_info "Development environment started. Code changes will be auto-reloaded."
    echo_info "View logs with: docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f $services"
}

# Function to do incremental rebuild (only changed services)
incremental_build() {
    echo_info "Performing incremental build (detects changes automatically)..."
    
    # Build without --no-cache to use layer caching
    docker-compose build --parallel
    
    echo_info "Incremental build complete!"
}

# Function to clean build (equivalent to --no-cache but smarter)
clean_build() {
    local services="$1"
    echo_warn "Performing clean build (removes all cache)..."
    
    # Remove images first
    if [ -n "$services" ]; then
        docker-compose build --no-cache --parallel $services
    else
        docker-compose build --no-cache --parallel
    fi
    
    echo_info "Clean build complete!"
}

# Function to check what needs rebuilding
check_changes() {
    echo_info "Checking what services need rebuilding..."
    
    # This is a placeholder - you could implement more sophisticated change detection
    echo_info "Services that might need rebuilding based on recent changes:"
    
    # Check git changes in the last commit
    if git rev-parse --git-dir > /dev/null 2>&1; then
        local changed_files=$(git diff --name-only HEAD~1 HEAD)
        
        if echo "$changed_files" | grep -q "libs/"; then
            echo_warn "  → Shared libraries changed - most services may need rebuilding"
        fi
        
        for service_dir in services/*/; do
            service_name=$(basename "$service_dir")
            if echo "$changed_files" | grep -q "services/$service_name/"; then
                echo_warn "  → $service_name needs rebuilding"
            fi
        done
    else
        echo_warn "Not in a git repository - cannot detect changes automatically"
    fi
}

# Main command handling
case "$1" in
    "build")
        if [ "$2" = "clean" ]; then
            clean_build "$3"
        elif [ "$2" = "dev" ]; then
            build_dev_service "$3"
        else
            build_with_cache "$2"
        fi
        ;;
    "dev")
        start_dev "$2"
        ;;
    "incremental")
        incremental_build
        ;;
    "check")
        check_changes
        ;;
    "help"|*)
        echo "HuleEdu Development Workflow Script"
        echo ""
        echo "Usage: $0 <command> [options]"
        echo ""
        echo "Commands:"
        echo "  build [services]        - Build services with optimized caching"
        echo "  build clean [services]  - Clean build (no cache) for services"
        echo "  build dev [service]     - Build single service for development"
        echo "  dev [services]          - Start development environment with hot-reload"
        echo "  incremental             - Incremental build using cache"
        echo "  check                   - Check what services need rebuilding"
        echo "  help                    - Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0 build nlp_service batch_orchestrator_service"
        echo "  $0 build clean nlp_service"
        echo "  $0 dev nlp_service"
        echo "  $0 incremental"
        echo "  $0 check"
        ;;
esac