# TASK: CJ BatchMonitor embed + recovery after Kafka/db outage

## Summary
- Embedded BatchMonitor into `services/cj_assessment_service/app.py` so monitor runs in-process (no separate worker) and added heartbeat + completion sweep logs for visibility.
- Added completion sweep in monitor to finalize batches when callbacks are complete.
- Current blocking issue: local infra (Kafka bootstrap to `kafka:9092` failing; `cj_assessment_db` in recovery/rejecting connections) prevents validation; pipeline test stalled after CJ initiation.

## Status
- Code merged locally (format/lint clean); not validated in running stack due to infra outages.
- CJ service container unhealthy; db container in recovery; Kafka unreachable from CJ container.

## Next Steps
1) Restore infra:
   - Bring `huleedu_cj_assessment_db` up; resolve recovery/connection rejection.
   - Ensure Kafka/Zookeeper containers running and reachable from CJ service (`kafka:9092`).
   - Restart `huleedu_cj_assessment_service` once infra is healthy.
2) Re-run pipeline test (correlation `4cc75b6c-0fb2-465f-a20d-dfa0fb7de79f` / batch `588f04f4-219f-4545-9040-eabae4161f72`) to confirm:
   - monitor heartbeat logs in Loki,
   - completion sweep finalizes CJ batches (cj_assessment.completed + ras results).
3) If still stalled, inspect `cj_batch_states`/`cj_batch_uploads` for new runs and verify completion sweep threshold logic.

## Files touched
- `services/cj_assessment_service/app.py` — start monitor task; stop it on shutdown.
- `services/cj_assessment_service/batch_monitor.py` — heartbeat log + completion sweep finalize path.

## Open Risks
- Infra downtime masks functional validation; need stable Kafka + DB to confirm fix.
- Compose restart of db failed (network/compose dependency); rerun with full compose stack.

## 2025-11-21 Updates (post-restore)
- Infra restored; BatchMonitor running; stalled batches 35–38 forced to completion.
- E2E CJ functional test now passes but took ~3m56s for 4 essays: completion gate still based on 95% of `total_budget=350`, so batch remained in WAITING_CALLBACKS until the 5-minute monitor sweep forced completion. Callbacks arrived in ~12s; delay is purely the completion threshold logic.
- Proposed follow-up (not yet implemented): stability-first completion, cap budget denominator to nC2 for small batches, keep monitor only for recovery (or shorten dev interval).
- Once completion gate is fixed, BatchMonitor should remain recovery-only; normal-path completion must not depend on the 5-minute sweep.
