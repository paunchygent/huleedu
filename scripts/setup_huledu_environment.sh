#!/usr/bin/env bash
# This script bootstraps the HuleEdu development environment for OpenAI Codex
# browser sandboxes (and local shells) by installing all monorepo dependencies.

set -euo pipefail # Fail fast on unset vars, non-zero exits, or pipeline issues.

# Optional: Uncomment for verbose debugging.
# set -x # Print commands and their arguments as they are executed.

NC='\033[0m' # No Color
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'

echo -e "${BLUE}--- Starting HuleEdu Microservice Environment Setup ---${NC}"
echo -e "${BLUE}Detecting project root for OpenAI Codex sandbox compatibility...${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_PARENT="$(dirname "$SCRIPT_DIR")"

is_repo_root() {
    local dir="$1"
    [[ -n "$dir" ]] || return 1
    [[ -d "$dir" ]] || return 1
    [[ -f "$dir/pyproject.toml" ]] || return 1
    [[ -d "$dir/services" ]] || return 1
    [[ -d "$dir/libs/common_core" ]] || return 1
    [[ -d "$dir/libs/huleedu_service_libs" ]] || return 1
}

print_structure_error() {
    echo -e "${RED}Error: Unable to locate the HuleEdu project root.${NC}"
    echo -e "${RED}Expected to find pyproject.toml, services/, and libs/common_core/.${NC}"
    echo -e "${RED}Current directory: $(pwd)${NC}"
    echo -e "${RED}Directory contents:${NC}"
    ls -la
}

find_repo_root() {
    local -a candidates=()

    # Explicit overrides (environment variables take priority)
    if [ -n "${HULEDU_REPO_ROOT:-}" ]; then candidates+=("$HULEDU_REPO_ROOT"); fi
    if [ -n "${PROJECT_DIR:-}" ]; then candidates+=("$PROJECT_DIR"); fi

    # Default Codex mount path (codex-universal maps repos to /workspace/<name>)
    local codex_default="/workspace/huledu-reboot"
    if [ -d "$codex_default" ]; then candidates+=("$codex_default"); fi

    # Generic Codex mapping for arbitrary repo names
    local codex_repo="/workspace/$(basename "$PROJECT_PARENT")"
    if [ -d "$codex_repo" ]; then candidates+=("$codex_repo"); fi

    # Git-based detection
    if command -v git >/dev/null 2>&1; then
        local git_root
        git_root="$(cd "$SCRIPT_DIR" && git rev-parse --show-toplevel 2>/dev/null || true)"
        if [ -n "$git_root" ]; then candidates+=("$git_root"); fi
    fi

    # Fall back to script parent and current working directory
    candidates+=("$PROJECT_PARENT" "$(pwd)")

    for dir in "${candidates[@]}"; do
        if is_repo_root "$dir"; then
            echo "$dir"
            return 0
        fi
    done

    return 1
}

if ! PROJECT_ROOT="$(find_repo_root)"; then
    print_structure_error
    exit 1
fi

cd "$PROJECT_ROOT"
echo -e "${GREEN}Changed directory to $(pwd)${NC}"
echo -e "${GREEN}Confirmed HuleEdu project structure detected${NC}"

# Ensure PDM caches/logs live inside the repo (Codex $HOME may be read-only)
PDM_HOME_DIR="${PDM_HOME:-$PROJECT_ROOT/.pdm}"
mkdir -p "$PDM_HOME_DIR"
export PDM_HOME="$PDM_HOME_DIR"

DEFAULT_PDM_LOG_DIR="${PDM_LOG_DIR:-$PDM_HOME/logs}"
mkdir -p "$DEFAULT_PDM_LOG_DIR"
export PDM_LOG_DIR="$DEFAULT_PDM_LOG_DIR"

DEFAULT_PDM_CACHE_DIR="${PDM_CACHE_DIR:-$PDM_HOME/cache}"
mkdir -p "$DEFAULT_PDM_CACHE_DIR"
export PDM_CACHE_DIR="$DEFAULT_PDM_CACHE_DIR"

