T014 — ELS Repository and Service Results SRP/DDD Refactor (REVISED)

  Context

  The Essay Lifecycle Service has two large modules that violate SRP:
  - services/essay_lifecycle_service/implementations/essay_repository_postg
  res_impl.py (~1062 LoC)
  - services/essay_lifecycle_service/implementations/service_result_handler
  _impl.py (~858 LoC)

  Following our established patterns from Spellchecker and Result
  Aggregator services, we will split these into focused modules while
  maintaining flat implementation structure and consistent DI patterns.

  Goals

  - Enforce SRP within ELS persistence and event result handling layers
  - Preserve public interfaces: EssayRepositoryProtocol and
  ServiceResultHandler
  - Follow established service patterns (flat implementations directory, no
   nested structures)
  - Inject async_sessionmaker instead of creating engines in repositories
  - Maintain separation between thin events (ELS) and rich events (RAS) per
   dual-event pattern

  Non-Goals

  - No nested directory structures under implementations
  - No backward compatibility layers or legacy shims
  - No changes to event contracts or Kafka topics
  - No modification of the dual-event pattern

  End-State Architecture

  Repository Implementation (Flat Structure)

  services/essay_lifecycle_service/implementations/
  ├── essay_repository_postgres_impl.py    # Facade (~200 LoC)
  ├── essay_repository_queries.py          # Read/write operations (~400 
  LoC)
  ├── essay_repository_mappers.py          # DB↔domain mapping (~150 LoC)
  ├── essay_repository_idempotency.py      # Content idempotency & slot ops
   (~200 LoC)

  Service Result Handler Implementation (Flat Structure)

  services/essay_lifecycle_service/implementations/
  ├── service_result_handler_impl.py       # Facade (~150 LoC)
  ├── spellcheck_result_handler.py         # SpellcheckPhaseCompletedV1 
  handler (~200 LoC)
  ├── cj_result_handler.py                 # CJ assessment handler (~250 
  LoC)
  ├── nlp_result_handler.py                # NLP completion handler (~200 
  LoC)
  ├── state_transition_handler.py          # State machine operations (~150
   LoC)

  Implementation Details

  1. Repository Refactoring

  essay_repository_postgres_impl.py (Facade):
  class PostgreSQLEssayRepository(EssayRepositoryProtocol):
      """Facade for PostgreSQL essay repository."""

      def __init__(
          self,
          session_factory: async_sessionmaker,
          database_metrics: DatabaseMetrics | None = None,
      ):
          self.session_factory = session_factory
          self.database_metrics = database_metrics
          self.queries = EssayRepositoryQueries(session_factory)
          self.mappers = EssayRepositoryMappers()
          self.idempotency = EssayIdempotencyOperations(session_factory)

  Key Changes:
  - Remove engine creation from repository
  - Inject async_sessionmaker from DI
  - Delegate to specialized modules
  - Keep facade thin (~200 LoC)

  2. Service Result Handler Refactoring

  service_result_handler_impl.py (Facade):
  class DefaultServiceResultHandler(ServiceResultHandler):
      """Facade for service result handling."""

      def __init__(
          self,
          repository: EssayRepositoryProtocol,
          batch_coordinator: BatchCoordinationHandler,
          session_factory: async_sessionmaker,
      ):
          self.repository = repository
          self.batch_coordinator = batch_coordinator
          self.session_factory = session_factory

          # Delegate handlers
          self.spellcheck_handler = SpellcheckResultHandler(
              repository, batch_coordinator, session_factory
          )
          self.cj_handler = CJResultHandler(
              repository, batch_coordinator, session_factory
          )
          self.nlp_handler = NLPResultHandler(
              repository, batch_coordinator, session_factory
          )

  spellcheck_result_handler.py:
  """
  Handler for SpellcheckPhaseCompletedV1 (thin event) for state 
  transitions.
  Part of dual-event pattern where RAS handles rich SpellcheckResultV1.
  """
  class SpellcheckResultHandler:
      async def handle_spellcheck_phase_completed(
          self,
          essay_id: str,
          batch_id: str,
          status: EssayStatus,
          corrected_text_storage_id: str | None,
          error_code: str | None,
          correlation_id: UUID,
          confirm_idempotency: Callable | None = None,
      ) -> bool:
          # Existing logic from service_result_handler_impl.py lines 
  267-437

  3. DI Provider Updates

  services/essay_lifecycle_service/di.py:
  @provide(scope=Scope.APP)
  def provide_database_engine(self, settings: Settings) -> AsyncEngine:
      """Provide database engine."""
      return create_async_engine(
          settings.DATABASE_URL,
          echo=False,
          pool_size=settings.DATABASE_POOL_SIZE,
          max_overflow=settings.DATABASE_MAX_OVERFLOW,
      )

  @provide(scope=Scope.APP)
  def provide_session_factory(self, engine: AsyncEngine) -> 
  async_sessionmaker:
      """Provide async session factory."""
      return async_sessionmaker(engine, expire_on_commit=False)

  @provide(scope=Scope.APP)
  async def provide_essay_repository(
      self,
      session_factory: async_sessionmaker,
      database_metrics: DatabaseMetrics,
  ) -> EssayRepositoryProtocol:
      """Provide repository with injected session factory."""
      if settings.ENVIRONMENT == "testing":
          return MockEssayRepository()

      return PostgreSQLEssayRepository(session_factory, database_metrics)

  @provide(scope=Scope.APP)
  async def initialize_database_schema(
      self, engine: AsyncEngine, settings: Settings
  ) -> None:
      """Initialize database schema at startup."""
      if settings.ENVIRONMENT != "testing":
          async with engine.begin() as conn:
              await conn.run_sync(Base.metadata.create_all)

  Migration Plan

  Phase 1: Repository Refactoring

  1. Create new files: essay_repository_queries.py,
  essay_repository_mappers.py, essay_repository_idempotency.py
  2. Move code from essay_repository_postgres_impl.py to appropriate
  modules
  3. Update PostgreSQLEssayRepository to be a facade that delegates
  4. Update DI to inject session_factory instead of settings

  Phase 2: Service Result Handler Refactoring

  1. Create new files: spellcheck_result_handler.py, cj_result_handler.py,
  nlp_result_handler.py, state_transition_handler.py
  2. Move handler logic from service_result_handler_impl.py
  3. Update DefaultServiceResultHandler to delegate to new handlers
  4. Verify event routing in batch_command_handlers.py still works

  Phase 3: Validation

  1. Run pdm run lint and fix any issues
  2. Run pdm run typecheck-all and fix type errors
  3. Run pdm run test-all to ensure all tests pass
  4. Test with Docker: pdm run dev dev essay_lifecycle_service

  Acceptance Criteria

  ✅ Public protocols unchanged (EssayRepositoryProtocol,
  ServiceResultHandler)✅ Flat implementation structure (no
  subdirectories)✅ Repository uses injected session_factory, not
  self-created engine✅ Schema initialization happens in DI startup✅ All
  handler methods preserve exact signatures✅ Dual-event pattern preserved
  (thin events for ELS, rich for RAS)✅ All tests pass: pdm run test-all✅
  Linting passes: pdm run lint✅ Type checking passes: pdm run 
  typecheck-all
