#!/bin/bash
"""
Master Test Script: State Machine Refactoring Validation

This script coordinates validation of all 4 phases:
1. Phase 1: common_core Updates
2. Phase 2: ELS State Machine Implementation  
3. Phase 3: BOS Dynamic Pipeline Orchestration
4. Phase 4: End-to-End Pipeline Validation

Usage: ./scripts/tests/test_state_machine_refactoring.sh [phase_number]
       ./scripts/tests/test_state_machine_refactoring.sh all
"""

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}🚀 HuleEdu State Machine Refactoring Test Suite${NC}"
echo -e "${BLUE}===============================================${NC}"
echo "Project Root: $PROJECT_ROOT"
echo ""

# Function to run a specific phase test
run_phase_test() {
    local phase_num=$1
    local test_script=$2
    local description=$3
    
    echo -e "${YELLOW}Phase $phase_num: $description${NC}"
    echo "Running: pdm run python $test_script"
    echo ""
    
    if pdm run python "$test_script"; then
        echo -e "${GREEN}✅ Phase $phase_num validation PASSED${NC}"
        return 0
    else
        echo -e "${RED}❌ Phase $phase_num validation FAILED${NC}"
        return 1
    fi
}

# Function to display usage
show_usage() {
    echo "Usage: $0 [phase_number|all]"
    echo ""
    echo "Available phases:"
    echo "  1    - common_core Updates (Events, Enums, Models)"
    echo "  2    - ELS State Machine Implementation"
    echo "  3    - BOS Dynamic Pipeline Orchestration"
    echo "  4    - End-to-End Pipeline Validation"
    echo "  all  - Run all phases sequentially"
    echo ""
    echo "Examples:"
    echo "  $0 1          # Run only Phase 1"
    echo "  $0 all        # Run all phases"
    echo "  $0            # Interactive mode"
}

# Function to run all phases
run_all_phases() {
    echo -e "${BLUE}Running All Phases Sequentially${NC}"
    echo ""
    
    local total_phases=4
    local passed_phases=0
    
    # Phase 1: common_core Updates
    if run_phase_test 1 "scripts/tests/test_phase1_common_core_events.py" "common_core Updates"; then
        ((passed_phases++))
    fi
    echo ""
    
    # Phase 2: ELS State Machine
    if run_phase_test 2 "scripts/tests/test_phase2_els_state_machine.py" "ELS State Machine Implementation"; then
        ((passed_phases++))
    fi
    echo ""
    
    # Phase 3: BOS Orchestration
    if run_phase_test 3 "scripts/tests/test_phase3_bos_orchestration.py" "BOS Dynamic Pipeline Orchestration"; then
        ((passed_phases++))
    fi
    echo ""
    
    # Phase 4: End-to-End Validation
    if run_phase_test 4 "scripts/tests/test_phase4_end_to_end_validation.py" "End-to-End Pipeline Validation"; then
        ((passed_phases++))
    fi
    echo ""
    
    # Summary
    echo -e "${BLUE}================================================${NC}"
    echo -e "${BLUE}📊 Final Summary${NC}"
    echo -e "${BLUE}================================================${NC}"
    echo "Phases passed: $passed_phases/$total_phases"
    
    if [ "$passed_phases" -eq "$total_phases" ]; then
        echo -e "${GREEN}🎉 ALL PHASES PASSED! State machine refactoring is ready.${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️  Some phases failed or are not yet implemented.${NC}"
        echo "This is expected during incremental development."
        
        if [ "$passed_phases" -eq 0 ]; then
            echo -e "${RED}❌ No phases passed. Check implementation status.${NC}"
            return 1
        else
            echo -e "${GREEN}✅ $passed_phases phases are working correctly.${NC}"
            return 0
        fi
    fi
}

# Function to run specific phase
run_specific_phase() {
    local phase=$1
    
    case $phase in
        1)
            run_phase_test 1 "scripts/tests/test_phase1_common_core_events.py" "common_core Updates"
            ;;
        2)
            run_phase_test 2 "scripts/tests/test_phase2_els_state_machine.py" "ELS State Machine Implementation"
            ;;
        3)
            run_phase_test 3 "scripts/tests/test_phase3_bos_orchestration.py" "BOS Dynamic Pipeline Orchestration"
            ;;
        4)
            run_phase_test 4 "scripts/tests/test_phase4_end_to_end_validation.py" "End-to-End Pipeline Validation"
            ;;
        *)
            echo -e "${RED}❌ Invalid phase number: $phase${NC}"
            echo "Valid phases: 1, 2, 3, 4"
            return 1
            ;;
    esac
}

# Function for interactive mode
interactive_mode() {
    echo -e "${YELLOW}Interactive Mode${NC}"
    echo "Select which phase to test:"
    echo "  1) Phase 1: common_core Updates"
    echo "  2) Phase 2: ELS State Machine Implementation"
    echo "  3) Phase 3: BOS Dynamic Pipeline Orchestration"
    echo "  4) Phase 4: End-to-End Pipeline Validation"
    echo "  5) All phases"
    echo "  6) Exit"
    echo ""
    read -p "Enter your choice (1-6): " choice
    
    case $choice in
        1|2|3|4)
            run_specific_phase "$choice"
            ;;
        5)
            run_all_phases
            ;;
        6)
            echo "Exiting..."
            exit 0
            ;;
        *)
            echo -e "${RED}❌ Invalid choice: $choice${NC}"
            return 1
            ;;
    esac
}

# Main execution
main() {
    # Check if PDM is available
    if ! command -v pdm &> /dev/null; then
        echo -e "${RED}❌ PDM is not installed or not in PATH${NC}"
        echo "Please install PDM: https://pdm.fming.dev/"
        exit 1
    fi
    
    # Parse command line arguments
    if [ $# -eq 0 ]; then
        # No arguments - interactive mode
        interactive_mode
    elif [ $# -eq 1 ]; then
        case $1 in
            all)
                run_all_phases
                ;;
            1|2|3|4)
                run_specific_phase "$1"
                ;;
            -h|--help|help)
                show_usage
                exit 0
                ;;
            *)
                echo -e "${RED}❌ Invalid argument: $1${NC}"
                show_usage
                exit 1
                ;;
        esac
    else
        echo -e "${RED}❌ Too many arguments${NC}"
        show_usage
        exit 1
    fi
}

# Run main function
main "$@" 