"""
Script to add 'from __future__ import annotations' to Python files.

This script will add the future import statement after the module docstring
and before any other imports in each specified Python file.
"""

from pathlib import Path

# List of files to process (relative to repository root)
FILES_TO_UPDATE = [
    # api_gateway_service
    "services/api_gateway_service/app/metrics.py",
    "services/api_gateway_service/app/di.py",
    "services/api_gateway_service/app/rate_limiter.py",
    "services/api_gateway_service/app/startup_setup.py",
    "services/api_gateway_service/app/main.py",
    "services/api_gateway_service/auth.py",
    "services/api_gateway_service/routers/batch_routes.py",
    "services/api_gateway_service/routers/class_routes.py",
    "services/api_gateway_service/routers/file_routes.py",
    "services/api_gateway_service/routers/status_routes.py",
    "services/api_gateway_service/routers/websocket_routes.py",
    "services/api_gateway_service/routers/health_routes.py",
    "services/api_gateway_service/tests/conftest.py",
    "services/api_gateway_service/tests/test_acl_transformers.py",
    "services/api_gateway_service/tests/test_status_routes.py",
    "services/api_gateway_service/tests/test_class_routes.py",

    # batch_conductor_service
    "services/batch_conductor_service/pipeline_definitions.py",
    "services/batch_conductor_service/pipeline_generator.py",
    "services/batch_conductor_service/tests/test_atomic_redis_operations.py",

    # batch_orchestrator_service
    "services/batch_orchestrator_service/implementations/utils.py",
    "services/batch_orchestrator_service/tests/unit/test_idempotency_outage.py",
    "services/batch_orchestrator_service/tests/unit/test_idempotency_basic.py",

    # class_management_service
    "services/class_management_service/metrics.py",
    "services/class_management_service/config.py",
    "services/class_management_service/app.py",
    "services/class_management_service/startup_setup.py",
    "services/class_management_service/implementations/event_publisher_impl.py",
    "services/class_management_service/tests/test_core_logic.py",

    # content_service
    "services/content_service/api/content_routes.py",
    "services/content_service/api/health_routes.py",

    # file_service
    "services/file_service/hypercorn_config.py",
    "services/file_service/tests/unit/test_empty_file_validation.py",

    # result_aggregator_service
    "services/result_aggregator_service/metrics.py",
    "services/result_aggregator_service/config.py",
    "services/result_aggregator_service/protocols.py",
    "services/result_aggregator_service/models_api.py",
    "services/result_aggregator_service/enums_db.py",
    "services/result_aggregator_service/di.py",
    "services/result_aggregator_service/models_db.py",
    "services/result_aggregator_service/app.py",
    "services/result_aggregator_service/kafka_consumer.py",
    "services/result_aggregator_service/api/query_routes.py",
    "services/result_aggregator_service/api/middleware.py",
    "services/result_aggregator_service/api/health_routes.py",
    "services/result_aggregator_service/startup_setup.py",
    "services/result_aggregator_service/implementations/aggregator_service_impl.py",
    "services/result_aggregator_service/implementations/batch_repository_postgres_impl.py",
    "services/result_aggregator_service/implementations/cache_manager_impl.py",
    "services/result_aggregator_service/implementations/security_impl.py",
    "services/result_aggregator_service/implementations/event_processor_impl.py",
    "services/result_aggregator_service/implementations/state_store_redis_impl.py",
    "services/result_aggregator_service/enums_api.py",
    "services/result_aggregator_service/tests/unit/test_cache_manager.py",
    "services/result_aggregator_service/tests/unit/test_aggregator_service.py",
    "services/result_aggregator_service/tests/unit/test_security_service.py",
    "services/result_aggregator_service/tests/unit/test_event_processor_impl.py",
    "services/result_aggregator_service/tests/integration/conftest.py",
    "services/result_aggregator_service/tests/integration/test_batch_repository_postgres.py",
    "services/result_aggregator_service/tests/integration/test_kafka_consumer_message_routing.py",
    "services/result_aggregator_service/tests/integration/test_kafka_consumer_idempotency.py",
    "services/result_aggregator_service/tests/integration/test_kafka_consumer_error_handling.py",
    "services/result_aggregator_service/tests/integration/test_api_endpoints.py",

    # spell_checker_service
    "services/spell_checker_service/spell_logic/l2_dictionary_loader.py",
    "services/spell_checker_service/tests/unit/test_spell_idempotency_basic.py",
    "services/spell_checker_service/tests/unit/test_spell_idempotency_outage.py",
    "services/spell_checker_service/tests/spell_logic/test_l2_dictionary_loader.py",
]

def add_future_import(file_path: str) -> bool:
    """Add future import to a single file if it doesn't already have it."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Skip if file already has the future import
        if any('from __future__ import annotations' in line for line in lines):
            print(f"Skipping (already has future import): {file_path}")
            return False

        new_lines = []
        in_docstring = False
        future_import_added = False

        for i, line in enumerate(lines):
            # Handle docstring
            if not in_docstring and line.strip().startswith('"""'):
                in_docstring = True
                new_lines.append(line)
                # Check if this is a single-line docstring
                if '"""' in line[3:]:
                    in_docstring = False
                continue
            elif in_docstring:
                new_lines.append(line)
                if '"""' in line:
                    in_docstring = False
                continue

            # Add future import after docstring and before other imports
            if not future_import_added and (line.strip().startswith('import ') or line.strip().startswith('from ')):
                new_lines.append('from __future__ import annotations\n\n')
                future_import_added = True
            elif not future_import_added and line.strip() == '':
                # If we hit an empty line after docstring, add the import here
                if i > 0 and any('"""' in l for l in lines[:i]):
                    new_lines.append('from __future__ import annotations\n\n')
                    future_import_added = True
                    new_lines.append(line)
                    continue

            new_lines.append(line)

        # If we got to the end without adding it, add at the top
        if not future_import_added:
            if not any('"""' in line for line in lines):
                # No docstring, add at the very top
                new_lines = ['from __future__ import annotations\n\n'] + new_lines
            else:
                # Has docstring, add after it
                for i, line in enumerate(new_lines):
                    if '"""' in line and not line.strip().startswith('"""'):
                        new_lines.insert(i + 1, 'from __future__ import annotations\n\n')
                        break

        # Write the file back
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

        print(f"Updated: {file_path}")
        return True

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

def main():
    """Main function to process all files."""
    repo_root = Path(__file__).parent.parent
    updated_count = 0

    for rel_path in FILES_TO_UPDATE:
        file_path = repo_root / rel_path
        if file_path.exists():
            if add_future_import(str(file_path)):
                updated_count += 1
        else:
            print(f"File not found: {file_path}")

    print(f"\nProcessing complete. Updated {updated_count} files.")

if __name__ == "__main__":
    main()