DEFAULT_HISHEL_CACHE_DIR="${HISHEL_CACHE_DIR:-$DEFAULT_PDM_CACHE_DIR/hishel}"
mkdir -p "$DEFAULT_HISHEL_CACHE_DIR"
export HISHEL_CACHE_DIR="$DEFAULT_HISHEL_CACHE_DIR"

# Check if PDM is installed
if ! command -v pdm &> /dev/null; then
    echo -e "${YELLOW}PDM command could not be found. Attempting to install PDM...${NC}"
    if command -v python3 &> /dev/null && python3 -m pip --version &> /dev/null; then
        echo -e "${BLUE}Python 3 and pip found. Installing PDM using 'python3 -m pip install --user pdm'...${NC}"
        python3 -m pip install --user pdm
        # Ensure the user's local bin directory is in PATH
        # This is a common location for pip --user installs
        USER_LOCAL_BIN="$(python3 -m site --user-base)/bin"
        if [[ ":$PATH:" != *":$USER_LOCAL_BIN:"* ]]; then
            echo -e "${BLUE}Adding $USER_LOCAL_BIN to PATH for this session.${NC}"
            export PATH="$USER_LOCAL_BIN:$PATH"
        fi
        # Re-check if PDM is now available
        if ! command -v pdm &> /dev/null; then
            echo -e "${RED}PDM installation attempted, but 'pdm' command still not found.${NC}"
            echo -e "${YELLOW}Please check pip installation output and ensure $USER_LOCAL_BIN is correctly in PATH permanently if needed.${NC}"
            exit 1
        else
            echo -e "${GREEN}PDM installed successfully and is now available.${NC}"
        fi
    else
        echo -e "${RED}Python 3 or pip is not available. Cannot automatically install PDM.${NC}"
        echo -e "${YELLOW}Please ensure Python 3, pip, and PDM are correctly set up in your base environment.${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}PDM found. Version: $(pdm --version)${NC}"

# Display project information
echo -e "${BLUE}--- HuleEdu Monorepo Information ---${NC}"
echo -e "${BLUE}Key components detected:${NC}"
echo -e "${BLUE}  • Batch Orchestration Service (services/batch_orchestrator_service)${NC}"
echo -e "${BLUE}  • Content Service (services/content_service)${NC}"
echo -e "${BLUE}  • Spellchecker Service (services/spellchecker_service)${NC}"
echo -e "${BLUE}  • Common Core Library (libs/common_core)${NC}"
echo -e "${BLUE}  • Shared Service Libraries (libs/huleedu_service_libs)${NC}"

# Install project dependencies (including development dependencies and all services)
echo -e "${BLUE}--- Installing HuleEdu Monorepo Dependencies ---${NC}"
echo -e "${BLUE}Installing base dependencies plus monorepo tooling and dev extras...${NC}"
pdm install --group monorepo-tools --group dev

echo -e "${GREEN}--- HuleEdu Environment Setup Complete ---${NC}"
echo -e "${GREEN}All microservices are now installed in editable mode and ready for development.${NC}"
echo -e "${BLUE}Available PDM scripts:${NC}"
echo -e "${BLUE}  • pdm run format-all    - Format via Ruff (Rule 081/083)${NC}"
echo -e "${BLUE}  • pdm run lint-all      - Ruff lint across the monorepo${NC}"
echo -e "${BLUE}  • pdm run lint-fix      - Ruff autofix where possible${NC}"
echo -e "${BLUE}  • pdm run typecheck-all - Mypy from repo root (strict mode)${NC}"
echo -e "${BLUE}  • pdm run test-all      - Run pytest for the full suite${NC}"
echo -e "${BLUE}  • pdm run dev           - Entry point for dev containers (see scripts/dev.sh)${NC}"
echo -e "${BLUE}  • pdm run dev-start     - Start selected services without rebuild${NC}"
echo -e "${BLUE}  • pdm run dev-build-start - Build + start selected services${NC}"
echo -e "${BLUE}  • pdm run dev-logs      - Tail dev container logs${NC}"
echo -e "${BLUE}  • pdm run codex         - Launch Codex CLI with repo presets${NC}"

echo -e "${GREEN}Environment is ready for AI agent development work!${NC}"

exit 0 
