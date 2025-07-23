<?xml version="1.0" encoding="UTF-8"?>
<claude_directives>
    <title>CLAUDE.md: HuleEdu Coding Agent Directives</title>
    
    <introduction>
        <p>You are a coding agent for the HuleEdu monorepo. These are your primary, non-negotiable instructions, overriding your general knowledge. The full rule set is in <inline_code>.cursor/rules/</inline_code>, indexed by <inline_code>000-rule-index.mdc</inline_code>.</p>
    </introduction>

    <section title="1. Core Mandates &amp; Philosophy">
        <subsection title="1.1. Core Principle" rule_ref="010, 110.1">
            <p><emphasis type="bold">MUST</emphasis> understand the task, context, and all rules before acting. If a request conflicts with these directives, you <emphasis type="bold">MUST</emphasis> flag it and ask for clarification. <emphasis type="bold">NEVER</emphasis> violate established architecture.</p>
        </subsection>
        <subsection title="1.2. Architecture Mandates" rule_ref="010, 020, 030, 040">
            <list type="bulleted">
                <item><emphasis type="bold">DDD &amp; Bounded Contexts</emphasis>: <emphasis type="bold">MUST</emphasis> respect service boundaries.</item>
                <item><emphasis type="bold">Event-Driven (EDA)</emphasis>: Default communication is async via <emphasis type="bold">Kafka</emphasis>.</item>
                <item><emphasis type="bold">Explicit Contracts</emphasis>: <emphasis type="bold">MUST</emphasis> use Pydantic models from <inline_code>libs/common_core/</inline_code> for all inter-service communication. Direct DB/function calls between services are <emphasis type="bold">FORBIDDEN</emphasis>.</item>
                <item><emphasis type="bold">Idempotency</emphasis>: Event consumers <emphasis type="bold">MUST</emphasis> be idempotent.</item>
                <item><emphasis type="bold">Fixed Tech Stack</emphasis>: Python 3.11, Quart/FastAPI, PDM, Dishka, PostgreSQL. <emphasis type="bold">NO</emphasis> alternatives.</item>
            </list>
        </subsection>
    </section>

    <section title="2. Implementation &amp; Coding Standards">
        <subsection title="2.1. Python Coding Standards" rule_ref="050">
            <list type="bulleted">
                <item><emphasis type="bold">Typing</emphasis>: <emphasis type="bold">MUST</emphasis> use full PEP 484 type hints. Use <inline_code>from __future__ import annotations</inline_code>. Avoid <inline_code>typing.Any</inline_code>.</item>
                <item><emphasis type="bold">Docstrings</emphasis>: <emphasis type="bold">MUST</emphasis> use Google-style for all public members with Args/Returns/Raises sections.</item>
                <item><emphasis type="bold">Formatting</emphasis>: Adhere to <emphasis type="bold">Ruff</emphasis> with <inline_code>line-length=100</inline_code>.</item>
                <item><emphasis type="bold">File Size</emphasis>: <emphasis type="bold">MUST</emphasis> adhere to a 400 LoC limit. Propose refactoring for larger files.</item>
            </list>
        </subsection>
        <subsection title="2.2. Dependency Injection (DI)" rule_ref="042">
            <list type="bulleted">
                <item><emphasis type="bold">Protocols First</emphasis>: Business logic <emphasis type="bold">MUST</emphasis> depend on <inline_code>typing.Protocol</inline_code>, not concrete classes.</item>
                <item><emphasis type="bold">Dishka for DI</emphasis>: <emphasis type="bold">MUST</emphasis> use Dishka. Providers live in <inline_code>&lt;service&gt;/di.py</inline_code>.</item>
                <item>
                    <emphasis type="bold">DI Provider Pattern</emphasis>:
                    <code language="python"><![CDATA[
from __future__ import annotations
from dishka import Provider, Scope, provide
from huleedu_service_libs.clients import RedisClientProtocol
from .implementations import MyServiceImpl
from .protocols import MyServiceProtocol

class ServiceProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_redis(self, settings: Settings) -> RedisClientProtocol:
        # ... client creation and start() call ...
        pass

    @provide(scope=Scope.REQUEST)
    def provide_service(self, redis: RedisClientProtocol) -> MyServiceProtocol:
        return MyServiceImpl(redis_client=redis)
                    ]]></code>
                </item>
            </list>
        </subsection>
        <subsection title="2.3. Service Library Usage" rule_ref="020.11, 040">
            <p><emphasis type="bold">MUST</emphasis> use <inline_code>huleedu-service-libs</inline_code> for infrastructure.</p>
            <list type="bulleted">
                <item><emphasis type="bold">FORBIDDEN</emphasis>: Direct imports of <inline_code>aiokafka</inline_code>, <inline_code>redis.asyncio</inline_code>, <inline_code>logging</inline_code>.</item>
                <item><emphasis type="bold">REQUIRED</emphasis>: Use <inline_code>KafkaBus</inline_code>, <inline_code>RedisClient</inline_code>, and <inline_code>create_service_logger</inline_code>.</item>
                <item><emphasis type="bold">REQUIRED</emphasis>: Wrap all Kafka consumers with <inline_code>@idempotent_consumer</inline_code>.</item>
            </list>
        </subsection>
        <subsection title="2.4. Pydantic V2 Serialization" rule_ref="051">
            <p>For JSON serialization (especially for Kafka), <emphasis type="bold">MUST</emphasis> use <inline_code>model_dump(mode="json")</inline_code> to handle <inline_code>UUID</inline_code> and <inline_code>datetime</inline_code> correctly.</p>
            <code language="python"><![CDATA[
def serialize_event(envelope: EventEnvelope) -> bytes:
    """Serializes an EventEnvelope to JSON bytes for Kafka."""
    json_payload = envelope.model_dump(mode="json")
    return json.dumps(json_payload).encode("utf-8")
            ]]></code>
        </subsection>
        <subsection title="2.5. SQLAlchemy &amp; Database" rule_ref="053, 042">
            <list type="bulleted">
                <item><emphasis type="bold">Repository Pattern</emphasis>: All DB access is via a repository implementing a <inline_code>Protocol</inline_code>.</item>
                <item><emphasis type="bold">Session Management</emphasis>: Repository <emphasis type="bold">MUST</emphasis> manage its own <inline_code>async_sessionmaker</inline_code>.</item>
                <item><emphasis type="bold">Eager Loading</emphasis>: <emphasis type="bold">MUST</emphasis> use <inline_code>options(selectinload(...))</inline_code> to prevent <inline_code>DetachedInstanceError</inline_code>.</item>
            </list>
            <code language="python"><![CDATA[
class PostgreSQLRepositoryImpl(MyRepositoryProtocol):
    def __init__(self, engine: AsyncEngine):
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def get_class_with_students(self, class_id: UUID) -> UserClass | None:
        async with self._session_factory() as session:
            stmt = (
                select(UserClass)
                .where(UserClass.id == class_id)
                .options(selectinload(UserClass.students))
            )
            return (await session.execute(stmt)).scalar_one_or_none()
            ]]></code>
        </subsection>
        <subsection title="2.6. Import Resolution" rule_ref="055">
            <p><emphasis type="bold">MUST</emphasis> use full, absolute module paths for all intra-repository imports to prevent conflicts.</p>
            <code language="python"><![CDATA[
# CORRECT
from services.batch_orchestrator_service.protocols import BatchProcessingServiceProtocol

# INCORRECT
from protocols import BatchProcessingServiceProtocol
            ]]></code>
        </subsection>
    </section>
    
    <section title="3. Application &amp; Service Structure">
        <subsection title="3.1. HTTP Service Blueprint" rule_ref="015, 041">
             <p>HTTP services <emphasis type="bold">MUST</emphasis> use the Blueprint/Router pattern. <inline_code>app.py</inline_code>/<inline_code>main.py</inline_code> is for setup only (&lt;150 LoC); routes live in <inline_code>api/</inline_code> or <inline_code>routers/</inline_code>.</p>
        </subsection>
        <subsection title="3.2. Dockerization" rule_ref="084">
            <p>Dockerfiles <emphasis type="bold">MUST</emphasis> set <inline_code>ENV PYTHONPATH=/app</inline_code>. <emphasis type="bold">MUST</emphasis> use Docker Compose v2 syntax (<inline_code>docker compose</inline_code>).</p>
        </subsection>
    </section>

    <section title="4. Tooling &amp; Workflow">
        <subsection title="4.1. PDM is Law" rule_ref="081, 083">
            <p><emphasis type="bold">PDM</emphasis> is the sole dependency manager. Use <inline_code>pdm run &lt;script_name&gt;</inline_code> for all tasks. Let PDM resolve dependency versions.</p>
        </subsection>
        <subsection title="4.2. Testing" rule_ref="070">
            <list type="bulleted">
                <item>Tests and <inline_code>mypy</inline_code> <emphasis type="bold">MUST</emphasis> be run from the repository root.</item>
                <item>Mock dependencies at the <inline_code>Protocol</inline_code> boundary using DI.</item>
                <item>
                    <emphasis type="bold">Prometheus Metric Conflicts</emphasis>: <emphasis type="bold">MUST</emphasis> use a fixture to clear the Prometheus registry between tests.
                    <code language="python"><![CDATA[
# In tests/conftest.py
@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    """Clears the Prometheus registry before each test."""
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    yield
                    ]]></code>
                </item>
            </list>
        </subsection>
    </section>

    <section title="5. Your Interaction Protocol" rule_ref="110">
        <list type="numbered">
            <item><emphasis type="bold">State Mode</emphasis>: Begin by stating your mode: Planning, Coding, Testing, etc.</item>
            <item><emphasis type="bold">Plan First</emphasis>: Provide a numbered plan for non-trivial tasks.</item>
            <item><emphasis type="bold">Generate Compliant Code</emphasis>: All code <emphasis type="bold">MUST</emphasis> adhere to all rules, including docstrings and types.</item>
            <item><emphasis type="bold">Be Explicit</emphasis>: Use <inline_code>// ... existing code ...</inline_code> markers in file edits.</item>
            <item><emphasis type="bold">Cite Sources</emphasis>: Reference rule numbers when applicable (e.g., "per Rule 053...").</item>
        </list>
    </section>
</claude_directives>