# Correlation ID Usage Analysis Report

## Statistics

- Total files with correlation_id: 102
- Optional parameters: 55
- None defaults: 49
- Conditional None assignments: 3
- UUID generation points: 330
- String conversions: 109
- None checks: 1

## Correlation ID Generation Points

These locations generate new correlation IDs:

### services/class_management_service/models_db.py
- Line 32: Column("class_id", UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE")),
- Line 33: Column("student_id", UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE")),
- Line 39: id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
- Line 66: id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
- Line 83: id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
- Line 117: id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
- Line 119: UUID(as_uuid=True), nullable=False, index=True, unique=True

### services/class_management_service/tests/test_api_integration.py
- Line 104: mock_class.id = uuid.uuid4()
- Line 128: mock_student.id = uuid.uuid4()
- Line 153: class_id = uuid.uuid4()
- Line 178: class_id = uuid.uuid4()
- Line 192: student_id = uuid.uuid4()
- Line 215: student_id = uuid.uuid4()
- Line 232: class_id = uuid.uuid4()
- Line 262: class_id = uuid.uuid4()
- Line 279: student_id = uuid.uuid4()
- Line 311: student_id = uuid.uuid4()
- Line 327: class_id = uuid.uuid4()
- Line 343: class_id = uuid.uuid4()
- Line 357: student_id = uuid.uuid4()
- Line 373: student_id = uuid.uuid4()

### services/class_management_service/api/student_routes.py
- Line 41: correlation_id = uuid.uuid4()
- Line 87: student_uuid = uuid.UUID(student_id)
- Line 146: student_uuid = uuid.UUID(student_id)
- Line 149: correlation_id = uuid.uuid4()
- Line 211: student_uuid = uuid.UUID(student_id)

### services/class_management_service/api/class_routes.py
- Line 41: correlation_id = uuid.uuid4()  # Generate correlation ID
- Line 76: class_uuid = uuid.UUID(class_id)
- Line 133: class_uuid = uuid.UUID(class_id)
- Line 136: correlation_id = uuid.uuid4()
- Line 198: class_uuid = uuid.UUID(class_id)

### services/class_management_service/implementations/class_repository_mock_impl.py
- Line 37: class_id = uuid.uuid4()
- Line 40: id=uuid.uuid4(),
- Line 79: student_id = uuid.uuid4()

### services/batch_conductor_service/implementations/pipeline_resolution_service_impl.py
- Line 185: event_id=uuid4(),

### services/essay_lifecycle_service/core_logic.py
- Line 17: return uuid4()

### services/essay_lifecycle_service/tests/test_redis_notifications.py
- Line 72: essay_id = str(uuid4())
- Line 75: correlation_id = uuid4()
- Line 106: essay_id = str(uuid4())
- Line 123: "essay_id": str(uuid4()),
- Line 126: "correlation_id": str(uuid4()),
- Line 148: essay_id = str(uuid4())
- Line 170: essay_id = str(uuid4())

### services/essay_lifecycle_service/tests/test_essay_repository_integration.py
- Line 61: unique_id = str(uuid.uuid4())[:8]  # Short unique suffix

### services/essay_lifecycle_service/tests/unit/test_future_services_command_handlers.py
- Line 34: return uuid4()

### services/essay_lifecycle_service/tests/unit/test_els_idempotency_integration.py
- Line 88: "event_id": str(uuid.uuid4()),
- Line 92: "correlation_id": str(uuid.uuid4()),
- Line 322: "event_id": str(uuid.uuid4()),  # Different UUID each time
- Line 326: "correlation_id": str(uuid.uuid4()),  # Different UUID each time

### services/essay_lifecycle_service/tests/unit/test_batch_phase_coordinator_impl.py
- Line 80: correlation_id = uuid4()
- Line 140: correlation_id = uuid4()
- Line 199: correlation_id = uuid4()
- Line 247: correlation_id = uuid4()
- Line 287: correlation_id = uuid4()
- Line 315: correlation_id = uuid4()
- Line 429: correlation_id = uuid4()

### services/essay_lifecycle_service/tests/unit/test_cj_assessment_command_handler.py
- Line 96: return uuid4()

### services/essay_lifecycle_service/tests/unit/test_service_result_handler_impl.py
- Line 105: correlation_id = uuid4()
- Line 150: correlation_id = uuid4()
- Line 186: correlation_id = uuid4()
- Line 210: correlation_id = uuid4()
- Line 260: correlation_id = uuid4()
- Line 301: correlation_id = uuid4()
- Line 322: correlation_id = uuid4()
- Line 361: correlation_id = uuid4()

### services/essay_lifecycle_service/tests/unit/test_spellcheck_command_handler.py
- Line 95: return uuid4()

### services/essay_lifecycle_service/tests/unit/test_validation_event_consumer.py
- Line 45: correlation_id=uuid4(),
- Line 54: event_id=uuid4(),
- Line 152: correlation_id = uuid4()
- Line 175: event_id=uuid4(),
- Line 226: event_id=uuid4(),
- Line 251: event_id=uuid4(),
- Line 300: event_id=uuid4(),
- Line 318: event_id=uuid4(),

### services/essay_lifecycle_service/tests/unit/test_batch_command_integration.py
- Line 53: correlation_id = uuid4()
- Line 93: correlation_id = uuid4()

### services/essay_lifecycle_service/tests/unit/test_batch_command_handler_impl.py
- Line 94: return uuid4()

### services/essay_lifecycle_service/tests/unit/test_batch_tracker_validation_enhanced.py
- Line 65: correlation_id=uuid4(),
- Line 328: correlation_id = uuid4()

### services/essay_lifecycle_service/implementations/event_publisher.py
- Line 68: correlation_id=correlation_id or uuid4(),
- Line 174: correlation_id=correlation_id or uuid4(),
- Line 220: correlation_id=correlation_id or uuid4(),
- Line 261: correlation_id=correlation_id or uuid4(),
- Line 291: correlation_id=correlation_id or uuid4(),
- Line 321: correlation_id=correlation_id or uuid4(),

### services/batch_orchestrator_service/tests/test_nlp_initiator_impl.py
- Line 73: return uuid.uuid4()

### services/batch_orchestrator_service/tests/test_ai_feedback_initiator_impl.py
- Line 75: return uuid.uuid4()

### services/batch_orchestrator_service/tests/test_bos_pipeline_orchestration.py
- Line 173: batch_id = str(uuid4())
- Line 174: correlation_id = uuid4()
- Line 179: essay_id=str(uuid4()),
- Line 183: essay_id=str(uuid4()),

### services/batch_orchestrator_service/tests/unit/test_idempotency_outage.py
- Line 96: batch_id = str(uuid.uuid4())
- Line 97: correlation_id = str(uuid.uuid4())
- Line 99: "event_id": str(uuid.uuid4()),

### services/batch_orchestrator_service/tests/unit/test_idempotency_basic.py
- Line 97: batch_id = str(uuid.uuid4())
- Line 98: correlation_id = str(uuid.uuid4())
- Line 100: "event_id": str(uuid.uuid4()),
- Line 132: batch_id = str(uuid.uuid4())
- Line 133: correlation_id = str(uuid.uuid4())
- Line 137: "event_id": str(uuid.uuid4()),

### services/batch_orchestrator_service/api/batch_routes.py
- Line 42: correlation_id = uuid.uuid4()
- Line 275: correlation_id=str(correlation_id) if correlation_id else str(uuid.uuid4()),

### services/batch_orchestrator_service/implementations/batch_processing_service_impl.py
- Line 52: batch_id = str(uuid.uuid4())
- Line 57: str(uuid.uuid4()) for _ in range(registration_data.expected_essay_count)

### services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py
- Line 254: correlation_uuid = UUID(correlation_id) if correlation_id else None
- Line 403: correlation_uuid = UUID(correlation_id) if correlation_id else None

### services/libs/huleedu_service_libs/tests/test_idempotency.py
- Line 126: "event_id": str(uuid.uuid4()),
- Line 130: "correlation_id": str(uuid.uuid4()),
- Line 318: "event_id": str(uuid.uuid4()),  # Different UUID each time
- Line 322: "correlation_id": str(uuid.uuid4()),  # Different UUID each time

### services/content_service/implementations/filesystem_content_store.py
- Line 42: content_id = uuid.uuid4().hex

### services/api_gateway_service/routers/status_routes.py
- Line 38: correlation_id = getattr(request.state, "correlation_id", None) or str(uuid4())

### services/api_gateway_service/routers/batch_routes.py
- Line 73: correlation_id = uuid4()

### services/result_aggregator_service/tests/unit/test_event_processor_impl.py
- Line 135: batch_id = str(uuid4())
- Line 136: user_id = str(uuid4())
- Line 160: event_id=uuid4(),
- Line 185: batch_id = str(uuid4())
- Line 186: user_id = str(uuid4())
- Line 210: event_id=uuid4(),
- Line 238: batch_id = str(uuid4())
- Line 239: user_id = str(uuid4())
- Line 262: event_id=uuid4(),
- Line 288: batch_id = str(uuid4())
- Line 300: correlation_id=uuid4(),
- Line 304: event_id=uuid4(),
- Line 332: batch_id = str(uuid4())
- Line 343: correlation_id=uuid4(),
- Line 347: event_id=uuid4(),
- Line 375: batch_id = str(uuid4())
- Line 383: correlation_id=uuid4(),
- Line 387: event_id=uuid4(),
- Line 413: batch_id = str(uuid4())
- Line 423: correlation_id=uuid4(),
- Line 427: event_id=uuid4(),
- Line 453: essay_id = str(uuid4())
- Line 454: batch_id = str(uuid4())
- Line 455: storage_id = str(uuid4())
- Line 487: event_id=uuid4(),
- Line 517: essay_id = str(uuid4())
- Line 518: batch_id = str(uuid4())
- Line 542: event_id=uuid4(),
- Line 571: essay_id = str(uuid4())
- Line 572: batch_id = str(uuid4())
- Line 597: event_id=uuid4(),
- Line 640: event_id=uuid4(),
- Line 658: entity_id=str(uuid4()),
- Line 678: event_id=uuid4(),
- Line 702: batch_id = str(uuid4())
- Line 703: essay1_id = str(uuid4())
- Line 704: essay2_id = str(uuid4())
- Line 719: cj_assessment_job_id=str(uuid4()),
- Line 737: event_id=uuid4(),
- Line 785: batch_id = str(uuid4())
- Line 786: essay1_id = str(uuid4())
- Line 801: cj_assessment_job_id=str(uuid4()),
- Line 819: event_id=uuid4(),
- Line 849: batch_id = str(uuid4())
- Line 864: cj_assessment_job_id=str(uuid4()),
- Line 871: event_id=uuid4(),
- Line 894: batch_id = str(uuid4())
- Line 909: cj_assessment_job_id=str(uuid4()),
- Line 912: "els_essay_id": str(uuid4()),
- Line 922: event_id=uuid4(),

### services/result_aggregator_service/tests/integration/test_kafka_consumer_message_routing.py
- Line 44: batch_id: str = str(uuid4())
- Line 45: user_id: str = str(uuid4())
- Line 63: event_id=uuid4(),
- Line 67: correlation_id=uuid4(),
- Line 93: essay_id: str = str(uuid4())
- Line 94: batch_id: str = str(uuid4())
- Line 115: event_id=uuid4(),
- Line 119: correlation_id=uuid4(),
- Line 144: batch_id: str = str(uuid4())
- Line 166: event_id=uuid4(),
- Line 170: correlation_id=uuid4(),
- Line 195: batch_id: str = str(uuid4())
- Line 206: correlation_id=uuid4(),
- Line 210: event_id=uuid4(),
- Line 214: correlation_id=uuid4(),
- Line 241: "event_id": str(uuid4()),

### services/result_aggregator_service/tests/integration/test_kafka_consumer_idempotency.py
- Line 34: batch_id: str = str(uuid4())
- Line 59: batch_id: str = str(uuid4())
- Line 87: batch_id: str = str(uuid4())
- Line 114: batch_id: str = str(uuid4())
- Line 149: batch_id1: str = str(uuid4())
- Line 150: batch_id2: str = str(uuid4())
- Line 185: user_id=str(uuid4()),
- Line 196: event_id=uuid4(),
- Line 200: correlation_id=uuid4(),

### services/result_aggregator_service/tests/integration/test_kafka_consumer_error_handling.py
- Line 99: "event_id": str(uuid4()),
- Line 105: "batch_id": str(uuid4()),
- Line 138: batch_id1 = str(uuid4())
- Line 139: batch_id2 = str(uuid4())
- Line 149: user_id=str(uuid4()),
- Line 158: event_id=uuid4(),
- Line 162: correlation_id=uuid4(),
- Line 189: entity_id=str(uuid4()),
- Line 207: event_id=uuid4(),
- Line 211: correlation_id=uuid4(),

### services/result_aggregator_service/api/query_routes.py
- Line 48: g.correlation_id = request.headers.get("X-Correlation-ID", str(uuid4()))

### services/cj_assessment_service/event_processor.py
- Line 242: correlation_id if isinstance(correlation_id, UUID) else UUID(str(correlation_id))
- Line 320: correlation_id if isinstance(correlation_id, UUID) else UUID(str(correlation_id))

### services/cj_assessment_service/tests/conftest.py
- Line 60: return str(uuid4())
- Line 66: return str(uuid4())
- Line 72: return str(uuid4())
- Line 167: correlation_id=uuid4(),
- Line 180: correlation_id=uuid4(),
- Line 295: {"els_essay_id": str(uuid4()), "rank": 1, "score": 0.85},
- Line 296: {"els_essay_id": str(uuid4()), "rank": 2, "score": 0.72},

### services/cj_assessment_service/tests/unit/test_cj_idempotency_basic.py
- Line 51: batch_id = str(uuid.uuid4())
- Line 52: essay1_id = str(uuid.uuid4())
- Line 53: essay2_id = str(uuid.uuid4())
- Line 54: storage1_id = str(uuid.uuid4())
- Line 55: storage2_id = str(uuid.uuid4())
- Line 57: "event_id": str(uuid.uuid4()),
- Line 61: "correlation_id": str(uuid.uuid4()),
- Line 230: shared_event_id = str(uuid.uuid4())
- Line 236: "correlation_id": str(uuid.uuid4()),
- Line 245: "correlation_id": str(uuid.uuid4()),

### services/cj_assessment_service/tests/unit/test_cj_idempotency_outage.py
- Line 47: batch_id = str(uuid.uuid4())
- Line 48: essay1_id = str(uuid.uuid4())
- Line 49: essay2_id = str(uuid.uuid4())
- Line 50: storage1_id = str(uuid.uuid4())
- Line 51: storage2_id = str(uuid.uuid4())
- Line 53: "event_id": str(uuid.uuid4()),
- Line 57: "correlation_id": str(uuid.uuid4()),

### services/cj_assessment_service/tests/unit/test_cj_idempotency_failures.py
- Line 46: batch_id = str(uuid.uuid4())
- Line 47: essay1_id = str(uuid.uuid4())
- Line 48: essay2_id = str(uuid.uuid4())
- Line 49: storage1_id = str(uuid.uuid4())
- Line 50: storage2_id = str(uuid.uuid4())
- Line 52: "event_id": str(uuid.uuid4()),
- Line 56: "correlation_id": str(uuid.uuid4()),

### services/spell_checker_service/models_db.py
- Line 55: UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
- Line 57: batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
- Line 58: essay_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
- Line 103: UUID(as_uuid=True), ForeignKey("spellcheck_jobs.job_id", ondelete="CASCADE")

### services/spell_checker_service/tests/conftest.py
- Line 78: return str(uuid4())
- Line 84: return str(uuid4())
- Line 102: return EntityReference(entity_id=sample_essay_id, entity_type="essay", parent_id=str(uuid4()))
- Line 140: correlation_id=uuid4(),

### services/spell_checker_service/tests/test_repository_postgres.py
- Line 88: batch_id = uuid4()
- Line 89: essay_id = uuid4()
- Line 102: job_id = await repo.create_job(batch_id=uuid4(), essay_id=uuid4())
- Line 102: job_id = await repo.create_job(batch_id=uuid4(), essay_id=uuid4())
- Line 112: job_id = await repo.create_job(batch_id=uuid4(), essay_id=uuid4())
- Line 112: job_id = await repo.create_job(batch_id=uuid4(), essay_id=uuid4())

### services/spell_checker_service/tests/test_contract_compliance.py
- Line 167: UUID(request_envelope_dict["correlation_id"])

### services/spell_checker_service/tests/test_di_container.py
- Line 57: await repo.create_job(batch_id=uuid.uuid4(), essay_id=uuid.uuid4())
- Line 57: await repo.create_job(batch_id=uuid.uuid4(), essay_id=uuid.uuid4())

### services/spell_checker_service/tests/unit/test_spell_idempotency_basic.py
- Line 160: shared_event_id = str(uuid.uuid4())
- Line 166: "correlation_id": str(uuid.uuid4()),
- Line 174: "correlation_id": str(uuid.uuid4()),

### services/spell_checker_service/tests/unit/test_kafka_consumer_integration.py
- Line 61: essay_id = str(uuid.uuid4())
- Line 62: correlation_id = str(uuid.uuid4())
- Line 65: "event_id": str(uuid.uuid4()),

### services/spell_checker_service/tests/unit/spell_idempotency_test_utils.py
- Line 84: essay_id = str(uuid.uuid4())
- Line 85: correlation_id = str(uuid.uuid4())
- Line 88: "event_id": str(uuid.uuid4()),

### services/spell_checker_service/alembic/versions/20250630_0001_initial_schema.py
- Line 25: sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),
- Line 26: sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
- Line 27: sa.Column("essay_id", postgresql.UUID(as_uuid=True), nullable=False),
- Line 46: sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spellcheck_jobs.job_id", ondelete="CASCADE"), nullable=False),

### services/spell_checker_service/implementations/spell_repository_postgres_impl.py
- Line 86: new_job_id = uuid.uuid4()

### services/file_service/tests/unit/test_core_logic_validation_failures.py
- Line 44: correlation_id = uuid.uuid4()
- Line 116: correlation_id = uuid.uuid4()
- Line 173: correlation_id = uuid.uuid4()
- Line 230: correlation_id = uuid.uuid4()
- Line 288: correlation_id = uuid.uuid4()

### services/file_service/tests/unit/test_core_logic_validation_errors.py
- Line 40: correlation_id = uuid.uuid4()
- Line 92: correlation_id = uuid.uuid4()

### services/file_service/tests/unit/test_core_logic_raw_storage.py
- Line 26: batch_id = str(uuid.uuid4())
- Line 29: correlation_id = uuid.uuid4()
- Line 80: batch_id = str(uuid.uuid4())
- Line 83: correlation_id = uuid.uuid4()
- Line 127: batch_id = str(uuid.uuid4())
- Line 130: correlation_id = uuid.uuid4()
- Line 179: batch_id = str(uuid.uuid4())
- Line 182: correlation_id = uuid.uuid4()

### services/file_service/tests/unit/test_empty_file_validation.py
- Line 36: correlation_id = uuid.uuid4()
- Line 114: correlation_id = uuid.uuid4()
- Line 174: correlation_id = uuid.uuid4()

### services/file_service/tests/unit/test_file_routes_validation.py
- Line 254: uuid.UUID(data["correlation_id"])  # Should not raise exception
- Line 314: uuid.UUID(data["correlation_id"])  # Should not raise exception
- Line 385: uuid.UUID(data["correlation_id"])  # Should not raise exception

### services/file_service/tests/unit/test_event_publisher_file_management.py
- Line 58: correlation_id = uuid.uuid4()
- Line 150: correlation_id = uuid.uuid4()

### services/file_service/tests/unit/test_core_logic_validation_success.py
- Line 42: correlation_id = uuid.uuid4()
- Line 121: correlation_id = uuid.uuid4()

### services/file_service/api/file_routes.py
- Line 77: main_correlation_id = uuid.UUID(correlation_id_header)
- Line 84: main_correlation_id = uuid.uuid4()
- Line 86: main_correlation_id = uuid.uuid4()
- Line 216: main_correlation_id = uuid.UUID(correlation_id_header)
- Line 223: main_correlation_id = uuid.uuid4()
- Line 225: main_correlation_id = uuid.uuid4()
- Line 238: essay_id = str(uuid.uuid4())  # Generate essay_id for each file
- Line 348: correlation_id = uuid.UUID(correlation_id_header)
- Line 355: correlation_id = uuid.uuid4()
- Line 357: correlation_id = uuid.uuid4()

### common_core/tests/test_event_utils.py
- Line 25: "event_id": str(uuid4()),  # Different each time
- Line 32: event1["event_id"] = str(uuid4())
- Line 36: event2["event_id"] = str(uuid4())  # Different UUID
- Line 55: "event_id": str(uuid4()),
- Line 60: "event_id": str(uuid4()),
- Line 78: "event_id": str(uuid4()),
- Line 83: "event_id": str(uuid4()),
- Line 128: event = {"data": {}, "event_id": str(uuid4()), "source_service": "test_service"}
- Line 143: "event_id": str(uuid4()),
- Line 182: "event_id": str(uuid4()),
- Line 186: "correlation_id": str(uuid4()),
- Line 215: correlation_id = str(uuid4())
- Line 217: "event_id": str(uuid4()),
- Line 234: "event_id": str(uuid4()),

### common_core/tests/unit/test_class_events.py
- Line 46: correlation_id = uuid4()
- Line 67: correlation_id = uuid4()
- Line 144: correlation_id = uuid4()
- Line 169: correlation_id = uuid4()
- Line 262: correlation_id = uuid4()
- Line 308: correlation_id = uuid4()

### common_core/tests/unit/test_file_management_events.py
- Line 57: correlation_id = uuid4()
- Line 96: correlation_id = uuid4()
- Line 199: correlation_id = uuid4()
- Line 220: correlation_id = uuid4()
- Line 247: correlation_id = uuid4()
- Line 292: correlation_id = uuid4()
- Line 313: correlation_id = uuid4()
- Line 340: correlation_id = uuid4()

### common_core/tests/unit/test_file_events.py
- Line 44: correlation_id = uuid4()
- Line 84: correlation_id = uuid4()
- Line 106: correlation_id = uuid4()
- Line 245: correlation_id = uuid4()

## Test Files Requiring Updates

- services/class_management_service/tests/test_api_integration.py
- services/essay_lifecycle_service/tests/test_redis_notifications.py
- services/essay_lifecycle_service/tests/test_essay_repository_integration.py
- services/essay_lifecycle_service/tests/unit/test_future_services_command_handlers.py
- services/essay_lifecycle_service/tests/unit/test_els_idempotency_integration.py
- services/essay_lifecycle_service/tests/unit/test_batch_phase_coordinator_impl.py
- services/essay_lifecycle_service/tests/unit/test_cj_assessment_command_handler.py
- services/essay_lifecycle_service/tests/unit/test_service_result_handler_impl.py
- services/essay_lifecycle_service/tests/unit/test_spellcheck_command_handler.py
- services/essay_lifecycle_service/tests/unit/test_validation_event_consumer.py
- services/essay_lifecycle_service/tests/unit/test_batch_command_integration.py
- services/essay_lifecycle_service/tests/unit/test_batch_command_handler_impl.py
- services/essay_lifecycle_service/tests/unit/test_batch_tracker_validation_enhanced.py
- services/batch_orchestrator_service/tests/test_nlp_initiator_impl.py
- services/batch_orchestrator_service/tests/test_ai_feedback_initiator_impl.py
- services/batch_orchestrator_service/tests/test_bos_pipeline_orchestration.py
- services/batch_orchestrator_service/tests/unit/test_idempotency_outage.py
- services/batch_orchestrator_service/tests/unit/test_idempotency_basic.py
- services/libs/huleedu_service_libs/tests/test_idempotency.py
- services/result_aggregator_service/tests/unit/test_event_processor_impl.py
- services/result_aggregator_service/tests/integration/test_kafka_consumer_message_routing.py
- services/result_aggregator_service/tests/integration/test_kafka_consumer_idempotency.py
- services/result_aggregator_service/tests/integration/test_kafka_consumer_error_handling.py
- services/cj_assessment_service/tests/conftest.py
- services/cj_assessment_service/tests/unit/test_cj_idempotency_basic.py
- services/cj_assessment_service/tests/unit/test_cj_idempotency_outage.py
- services/cj_assessment_service/tests/unit/test_cj_idempotency_failures.py
- services/cj_assessment_service/tests/unit/mocks.py
- services/spell_checker_service/tests/conftest.py
- services/spell_checker_service/tests/test_repository_postgres.py
- services/spell_checker_service/tests/test_contract_compliance.py
- services/spell_checker_service/tests/test_di_container.py
- services/spell_checker_service/tests/unit/test_spell_idempotency_basic.py
- services/spell_checker_service/tests/unit/test_kafka_consumer_integration.py
- services/spell_checker_service/tests/unit/spell_idempotency_test_utils.py
- services/file_service/tests/unit/test_core_logic_validation_failures.py
- services/file_service/tests/unit/test_core_logic_validation_errors.py
- services/file_service/tests/unit/test_core_logic_raw_storage.py
- services/file_service/tests/unit/test_empty_file_validation.py
- services/file_service/tests/unit/test_file_routes_validation.py
- services/file_service/tests/unit/test_event_publisher_file_management.py
- services/file_service/tests/unit/test_core_logic_validation_success.py
- common_core/tests/test_event_utils.py
- common_core/tests/unit/test_class_events.py
- common_core/tests/unit/test_file_management_events.py
- common_core/tests/unit/test_file_events.py

## Detailed Findings by Pattern

### Optional correlation_id parameters

**services/essay_lifecycle_service/protocols.py**
  - Line 108: `self, essay_ref: EntityReference, status: EssayStatus, correlation_id: UUID | None = None`

**services/essay_lifecycle_service/app.py**
  - Line 44: `def __init__(self, error: str, detail: str | None = None, correlation_id: str | None = None):`

**services/essay_lifecycle_service/api/essay_routes.py**
  - Line 51: `correlation_id: str | None = None`

**services/essay_lifecycle_service/api/batch_routes.py**
  - Line 44: `correlation_id: str | None = None`

**services/essay_lifecycle_service/implementations/service_result_handler_impl.py**
  - Line 67: `correlation_id: UUID | None = None,`
  - Line 236: `correlation_id: UUID | None = None,`
  - Line 343: `correlation_id: UUID | None = None,`

**services/essay_lifecycle_service/implementations/future_services_command_handlers.py**
  - Line 47: `self, command_data: BatchServiceNLPInitiateCommandDataV1, correlation_id: UUID | None = None`
  - Line 56: `correlation_id: UUID | None = None,`

**services/essay_lifecycle_service/implementations/batch_command_handler_impl.py**
  - Line 57: `correlation_id: UUID | None = None,`
  - Line 65: `self, command_data: BatchServiceNLPInitiateCommandDataV1, correlation_id: UUID | None = None`
  - Line 75: `correlation_id: UUID | None = None,`
  - Line 85: `correlation_id: UUID | None = None,`

**services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py**
  - Line 99: `correlation_id: UUID | None = None,`
  - Line 228: `correlation_id: UUID | None = None,`

**services/essay_lifecycle_service/implementations/spellcheck_command_handler.py**
  - Line 49: `correlation_id: UUID | None = None,`

**services/essay_lifecycle_service/implementations/event_publisher.py**
  - Line 44: `self, essay_ref: EntityReference, status: EssayStatus, correlation_id: UUID | None = None`
  - Line 90: `correlation_id: UUID | None = None,`
  - Line 148: `correlation_id: UUID | None = None,`
  - Line 195: `correlation_id: UUID | None = None,`
  - Line 249: `correlation_id: UUID | None = None,`
  - Line 279: `correlation_id: UUID | None = None,`
  - Line 309: `correlation_id: UUID | None = None,`

**services/essay_lifecycle_service/implementations/cj_assessment_command_handler.py**
  - Line 49: `correlation_id: UUID | None = None,`

**services/essay_lifecycle_service/implementations/batch_phase_coordinator_impl.py**
  - Line 42: `correlation_id: UUID | None = None,`
  - Line 246: `correlation_id: UUID | None = None,`

**services/batch_orchestrator_service/implementations/cj_assessment_initiator_impl.py**
  - Line 42: `correlation_id: UUID | None,`

**services/batch_orchestrator_service/implementations/spellcheck_initiator_impl.py**
  - Line 39: `correlation_id: UUID | None,`

**services/batch_orchestrator_service/implementations/ai_feedback_initiator_impl.py**
  - Line 48: `correlation_id: UUID | None,`

**services/batch_orchestrator_service/implementations/nlp_initiator_impl.py**
  - Line 48: `correlation_id: UUID | None,`

**services/cj_assessment_service/protocols.py**
  - Line 111: `event_correlation_id: str | None,`
  - Line 196: `correlation_id: UUID | None,`
  - Line 204: `correlation_id: UUID | None,`

**services/cj_assessment_service/tests/unit/mocks.py**
  - Line 135: `event_correlation_id: str | None,  # Keep as str to match protocol`

**services/cj_assessment_service/implementations/db_access_impl.py**
  - Line 76: `event_correlation_id: str | None,`

**services/cj_assessment_service/implementations/event_publisher_impl.py**
  - Line 29: `correlation_id: UUID | None,`
  - Line 56: `correlation_id: UUID | None,`

**services/cj_assessment_service/cj_core_logic/workflow_orchestrator.py**
  - Line 33: `correlation_id: str | None,`

**services/cj_assessment_service/cj_core_logic/batch_preparation.py**
  - Line 25: `correlation_id: str | None,`

**services/spell_checker_service/protocols.py**
  - Line 63: `correlation_id: UUID | None,`

**services/spell_checker_service/tests/test_contract_compliance.py**
  - Line 162: `passed_correlation_id: UUID | None = call_args[0][2]  # Third argument`

**services/spell_checker_service/protocol_implementations/event_publisher_impl.py**
  - Line 26: `correlation_id: UUID | None,`

**common_core/src/common_core/events/batch_coordination_events.py**
  - Line 120: `correlation_id: UUID | None = Field(default=None, description="Request correlation ID")`

**common_core/src/common_core/events/file_management_events.py**
  - Line 30: `correlation_id: UUID | None = Field(default=None)`
  - Line 42: `correlation_id: UUID | None = Field(default=None)`
  - Line 54: `correlation_id: UUID | None = Field(default=None)`

**common_core/src/common_core/events/els_bos_events.py**
  - Line 69: `correlation_id: UUID | None = Field(`

**common_core/src/common_core/events/client_commands.py**
  - Line 35: `client_correlation_id: UUID | None = Field(`

**common_core/src/common_core/events/class_events.py**
  - Line 26: `correlation_id: UUID | None = Field(default=None)`
  - Line 40: `correlation_id: UUID | None = Field(default=None)`
  - Line 54: `correlation_id: UUID | None = Field(default=None)`
  - Line 69: `correlation_id: UUID | None = Field(default=None)`
  - Line 86: `correlation_id: UUID | None = Field(default=None)`

**common_core/src/common_core/events/file_events.py**
  - Line 37: `correlation_id: UUID | None = Field(default=None, description="Request correlation ID")`
  - Line 62: `correlation_id: UUID | None = Field(default=None, description="Request correlation ID")`

### Parameters with None as default

**services/batch_conductor_service/implementations/pipeline_resolution_service_impl.py**
  - Line 189: `correlation_id=None,`

**services/essay_lifecycle_service/protocols.py**
  - Line 108: `self, essay_ref: EntityReference, status: EssayStatus, correlation_id: UUID | None = None`
  - Line 120: `correlation_id: UUID,`

**services/essay_lifecycle_service/core_logic.py**
  - Line 15: `def generate_correlation_id() -> UUID:`

**services/essay_lifecycle_service/app.py**
  - Line 44: `def __init__(self, error: str, detail: str | None = None, correlation_id: str | None = None):`

**services/essay_lifecycle_service/tests/unit/test_cj_assessment_command_handler.py**
  - Line 223: `command_data=cj_assessment_command_data, correlation_id=correlation_id`

**services/essay_lifecycle_service/tests/unit/test_spellcheck_command_handler.py**
  - Line 216: `command_data=spellcheck_command_data, correlation_id=correlation_id`

**services/essay_lifecycle_service/api/essay_routes.py**
  - Line 51: `correlation_id: str | None = None`

**services/essay_lifecycle_service/api/batch_routes.py**
  - Line 44: `correlation_id: str | None = None`

**services/essay_lifecycle_service/implementations/service_result_handler_impl.py**
  - Line 67: `correlation_id: UUID | None = None,`
  - Line 121: `"correlation_id": str(correlation_id),`
  - Line 228: `"correlation_id": str(correlation_id),`
  - Line 335: `"correlation_id": str(correlation_id),`

**services/essay_lifecycle_service/implementations/future_services_command_handlers.py**
  - Line 47: `self, command_data: BatchServiceNLPInitiateCommandDataV1, correlation_id: UUID | None = None`
  - Line 56: `correlation_id: UUID | None = None,`

**services/essay_lifecycle_service/implementations/batch_command_handler_impl.py**
  - Line 57: `correlation_id: UUID | None = None,`
  - Line 61: `command_data, correlation_id`
  - Line 69: `command_data, correlation_id`
  - Line 79: `command_data, correlation_id`

**services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py**
  - Line 92: `extra={"error": str(e), "correlation_id": str(correlation_id)},`
  - Line 221: `extra={"error": str(e), "correlation_id": str(correlation_id)},`

**services/essay_lifecycle_service/implementations/spellcheck_command_handler.py**
  - Line 49: `correlation_id: UUID | None = None,`

**services/essay_lifecycle_service/implementations/event_publisher.py**
  - Line 44: `self, essay_ref: EntityReference, status: EssayStatus, correlation_id: UUID | None = None`
  - Line 84: `await self._publish_essay_status_to_redis(essay_ref, status, correlation_id)`
  - Line 148: `correlation_id: UUID | None = None,`
  - Line 195: `correlation_id: UUID | None = None,`
  - Line 249: `correlation_id: UUID | None = None,`
  - Line 279: `correlation_id: UUID | None = None,`
  - Line 309: `correlation_id: UUID | None = None,`

**services/essay_lifecycle_service/implementations/cj_assessment_command_handler.py**
  - Line 49: `correlation_id: UUID | None = None,`

**services/essay_lifecycle_service/implementations/batch_phase_coordinator_impl.py**
  - Line 42: `correlation_id: UUID | None = None,`
  - Line 246: `correlation_id: UUID | None = None,`

**services/batch_orchestrator_service/protocols.py**
  - Line 57: `correlation_id: uuid.UUID | None,`
  - Line 178: `correlation_id: uuid.UUID,`
  - Line 212: `correlation_id: str,`

**services/batch_orchestrator_service/tests/test_nlp_initiator_impl.py**
  - Line 242: `correlation_id=None,  # None correlation ID`

**services/batch_orchestrator_service/tests/test_ai_feedback_initiator_impl.py**
  - Line 329: `correlation_id=None,  # None correlation ID`

**services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py**
  - Line 52: `correlation_id: str,`
  - Line 118: `logger.info(message, extra={"correlation_id": correlation_id})`
  - Line 427: `extra={"correlation_id": correlation_id},`

**services/libs/huleedu_service_libs/error_handling/context_manager.py**
  - Line 24: `correlation_id: Optional[str] = None`
  - Line 103: `correlation_id: Optional[str] = None,`
  - Line 152: `correlation_id: Optional[str] = None,`

**services/result_aggregator_service/models_api.py**
  - Line 127: `correlation_id: Optional[str] = None`

**services/cj_assessment_service/event_processor.py**
  - Line 82: `"correlation_id": str(envelope.correlation_id),`

**services/cj_assessment_service/protocols.py**
  - Line 111: `event_correlation_id: str | None,`

**services/spell_checker_service/event_processor.py**
  - Line 76: `"correlation_id": str(request_envelope.correlation_id),`
  - Line 171: `extra={"correlation_id": str(request_envelope.correlation_id)},`

**services/file_service/core_logic.py**
  - Line 35: `main_correlation_id: uuid.UUID,`

### Conditional None assignments

**services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py**
  - Line 253: `# Convert correlation_id from string to UUID if needed`

**services/cj_assessment_service/implementations/event_publisher_impl.py**
  - Line 29: `correlation_id: UUID | None,`
  - Line 56: `correlation_id: UUID | None,`

### UUID generation locations

**services/class_management_service/models_db.py**
  - Line 32: `Column("class_id", UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE")),`
  - Line 33: `Column("student_id", UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE")),`
  - Line 39: `id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)`
  - Line 66: `id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)`
  - Line 83: `id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)`
  - Line 117: `id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)`
  - Line 119: `UUID(as_uuid=True), nullable=False, index=True, unique=True`

**services/class_management_service/tests/test_api_integration.py**
  - Line 104: `mock_class.id = uuid.uuid4()`
  - Line 128: `mock_student.id = uuid.uuid4()`
  - Line 153: `class_id = uuid.uuid4()`
  - Line 178: `class_id = uuid.uuid4()`
  - Line 192: `student_id = uuid.uuid4()`
  - Line 215: `student_id = uuid.uuid4()`
  - Line 232: `class_id = uuid.uuid4()`
  - Line 262: `class_id = uuid.uuid4()`
  - Line 279: `student_id = uuid.uuid4()`
  - Line 311: `student_id = uuid.uuid4()`
  - Line 327: `class_id = uuid.uuid4()`
  - Line 343: `class_id = uuid.uuid4()`
  - Line 357: `student_id = uuid.uuid4()`
  - Line 373: `student_id = uuid.uuid4()`

**services/class_management_service/api/student_routes.py**
  - Line 41: `correlation_id = uuid.uuid4()`
  - Line 87: `student_uuid = uuid.UUID(student_id)`
  - Line 146: `student_uuid = uuid.UUID(student_id)`
  - Line 149: `correlation_id = uuid.uuid4()`
  - Line 211: `student_uuid = uuid.UUID(student_id)`

**services/class_management_service/api/class_routes.py**
  - Line 41: `correlation_id = uuid.uuid4()  # Generate correlation ID`
  - Line 76: `class_uuid = uuid.UUID(class_id)`
  - Line 133: `class_uuid = uuid.UUID(class_id)`
  - Line 136: `correlation_id = uuid.uuid4()`
  - Line 198: `class_uuid = uuid.UUID(class_id)`

**services/class_management_service/implementations/class_repository_mock_impl.py**
  - Line 37: `class_id = uuid.uuid4()`
  - Line 40: `id=uuid.uuid4(),`
  - Line 79: `student_id = uuid.uuid4()`

**services/batch_conductor_service/implementations/pipeline_resolution_service_impl.py**
  - Line 185: `event_id=uuid4(),`

**services/essay_lifecycle_service/core_logic.py**
  - Line 17: `return uuid4()`

**services/essay_lifecycle_service/tests/test_redis_notifications.py**
  - Line 72: `essay_id = str(uuid4())`
  - Line 75: `correlation_id = uuid4()`
  - Line 106: `essay_id = str(uuid4())`
  - Line 123: `"essay_id": str(uuid4()),`
  - Line 126: `"correlation_id": str(uuid4()),`
  - Line 148: `essay_id = str(uuid4())`
  - Line 170: `essay_id = str(uuid4())`

**services/essay_lifecycle_service/tests/test_essay_repository_integration.py**
  - Line 61: `unique_id = str(uuid.uuid4())[:8]  # Short unique suffix`

**services/essay_lifecycle_service/tests/unit/test_future_services_command_handlers.py**
  - Line 34: `return uuid4()`

**services/essay_lifecycle_service/tests/unit/test_els_idempotency_integration.py**
  - Line 88: `"event_id": str(uuid.uuid4()),`
  - Line 92: `"correlation_id": str(uuid.uuid4()),`
  - Line 322: `"event_id": str(uuid.uuid4()),  # Different UUID each time`
  - Line 326: `"correlation_id": str(uuid.uuid4()),  # Different UUID each time`

**services/essay_lifecycle_service/tests/unit/test_batch_phase_coordinator_impl.py**
  - Line 80: `correlation_id = uuid4()`
  - Line 140: `correlation_id = uuid4()`
  - Line 199: `correlation_id = uuid4()`
  - Line 247: `correlation_id = uuid4()`
  - Line 287: `correlation_id = uuid4()`
  - Line 315: `correlation_id = uuid4()`
  - Line 429: `correlation_id = uuid4()`

**services/essay_lifecycle_service/tests/unit/test_cj_assessment_command_handler.py**
  - Line 96: `return uuid4()`

**services/essay_lifecycle_service/tests/unit/test_service_result_handler_impl.py**
  - Line 105: `correlation_id = uuid4()`
  - Line 150: `correlation_id = uuid4()`
  - Line 186: `correlation_id = uuid4()`
  - Line 210: `correlation_id = uuid4()`
  - Line 260: `correlation_id = uuid4()`
  - Line 301: `correlation_id = uuid4()`
  - Line 322: `correlation_id = uuid4()`
  - Line 361: `correlation_id = uuid4()`

**services/essay_lifecycle_service/tests/unit/test_spellcheck_command_handler.py**
  - Line 95: `return uuid4()`

**services/essay_lifecycle_service/tests/unit/test_validation_event_consumer.py**
  - Line 45: `correlation_id=uuid4(),`
  - Line 54: `event_id=uuid4(),`
  - Line 152: `correlation_id = uuid4()`
  - Line 175: `event_id=uuid4(),`
  - Line 226: `event_id=uuid4(),`
  - Line 251: `event_id=uuid4(),`
  - Line 300: `event_id=uuid4(),`
  - Line 318: `event_id=uuid4(),`

**services/essay_lifecycle_service/tests/unit/test_batch_command_integration.py**
  - Line 53: `correlation_id = uuid4()`
  - Line 93: `correlation_id = uuid4()`

**services/essay_lifecycle_service/tests/unit/test_batch_command_handler_impl.py**
  - Line 94: `return uuid4()`

**services/essay_lifecycle_service/tests/unit/test_batch_tracker_validation_enhanced.py**
  - Line 65: `correlation_id=uuid4(),`
  - Line 328: `correlation_id = uuid4()`

**services/essay_lifecycle_service/implementations/event_publisher.py**
  - Line 68: `correlation_id=correlation_id or uuid4(),`
  - Line 174: `correlation_id=correlation_id or uuid4(),`
  - Line 220: `correlation_id=correlation_id or uuid4(),`
  - Line 261: `correlation_id=correlation_id or uuid4(),`
  - Line 291: `correlation_id=correlation_id or uuid4(),`
  - Line 321: `correlation_id=correlation_id or uuid4(),`

**services/batch_orchestrator_service/tests/test_nlp_initiator_impl.py**
  - Line 73: `return uuid.uuid4()`

**services/batch_orchestrator_service/tests/test_ai_feedback_initiator_impl.py**
  - Line 75: `return uuid.uuid4()`

**services/batch_orchestrator_service/tests/test_bos_pipeline_orchestration.py**
  - Line 173: `batch_id = str(uuid4())`
  - Line 174: `correlation_id = uuid4()`
  - Line 179: `essay_id=str(uuid4()),`
  - Line 183: `essay_id=str(uuid4()),`

**services/batch_orchestrator_service/tests/unit/test_idempotency_outage.py**
  - Line 96: `batch_id = str(uuid.uuid4())`
  - Line 97: `correlation_id = str(uuid.uuid4())`
  - Line 99: `"event_id": str(uuid.uuid4()),`

**services/batch_orchestrator_service/tests/unit/test_idempotency_basic.py**
  - Line 97: `batch_id = str(uuid.uuid4())`
  - Line 98: `correlation_id = str(uuid.uuid4())`
  - Line 100: `"event_id": str(uuid.uuid4()),`
  - Line 132: `batch_id = str(uuid.uuid4())`
  - Line 133: `correlation_id = str(uuid.uuid4())`
  - Line 137: `"event_id": str(uuid.uuid4()),`

**services/batch_orchestrator_service/api/batch_routes.py**
  - Line 42: `correlation_id = uuid.uuid4()`
  - Line 275: `correlation_id=str(correlation_id) if correlation_id else str(uuid.uuid4()),`

**services/batch_orchestrator_service/implementations/batch_processing_service_impl.py**
  - Line 52: `batch_id = str(uuid.uuid4())`
  - Line 57: `str(uuid.uuid4()) for _ in range(registration_data.expected_essay_count)`

**services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py**
  - Line 254: `correlation_uuid = UUID(correlation_id) if correlation_id else None`
  - Line 403: `correlation_uuid = UUID(correlation_id) if correlation_id else None`

**services/libs/huleedu_service_libs/tests/test_idempotency.py**
  - Line 126: `"event_id": str(uuid.uuid4()),`
  - Line 130: `"correlation_id": str(uuid.uuid4()),`
  - Line 318: `"event_id": str(uuid.uuid4()),  # Different UUID each time`
  - Line 322: `"correlation_id": str(uuid.uuid4()),  # Different UUID each time`

**services/content_service/implementations/filesystem_content_store.py**
  - Line 42: `content_id = uuid.uuid4().hex`

**services/api_gateway_service/routers/status_routes.py**
  - Line 38: `correlation_id = getattr(request.state, "correlation_id", None) or str(uuid4())`

**services/api_gateway_service/routers/batch_routes.py**
  - Line 73: `correlation_id = uuid4()`

**services/result_aggregator_service/tests/unit/test_event_processor_impl.py**
  - Line 135: `batch_id = str(uuid4())`
  - Line 136: `user_id = str(uuid4())`
  - Line 160: `event_id=uuid4(),`
  - Line 185: `batch_id = str(uuid4())`
  - Line 186: `user_id = str(uuid4())`
  - Line 210: `event_id=uuid4(),`
  - Line 238: `batch_id = str(uuid4())`
  - Line 239: `user_id = str(uuid4())`
  - Line 262: `event_id=uuid4(),`
  - Line 288: `batch_id = str(uuid4())`
  - Line 300: `correlation_id=uuid4(),`
  - Line 304: `event_id=uuid4(),`
  - Line 332: `batch_id = str(uuid4())`
  - Line 343: `correlation_id=uuid4(),`
  - Line 347: `event_id=uuid4(),`
  - Line 375: `batch_id = str(uuid4())`
  - Line 383: `correlation_id=uuid4(),`
  - Line 387: `event_id=uuid4(),`
  - Line 413: `batch_id = str(uuid4())`
  - Line 423: `correlation_id=uuid4(),`
  - Line 427: `event_id=uuid4(),`
  - Line 453: `essay_id = str(uuid4())`
  - Line 454: `batch_id = str(uuid4())`
  - Line 455: `storage_id = str(uuid4())`
  - Line 487: `event_id=uuid4(),`
  - Line 517: `essay_id = str(uuid4())`
  - Line 518: `batch_id = str(uuid4())`
  - Line 542: `event_id=uuid4(),`
  - Line 571: `essay_id = str(uuid4())`
  - Line 572: `batch_id = str(uuid4())`
  - Line 597: `event_id=uuid4(),`
  - Line 640: `event_id=uuid4(),`
  - Line 658: `entity_id=str(uuid4()),`
  - Line 678: `event_id=uuid4(),`
  - Line 702: `batch_id = str(uuid4())`
  - Line 703: `essay1_id = str(uuid4())`
  - Line 704: `essay2_id = str(uuid4())`
  - Line 719: `cj_assessment_job_id=str(uuid4()),`
  - Line 737: `event_id=uuid4(),`
  - Line 785: `batch_id = str(uuid4())`
  - Line 786: `essay1_id = str(uuid4())`
  - Line 801: `cj_assessment_job_id=str(uuid4()),`
  - Line 819: `event_id=uuid4(),`
  - Line 849: `batch_id = str(uuid4())`
  - Line 864: `cj_assessment_job_id=str(uuid4()),`
  - Line 871: `event_id=uuid4(),`
  - Line 894: `batch_id = str(uuid4())`
  - Line 909: `cj_assessment_job_id=str(uuid4()),`
  - Line 912: `"els_essay_id": str(uuid4()),`
  - Line 922: `event_id=uuid4(),`

**services/result_aggregator_service/tests/integration/test_kafka_consumer_message_routing.py**
  - Line 44: `batch_id: str = str(uuid4())`
  - Line 45: `user_id: str = str(uuid4())`
  - Line 63: `event_id=uuid4(),`
  - Line 67: `correlation_id=uuid4(),`
  - Line 93: `essay_id: str = str(uuid4())`
  - Line 94: `batch_id: str = str(uuid4())`
  - Line 115: `event_id=uuid4(),`
  - Line 119: `correlation_id=uuid4(),`
  - Line 144: `batch_id: str = str(uuid4())`
  - Line 166: `event_id=uuid4(),`
  - Line 170: `correlation_id=uuid4(),`
  - Line 195: `batch_id: str = str(uuid4())`
  - Line 206: `correlation_id=uuid4(),`
  - Line 210: `event_id=uuid4(),`
  - Line 214: `correlation_id=uuid4(),`
  - Line 241: `"event_id": str(uuid4()),`

**services/result_aggregator_service/tests/integration/test_kafka_consumer_idempotency.py**
  - Line 34: `batch_id: str = str(uuid4())`
  - Line 59: `batch_id: str = str(uuid4())`
  - Line 87: `batch_id: str = str(uuid4())`
  - Line 114: `batch_id: str = str(uuid4())`
  - Line 149: `batch_id1: str = str(uuid4())`
  - Line 150: `batch_id2: str = str(uuid4())`
  - Line 185: `user_id=str(uuid4()),`
  - Line 196: `event_id=uuid4(),`
  - Line 200: `correlation_id=uuid4(),`

**services/result_aggregator_service/tests/integration/test_kafka_consumer_error_handling.py**
  - Line 99: `"event_id": str(uuid4()),`
  - Line 105: `"batch_id": str(uuid4()),`
  - Line 138: `batch_id1 = str(uuid4())`
  - Line 139: `batch_id2 = str(uuid4())`
  - Line 149: `user_id=str(uuid4()),`
  - Line 158: `event_id=uuid4(),`
  - Line 162: `correlation_id=uuid4(),`
  - Line 189: `entity_id=str(uuid4()),`
  - Line 207: `event_id=uuid4(),`
  - Line 211: `correlation_id=uuid4(),`

**services/result_aggregator_service/api/query_routes.py**
  - Line 48: `g.correlation_id = request.headers.get("X-Correlation-ID", str(uuid4()))`

**services/cj_assessment_service/event_processor.py**
  - Line 242: `correlation_id if isinstance(correlation_id, UUID) else UUID(str(correlation_id))`
  - Line 320: `correlation_id if isinstance(correlation_id, UUID) else UUID(str(correlation_id))`

**services/cj_assessment_service/tests/conftest.py**
  - Line 60: `return str(uuid4())`
  - Line 66: `return str(uuid4())`
  - Line 72: `return str(uuid4())`
  - Line 167: `correlation_id=uuid4(),`
  - Line 180: `correlation_id=uuid4(),`
  - Line 295: `{"els_essay_id": str(uuid4()), "rank": 1, "score": 0.85},`
  - Line 296: `{"els_essay_id": str(uuid4()), "rank": 2, "score": 0.72},`

**services/cj_assessment_service/tests/unit/test_cj_idempotency_basic.py**
  - Line 51: `batch_id = str(uuid.uuid4())`
  - Line 52: `essay1_id = str(uuid.uuid4())`
  - Line 53: `essay2_id = str(uuid.uuid4())`
  - Line 54: `storage1_id = str(uuid.uuid4())`
  - Line 55: `storage2_id = str(uuid.uuid4())`
  - Line 57: `"event_id": str(uuid.uuid4()),`
  - Line 61: `"correlation_id": str(uuid.uuid4()),`
  - Line 230: `shared_event_id = str(uuid.uuid4())`
  - Line 236: `"correlation_id": str(uuid.uuid4()),`
  - Line 245: `"correlation_id": str(uuid.uuid4()),`

**services/cj_assessment_service/tests/unit/test_cj_idempotency_outage.py**
  - Line 47: `batch_id = str(uuid.uuid4())`
  - Line 48: `essay1_id = str(uuid.uuid4())`
  - Line 49: `essay2_id = str(uuid.uuid4())`
  - Line 50: `storage1_id = str(uuid.uuid4())`
  - Line 51: `storage2_id = str(uuid.uuid4())`
  - Line 53: `"event_id": str(uuid.uuid4()),`
  - Line 57: `"correlation_id": str(uuid.uuid4()),`

**services/cj_assessment_service/tests/unit/test_cj_idempotency_failures.py**
  - Line 46: `batch_id = str(uuid.uuid4())`
  - Line 47: `essay1_id = str(uuid.uuid4())`
  - Line 48: `essay2_id = str(uuid.uuid4())`
  - Line 49: `storage1_id = str(uuid.uuid4())`
  - Line 50: `storage2_id = str(uuid.uuid4())`
  - Line 52: `"event_id": str(uuid.uuid4()),`
  - Line 56: `"correlation_id": str(uuid.uuid4()),`

**services/spell_checker_service/models_db.py**
  - Line 55: `UUID(as_uuid=True), primary_key=True, default=uuid.uuid4`
  - Line 57: `batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)`
  - Line 58: `essay_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)`
  - Line 103: `UUID(as_uuid=True), ForeignKey("spellcheck_jobs.job_id", ondelete="CASCADE")`

**services/spell_checker_service/tests/conftest.py**
  - Line 78: `return str(uuid4())`
  - Line 84: `return str(uuid4())`
  - Line 102: `return EntityReference(entity_id=sample_essay_id, entity_type="essay", parent_id=str(uuid4()))`
  - Line 140: `correlation_id=uuid4(),`

**services/spell_checker_service/tests/test_repository_postgres.py**
  - Line 88: `batch_id = uuid4()`
  - Line 89: `essay_id = uuid4()`
  - Line 102: `job_id = await repo.create_job(batch_id=uuid4(), essay_id=uuid4())`
  - Line 102: `job_id = await repo.create_job(batch_id=uuid4(), essay_id=uuid4())`
  - Line 112: `job_id = await repo.create_job(batch_id=uuid4(), essay_id=uuid4())`
  - Line 112: `job_id = await repo.create_job(batch_id=uuid4(), essay_id=uuid4())`

**services/spell_checker_service/tests/test_contract_compliance.py**
  - Line 167: `UUID(request_envelope_dict["correlation_id"])`

**services/spell_checker_service/tests/test_di_container.py**
  - Line 57: `await repo.create_job(batch_id=uuid.uuid4(), essay_id=uuid.uuid4())`
  - Line 57: `await repo.create_job(batch_id=uuid.uuid4(), essay_id=uuid.uuid4())`

**services/spell_checker_service/tests/unit/test_spell_idempotency_basic.py**
  - Line 160: `shared_event_id = str(uuid.uuid4())`
  - Line 166: `"correlation_id": str(uuid.uuid4()),`
  - Line 174: `"correlation_id": str(uuid.uuid4()),`

**services/spell_checker_service/tests/unit/test_kafka_consumer_integration.py**
  - Line 61: `essay_id = str(uuid.uuid4())`
  - Line 62: `correlation_id = str(uuid.uuid4())`
  - Line 65: `"event_id": str(uuid.uuid4()),`

**services/spell_checker_service/tests/unit/spell_idempotency_test_utils.py**
  - Line 84: `essay_id = str(uuid.uuid4())`
  - Line 85: `correlation_id = str(uuid.uuid4())`
  - Line 88: `"event_id": str(uuid.uuid4()),`

**services/spell_checker_service/alembic/versions/20250630_0001_initial_schema.py**
  - Line 25: `sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),`
  - Line 26: `sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),`
  - Line 27: `sa.Column("essay_id", postgresql.UUID(as_uuid=True), nullable=False),`
  - Line 46: `sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spellcheck_jobs.job_id", ondelete="CASCADE"), nullable=False),`

**services/spell_checker_service/implementations/spell_repository_postgres_impl.py**
  - Line 86: `new_job_id = uuid.uuid4()`

**services/file_service/tests/unit/test_core_logic_validation_failures.py**
  - Line 44: `correlation_id = uuid.uuid4()`
  - Line 116: `correlation_id = uuid.uuid4()`
  - Line 173: `correlation_id = uuid.uuid4()`
  - Line 230: `correlation_id = uuid.uuid4()`
  - Line 288: `correlation_id = uuid.uuid4()`

**services/file_service/tests/unit/test_core_logic_validation_errors.py**
  - Line 40: `correlation_id = uuid.uuid4()`
  - Line 92: `correlation_id = uuid.uuid4()`

**services/file_service/tests/unit/test_core_logic_raw_storage.py**
  - Line 26: `batch_id = str(uuid.uuid4())`
  - Line 29: `correlation_id = uuid.uuid4()`
  - Line 80: `batch_id = str(uuid.uuid4())`
  - Line 83: `correlation_id = uuid.uuid4()`
  - Line 127: `batch_id = str(uuid.uuid4())`
  - Line 130: `correlation_id = uuid.uuid4()`
  - Line 179: `batch_id = str(uuid.uuid4())`
  - Line 182: `correlation_id = uuid.uuid4()`

**services/file_service/tests/unit/test_empty_file_validation.py**
  - Line 36: `correlation_id = uuid.uuid4()`
  - Line 114: `correlation_id = uuid.uuid4()`
  - Line 174: `correlation_id = uuid.uuid4()`

**services/file_service/tests/unit/test_file_routes_validation.py**
  - Line 254: `uuid.UUID(data["correlation_id"])  # Should not raise exception`
  - Line 314: `uuid.UUID(data["correlation_id"])  # Should not raise exception`
  - Line 385: `uuid.UUID(data["correlation_id"])  # Should not raise exception`

**services/file_service/tests/unit/test_event_publisher_file_management.py**
  - Line 58: `correlation_id = uuid.uuid4()`
  - Line 150: `correlation_id = uuid.uuid4()`

**services/file_service/tests/unit/test_core_logic_validation_success.py**
  - Line 42: `correlation_id = uuid.uuid4()`
  - Line 121: `correlation_id = uuid.uuid4()`

**services/file_service/api/file_routes.py**
  - Line 77: `main_correlation_id = uuid.UUID(correlation_id_header)`
  - Line 84: `main_correlation_id = uuid.uuid4()`
  - Line 86: `main_correlation_id = uuid.uuid4()`
  - Line 216: `main_correlation_id = uuid.UUID(correlation_id_header)`
  - Line 223: `main_correlation_id = uuid.uuid4()`
  - Line 225: `main_correlation_id = uuid.uuid4()`
  - Line 238: `essay_id = str(uuid.uuid4())  # Generate essay_id for each file`
  - Line 348: `correlation_id = uuid.UUID(correlation_id_header)`
  - Line 355: `correlation_id = uuid.uuid4()`
  - Line 357: `correlation_id = uuid.uuid4()`

**common_core/tests/test_event_utils.py**
  - Line 25: `"event_id": str(uuid4()),  # Different each time`
  - Line 32: `event1["event_id"] = str(uuid4())`
  - Line 36: `event2["event_id"] = str(uuid4())  # Different UUID`
  - Line 55: `"event_id": str(uuid4()),`
  - Line 60: `"event_id": str(uuid4()),`
  - Line 78: `"event_id": str(uuid4()),`
  - Line 83: `"event_id": str(uuid4()),`
  - Line 128: `event = {"data": {}, "event_id": str(uuid4()), "source_service": "test_service"}`
  - Line 143: `"event_id": str(uuid4()),`
  - Line 182: `"event_id": str(uuid4()),`
  - Line 186: `"correlation_id": str(uuid4()),`
  - Line 215: `correlation_id = str(uuid4())`
  - Line 217: `"event_id": str(uuid4()),`
  - Line 234: `"event_id": str(uuid4()),`

**common_core/tests/unit/test_class_events.py**
  - Line 46: `correlation_id = uuid4()`
  - Line 67: `correlation_id = uuid4()`
  - Line 144: `correlation_id = uuid4()`
  - Line 169: `correlation_id = uuid4()`
  - Line 262: `correlation_id = uuid4()`
  - Line 308: `correlation_id = uuid4()`

**common_core/tests/unit/test_file_management_events.py**
  - Line 57: `correlation_id = uuid4()`
  - Line 96: `correlation_id = uuid4()`
  - Line 199: `correlation_id = uuid4()`
  - Line 220: `correlation_id = uuid4()`
  - Line 247: `correlation_id = uuid4()`
  - Line 292: `correlation_id = uuid4()`
  - Line 313: `correlation_id = uuid4()`
  - Line 340: `correlation_id = uuid4()`

**common_core/tests/unit/test_file_events.py**
  - Line 44: `correlation_id = uuid4()`
  - Line 84: `correlation_id = uuid4()`
  - Line 106: `correlation_id = uuid4()`
  - Line 245: `correlation_id = uuid4()`

### String conversions of correlation_id

**services/essay_lifecycle_service/batch_command_handlers.py**
  - Line 122: `"correlation_id": str(correlation_id),`
  - Line 137: `"Event processed successfully", extra={"correlation_id": str(correlation_id)}`
  - Line 140: `logger.error("Event processing failed", extra={"correlation_id": str(correlation_id)})`
  - Line 318: `"correlation_id": str(correlation_id),`
  - Line 330: `"correlation_id": str(correlation_id),`

**services/essay_lifecycle_service/tests/test_redis_notifications.py**
  - Line 95: `assert notification_data["correlation_id"] == str(correlation_id)`

**services/essay_lifecycle_service/implementations/service_result_handler_impl.py**
  - Line 80: `"correlation_id": str(correlation_id),`
  - Line 91: `"correlation_id": str(correlation_id),`
  - Line 108: `"correlation_id": str(correlation_id),`
  - Line 121: `"correlation_id": str(correlation_id),`
  - Line 188: `"correlation_id": str(correlation_id),`
  - Line 196: `extra={"correlation_id": str(correlation_id)},`
  - Line 205: `"correlation_id": str(correlation_id),`
  - Line 228: `"correlation_id": str(correlation_id),`
  - Line 245: `"correlation_id": str(correlation_id),`
  - Line 255: `extra={"ranking": ranking, "correlation_id": str(correlation_id)},`
  - Line 266: `"correlation_id": str(correlation_id),`
  - Line 300: `"correlation_id": str(correlation_id),`
  - Line 308: `extra={"correlation_id": str(correlation_id)},`
  - Line 335: `"correlation_id": str(correlation_id),`
  - Line 353: `"correlation_id": str(correlation_id),`
  - Line 397: `"correlation_id": str(correlation_id),`
  - Line 405: `extra={"correlation_id": str(correlation_id)},`
  - Line 417: `"correlation_id": str(correlation_id),`

**services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py**
  - Line 53: `"correlation_id": str(correlation_id),`
  - Line 70: `"correlation_id": str(correlation_id),`
  - Line 83: `"correlation_id": str(correlation_id),`
  - Line 92: `extra={"error": str(e), "correlation_id": str(correlation_id)},`
  - Line 109: `"correlation_id": str(correlation_id),`
  - Line 125: `"correlation_id": str(correlation_id),`
  - Line 143: `"correlation_id": str(correlation_id),`
  - Line 186: `"correlation_id": str(correlation_id),`
  - Line 221: `extra={"error": str(e), "correlation_id": str(correlation_id)},`
  - Line 238: `"correlation_id": str(correlation_id),`
  - Line 270: `"correlation_id": str(correlation_id),`
  - Line 279: `extra={"error": str(e), "correlation_id": str(correlation_id)},`

**services/essay_lifecycle_service/implementations/spellcheck_command_handler.py**
  - Line 58: `"correlation_id": str(correlation_id),`
  - Line 74: `"correlation_id": str(correlation_id),`
  - Line 109: `"correlation_id": str(correlation_id),`
  - Line 122: `"correlation_id": str(correlation_id),`
  - Line 131: `"correlation_id": str(correlation_id),`
  - Line 152: `"correlation_id": str(correlation_id),`
  - Line 178: `"correlation_id": str(correlation_id),`
  - Line 187: `"correlation_id": str(correlation_id),`
  - Line 196: `"correlation_id": str(correlation_id),`
  - Line 206: `"correlation_id": str(correlation_id),`
  - Line 213: `extra={"correlation_id": str(correlation_id)},`

**services/essay_lifecycle_service/implementations/event_publisher.py**
  - Line 108: `"correlation_id": str(correlation_id) if correlation_id else None,`
  - Line 118: `"correlation_id": str(correlation_id) if correlation_id else None,`
  - Line 127: `"correlation_id": str(correlation_id) if correlation_id else None,`
  - Line 136: `"correlation_id": str(correlation_id) if correlation_id else None,`

**services/essay_lifecycle_service/implementations/cj_assessment_command_handler.py**
  - Line 58: `"correlation_id": str(correlation_id),`
  - Line 76: `"correlation_id": str(correlation_id),`
  - Line 94: `"correlation_id": str(correlation_id),`
  - Line 126: `"correlation_id": str(correlation_id),`
  - Line 139: `"correlation_id": str(correlation_id),`
  - Line 148: `"correlation_id": str(correlation_id),`
  - Line 172: `"correlation_id": str(correlation_id),`
  - Line 194: `"correlation_id": str(correlation_id),`
  - Line 212: `"correlation_id": str(correlation_id),`
  - Line 221: `"correlation_id": str(correlation_id),`
  - Line 230: `"correlation_id": str(correlation_id),`
  - Line 240: `"correlation_id": str(correlation_id),`
  - Line 247: `extra={"correlation_id": str(correlation_id)},`

**services/essay_lifecycle_service/implementations/service_request_dispatcher.py**
  - Line 56: `"correlation_id": str(correlation_id),`
  - Line 111: `"correlation_id": str(correlation_id),`
  - Line 121: `"correlation_id": str(correlation_id),`
  - Line 129: `"correlation_id": str(correlation_id),`
  - Line 186: `"correlation_id": str(correlation_id),`
  - Line 241: `"correlation_id": str(correlation_id),`
  - Line 251: `"correlation_id": str(correlation_id),`

**services/essay_lifecycle_service/implementations/batch_phase_coordinator_impl.py**
  - Line 60: `extra={"phase_name": phase_name, "correlation_id": str(correlation_id)},`
  - Line 75: `extra={"essay_id": essay_state.essay_id, "correlation_id": str(correlation_id)},`
  - Line 92: `"correlation_id": str(correlation_id),`
  - Line 110: `"correlation_id": str(correlation_id),`
  - Line 142: `"correlation_id": str(correlation_id),`
  - Line 164: `"correlation_id": str(correlation_id),`

**services/batch_orchestrator_service/tests/test_bos_pipeline_orchestration.py**
  - Line 224: `correlation_id=str(correlation_id),`

**services/batch_orchestrator_service/api/batch_routes.py**
  - Line 55: `extra={"correlation_id": str(correlation_id)},`
  - Line 75: `{"batch_id": batch_id, "correlation_id": str(correlation_id), "status": "registered"},`
  - Line 275: `correlation_id=str(correlation_id) if correlation_id else str(uuid.uuid4()),`

**services/batch_orchestrator_service/implementations/cj_assessment_initiator_impl.py**
  - Line 55: `extra={"correlation_id": str(correlation_id)},`
  - Line 110: `extra={"correlation_id": str(correlation_id)},`
  - Line 117: `extra={"correlation_id": str(correlation_id)},`

**services/batch_orchestrator_service/implementations/batch_processing_service_impl.py**
  - Line 64: `extra={"correlation_id": str(correlation_id)},`
  - Line 76: `extra={"correlation_id": str(correlation_id)},`
  - Line 164: `extra={"correlation_id": str(correlation_id)},`

**services/batch_orchestrator_service/implementations/spellcheck_initiator_impl.py**
  - Line 52: `extra={"correlation_id": str(correlation_id)},`
  - Line 101: `extra={"correlation_id": str(correlation_id)},`
  - Line 108: `extra={"correlation_id": str(correlation_id)},`

**services/batch_orchestrator_service/implementations/ai_feedback_initiator_impl.py**
  - Line 63: `extra={"correlation_id": str(correlation_id)},`
  - Line 115: `extra={"correlation_id": str(correlation_id)},`
  - Line 122: `extra={"correlation_id": str(correlation_id)},`

**services/batch_orchestrator_service/implementations/els_batch_phase_outcome_handler.py**
  - Line 73: `"correlation_id": str(correlation_id),`
  - Line 83: `extra={"correlation_id": str(correlation_id)},`
  - Line 91: `correlation_id=str(correlation_id),`

**services/batch_orchestrator_service/implementations/nlp_initiator_impl.py**
  - Line 63: `extra={"correlation_id": str(correlation_id)},`
  - Line 107: `extra={"correlation_id": str(correlation_id)},`
  - Line 114: `extra={"correlation_id": str(correlation_id)},`

**services/libs/huleedu_service_libs/event_utils.py**
  - Line 57: `return str(correlation_id)`

**services/api_gateway_service/routers/batch_routes.py**
  - Line 150: `"correlation_id": str(correlation_id),`

**services/cj_assessment_service/event_processor.py**
  - Line 143: `"correlation_id": str(correlation_id),`
  - Line 184: `correlation_id=str(correlation_id),`
  - Line 242: `correlation_id if isinstance(correlation_id, UUID) else UUID(str(correlation_id))`
  - Line 320: `correlation_id if isinstance(correlation_id, UUID) else UUID(str(correlation_id))`

**services/cj_assessment_service/implementations/event_publisher_impl.py**
  - Line 42: `key = str(correlation_id) if correlation_id else None`
  - Line 69: `key = str(correlation_id) if correlation_id else None`

**services/file_service/api/file_routes.py**
  - Line 383: `"correlation_id": str(correlation_id),`

**common_core/tests/unit/test_file_events.py**
  - Line 56: `assert str(serialized["correlation_id"]) == str(correlation_id)`

### Checks for None correlation_id

**services/libs/huleedu_service_libs/event_utils.py**
  - Line 56: `if correlation_id is not None:`

### Methods with None default for correlation_id

**services/essay_lifecycle_service/protocols.py**
  - Line 107: `publish_status_update() method`

**services/essay_lifecycle_service/app.py**
  - Line 44: `__init__() method`

**services/essay_lifecycle_service/implementations/service_result_handler_impl.py**
  - Line 64: `handle_spellcheck_result() method`
  - Line 233: `handle_cj_assessment_completed() method`
  - Line 340: `handle_cj_assessment_failed() method`

**services/essay_lifecycle_service/implementations/future_services_command_handlers.py**
  - Line 46: `process_initiate_nlp_command() method`
  - Line 53: `process_initiate_ai_feedback_command() method`

**services/essay_lifecycle_service/implementations/batch_command_handler_impl.py**
  - Line 54: `process_initiate_spellcheck_command() method`
  - Line 64: `process_initiate_nlp_command() method`
  - Line 72: `process_initiate_ai_feedback_command() method`
  - Line 82: `process_initiate_cj_assessment_command() method`

**services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py**
  - Line 96: `handle_essay_content_provisioned() method`
  - Line 225: `handle_essay_validation_failed() method`

**services/essay_lifecycle_service/implementations/spellcheck_command_handler.py**
  - Line 46: `process_initiate_spellcheck_command() method`

**services/essay_lifecycle_service/implementations/event_publisher.py**
  - Line 43: `publish_status_update() method`
  - Line 86: `_publish_essay_status_to_redis() method`
  - Line 141: `publish_batch_phase_progress() method`
  - Line 189: `publish_batch_phase_concluded() method`
  - Line 246: `publish_excess_content_provisioned() method`
  - Line 276: `publish_batch_essays_ready() method`
  - Line 306: `publish_els_batch_phase_outcome() method`

**services/essay_lifecycle_service/implementations/cj_assessment_command_handler.py**
  - Line 46: `process_initiate_cj_assessment_command() method`

**services/essay_lifecycle_service/implementations/batch_phase_coordinator_impl.py**
  - Line 38: `check_batch_completion() method`
  - Line 240: `_publish_batch_phase_outcome() method`

**services/libs/huleedu_service_libs/error_handling/context_manager.py**
  - Line 149: `capture_error_context() method`
  - Line 98: `from_exception() method`
