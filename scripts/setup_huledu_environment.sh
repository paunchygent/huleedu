#!/usr/bin/env bash
# This script is intended to be run when setting up the HuleEdu development environment
# for OpenAI Codex agent work in a browser-based sandbox environment.
# It installs dependencies for the entire monorepo including all microservices.

set -e # Exit immediately if a command exits with a non-zero status.
set -o pipefail # The return value of a pipeline is the status of the last command to exit with a non-zero status, or zero if no command exited with a non-zero status.

# Optional: Uncomment for stricter error checking or debugging
# set -u # Treat unset variables as an error.
# set -x # Print commands and their arguments as they are executed.

NC='\033[0m' # No Color
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'

echo -e "${BLUE}--- Starting HuleEdu Microservice Environment Setup ---${NC}"
echo -e "${BLUE}This script sets up the complete HuleEdu monorepo for AI agent development${NC}"

# Navigate to the project directory within the container
# As per OpenAI Codex environment, the repository is cloned to /workspace/huledu-reboot
# This script is located in scripts/ so we need to go up one level to reach project root
PROJECT_DIR="/workspace/huledu-reboot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

if [ -d "$PROJECT_DIR" ]; then
  cd "$PROJECT_DIR"
  echo -e "${GREEN}Changed directory to $(pwd)${NC}"
else
  # If running locally, use the calculated project root
  if [ -d "$PROJECT_ROOT" ] && [ -f "$PROJECT_ROOT/pyproject.toml" ]; then
    cd "$PROJECT_ROOT"
    echo -e "${GREEN}Changed directory to $(pwd) (calculated from script location)${NC}"
  else
    echo -e "${YELLOW}Project directory $PROJECT_DIR not found. Assuming current directory is the project root.${NC}"
    # If the script is already in the project root (e.g. /workspace/huledu-reboot), this is fine.
    # If not, the following commands might fail or operate on the wrong directory.
  fi
fi 

# Verify we're in the correct project by checking for key files
if [ ! -f "pyproject.toml" ] || [ ! -d "services" ] || [ ! -d "common_core" ]; then
    echo -e "${RED}Error: This doesn't appear to be the HuleEdu project root.${NC}"
    echo -e "${RED}Expected files/directories: pyproject.toml, services/, common_core/${NC}"
    echo -e "${RED}Current directory: $(pwd)${NC}"
    echo -e "${RED}Directory contents:${NC}"
    ls -la
    exit 1
fi

echo -e "${GREEN}Confirmed HuleEdu project structure detected${NC}"

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
echo -e "${BLUE}This monorepo contains multiple microservices:${NC}"
echo -e "${BLUE}  • Batch Orchestration Service (services/batch_orchestrator_service)${NC}"
echo -e "${BLUE}  • Content Service (services/content_service)${NC}"
echo -e "${BLUE}  • Spell Checker Service (services/spellchecker_service)${NC}"
echo -e "${BLUE}  • Common Core Package (common_core)${NC}"
echo -e "${BLUE}  • Service Libraries (services/libs)${NC}"
echo -e "${YELLOW}  • Essay Service (services/essay_service) - [PLACEHOLDER - NOT YET IMPLEMENTED]${NC}"

# Install project dependencies (including development dependencies and all services)
echo -e "${BLUE}--- Installing HuleEdu Monorepo Dependencies ---${NC}"
echo -e "${BLUE}Installing monorepo tools and dev dependencies...${NC}"
pdm install -G monorepo-tools

echo -e "${BLUE}Installing all services in editable mode for development...${NC}"
pdm install -G dev

echo -e "${GREEN}--- HuleEdu Environment Setup Complete ---${NC}"
echo -e "${GREEN}All microservices are now installed in editable mode and ready for development.${NC}"
echo -e "${BLUE}Available PDM scripts:${NC}"
echo -e "${BLUE}  • pdm run format-all    - Format all code with Black and isort${NC}"
echo -e "${BLUE}  • pdm run lint-all      - Lint all code with flake8${NC}"
echo -e "${BLUE}  • pdm run typecheck-all - Type check all code with mypy${NC}"
echo -e "${BLUE}  • pdm run test-all      - Run all tests with pytest${NC}"
echo -e "${BLUE}  • pdm run docker-build  - Build Docker containers${NC}"
echo -e "${BLUE}  • pdm run docker-up     - Start services with Docker Compose${NC}"
echo -e "${BLUE}Individual service development:${NC}"
echo -e "${BLUE}  • pdm run dev-content   - Run content service in dev mode${NC}"
echo -e "${BLUE}  • pdm run dev-batch     - Run batch orchestrator service in dev mode${NC}"
echo -e "${BLUE}  • pdm run -p services/spellchecker_service start_worker - Start spell checker worker${NC}"

echo -e "${GREEN}Environment is ready for AI agent development work!${NC}"

exit 0 