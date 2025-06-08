# Why Testcontainers is a Superior Approach for Your Project

For your use case, Testcontainers offers several key advantages over managing `docker-compose` with a script:

1. **Granular Control & Efficiency:** Instead of `up`/`down` on an entire stack, you can programmatically start *only the specific containers needed for a given test or test module*. For a unit/integration test of the `EssayLifecycleService`, you only need to start a PostgreSQL container, not Kafka, the Content Service, and everything else. This is significantly faster.
2. **Dynamic Configuration:** Testcontainers automatically finds a free port on the host machine and provides you with the connection details. This eliminates hardcoded ports in your test configuration and prevents port conflicts during test runs.
3. **Reliable Lifecycle Management:** It integrates seamlessly with Pytest's fixture scopes (`function`, `module`, `session`). You can start a database once per test session, ensuring all tests run against a clean, known state without the overhead of container restarts.
4. **Clean, Ephemeral State:** The library is designed to provide ephemeral containers that are automatically cleaned up, guaranteeing that your tests run in a clean, isolated environment every time.

---

## How to Implement Testcontainers in Your Architecture

Here is a methodical guide to integrating Testcontainers into your project, complete with code examples that align with your existing structure.

### Step 1: Update Dependencies

First, ensure you have the necessary Testcontainers packages. You already have `testcontainers[postgres]`, but you'll want the Kafka-specific one as well.

**In `pyproject.toml`:**

```toml
[dependency-groups]
monorepo-tools = [
    # ... existing tools
    "testcontainers[postgres,kafka]", # Consolidate and add kafka
]

```

After updating, run `pdm install --group monorepo-tools` to lock and install the new dependencies.

#### Step 2: Create Reusable Container Fixtures

The best practice is to define your containers as session-scoped Pytest fixtures. You can place these in `tests/conftest.py` or a dedicated `tests/fixtures/containers.py` file.

Here’s how you would define fixtures for PostgreSQL and Kafka.

**In `tests/conftest.py`:**

```python
# tests/conftest.py

from __future__ import annotations
import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.kafka import KafkaContainer
from testcontainers.core.container import GenericContainer
from testcontainers.core.waiting_utils import wait_for_logs

@pytest.fixture(scope="session")
def postgres_container() -> PostgresContainer:
    """
    Session-scoped fixture to provide a running PostgreSQL container.

    Yields:
        PostgresContainer: The running container instance.
    """
    # 'with' statement ensures the container is stopped after the test session
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def kafka_container() -> KafkaContainer:
    """
    Session-scoped fixture to provide a running Kafka container.

    Yields:
        KafkaContainer: The running container instance.
    """
    with KafkaContainer(image="confluentinc/cp-kafka:7.6.0") as kafka:
        yield kafka
```

#### Step 3: Refactor an Integration Test to Use a Fixture

Now, you can refactor a test that depends on PostgreSQL, like one for your `PostgreSQLEssayRepository`, to use the new fixture. This test would no longer need the heavy `isolated_services` fixture.

**Example test for `EssayLifecycleService`:**

```python
# tests/functional/essay_lifecycle_service/test_repository.py

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import PostgreSQLEssayRepository
from services.essay_lifecycle_service.config import Settings
from testcontainers.postgres import PostgresContainer # For type hinting

@pytest.mark.asyncio
async def test_repository_can_create_and_get_essay_state(
    postgres_container: PostgresContainer, # Request the fixture
):
    """
    Test that the repository can correctly create and retrieve an essay state.
    """
    # Testcontainers provides the dynamic connection URL
    connection_url = postgres_container.get_connection_url(driver="asyncpg")
    
    # Override settings to use the test container's DB
    mock_settings = Settings(
        DATABASE_URL=connection_url, 
        ENVIRONMENT="testing"
    )

    repo = PostgreSQLEssayRepository(settings=mock_settings)
    await repo.initialize_db_schema() # Initialize schema in the test DB

    # --- ARRANGE ---
    essay_id = "test-essay-123"
    # ... (rest of your test logic)

    # --- ACT ---
    await repo.create_or_update_essay_state_for_slot_assignment(
        essay_id=essay_id,
        # ... other params
    )
    retrieved_state = await repo.get_essay_state(essay_id)

    # --- ASSERT ---
    assert retrieved_state is not None
    assert retrieved_state.essay_id == essay_id
```

#### Step 4: Handle Your Own Service Containers

For E2E tests where you need your own services running, you'll use `GenericContainer`. This requires your service's Docker image to be built first. You can add a `docker-build-ci` script to your `pyproject.toml` to ensure images are built before tests run.

Here is how you'd create a fixture for your `content_service`, making it dependent on the `postgres_container` fixture.

**In `tests/conftest.py`:**

```python
# Add to tests/conftest.py

@pytest.fixture(scope="session")
def content_service_container(postgres_container: PostgresContainer) -> GenericContainer:
    """
    Fixture to run the content_service Docker container for E2E tests.

    Depends on the postgres_container to get the database URL.

    Yields:
        GenericContainer: The running content_service container.
    """
    # Assumes the image 'content-service:latest' has been built
    # Use the connection URL from the postgres_container fixture
    db_url = postgres_container.get_connection_url(driver="asyncpg")

    # The container will be connected to the same network as its dependencies
    with GenericContainer("content-service:latest") as service:
        # Link this service to the postgres container's network
        service.with_network(postgres_container.get_network())
        # Set environment variables required by the service
        service.with_env("DATABASE_URL", db_url)
        service.with_env("ENVIRONMENT", "testing")
        # Use the network alias for the database host
        postgres_alias = postgres_container.get_network_aliases()[0]
        service.with_env("DB_HOST", postgres_alias)

        # Expose the port to the host for HTTP requests
        service.with_exposed_ports(8000)

        # Wait until the service is ready by polling for a log message
        wait_for_logs(service, r"Uvicorn running on http://0.0.0.0:8000")
        
        yield service
```
