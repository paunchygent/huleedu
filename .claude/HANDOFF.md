# HuleEdu Monorepo - Handoff Document

## Current Status (Jan 25, 2025)

### What We Just Completed
Corrected major inaccuracies in Bayesian consensus model report (`docs/rapport_till_kollegor/files/kalibrering_rapport_korrigerad.html`). Fixed rater bias interpretation (negative=strict, positive=generous), updated all data values to match actual model output, anonymized content, and regenerated all figures with proper color schemes and layouts.

### System State
- All services running and healthy
- Tests passing (including `test_e2e_cj_after_nlp_with_pruning.py`)
- No blocking issues
- Redis caching plan still complete in `TASKS/updated_plan.md` (pending implementation)
- Bayesian report corrections completed using data from `output/bayesian_consensus_model/20250924-202445/bias_on/`
- All figures regenerated via `docs/rapport_till_kollegor/create_corrected_figures.py`

## Open Work

### Redis Caching Implementation (In Progress)
- **Plan**: Complete in `TASKS/updated_plan.md`
- **Architecture**: Cache wraps circuit breaker (outermost layer)
- **Key decisions**:
  - Scoped error handling (Redis vs delegate errors separated)
  - Cache serves hits even when circuit breaker open
  - Configuration-driven TTL (`BCS_CACHE_TTL_SECONDS`)
  - Corrupted entries evicted as cache misses
- **Files to create**:
  - `services/batch_orchestrator_service/implementations/cached_batch_conductor_client.py`
- **Files to modify**:
  - `services/batch_orchestrator_service/config.py` (add cache settings after line 83)
  - `services/batch_orchestrator_service/di.py` (update `provide_batch_conductor_client` lines 310-327)

## Next Steps

1. **Implement Redis caching** (follow `TASKS/updated_plan.md`):
   ```bash
   # 1. Update config
   vim services/batch_orchestrator_service/config.py
   # Add BCS_CACHE_TTL_SECONDS and BCS_CACHE_ENABLED after line 83

   # 2. Create cache wrapper
   vim services/batch_orchestrator_service/implementations/cached_batch_conductor_client.py
   # Copy implementation from plan

   # 3. Update DI
   vim services/batch_orchestrator_service/di.py
   # Update provide_batch_conductor_client (lines 310-327)

   # 4. Test
   pdm run pytest-root services/batch_orchestrator_service/tests/unit/test_cached_batch_conductor_client.py
   ```

2. **Verify cache effectiveness**:
   ```bash
   pdm run pytest-root tests/functional/test_e2e_cj_after_nlp_with_pruning.py -v -s
   # Look for "BCS resolution cache hit" in logs
   ```

## Key Artifacts

### Redis Caching Plan
- **Location**: `TASKS/updated_plan.md`
- **Cache key format**: `bcs_resolution:{batch_id}:{pipeline}:{correlation_id}`
- **TTL**: 10 seconds (configurable)
- **Layering**: Cache → Circuit Breaker → Base Client

### Test Commands
```bash
# Verify duplicate calls eliminated
pdm run pytest-root tests/functional/test_e2e_cj_after_nlp_with_pruning.py -v -s

# Check cache behavior in logs
docker logs huleedu_batch_orchestrator_service 2>&1 | grep "BCS resolution cache"
```

### Recent Report Corrections
**Data Source**: `output/bayesian_consensus_model/20250924-202445/bias_on/`
**Key Files**:
- `essay_consensus.csv` - 12 essays, grades E+ to B, ability scores 3.43-8.50
- `rater_bias_posteriors_eb.csv` - 14 raters, bias range -0.74 to +0.56
- `essay_inter_rater_stats.csv` - Agreement statistics

**Figures Generated**:
```
docs/rapport_till_kollegor/files/figur1_uppsatskvalitet.png
docs/rapport_till_kollegor/files/figur2_bedömarstränghet.png
docs/rapport_till_kollegor/files/figur3_betygströsklar.png
docs/rapport_till_kollegor/files/figur4_bedömarspridning.png
```

## Environment Setup

### Python Environment
```bash
pdm --version  # 2.10.4
python --version  # Python 3.11.x
pdm install  # From repo root only
```

### Container Status Check
```bash
docker ps | grep huleedu  # Should show all services
```

## Cache Configuration

### New Settings (to add)
```python
# services/batch_orchestrator_service/config.py (after line 83)
BCS_CACHE_TTL_SECONDS: int = Field(default=10, ge=1, le=300)
BCS_CACHE_ENABLED: bool = Field(default=True)
```

### Cache Response Schema
```python
# Cached BCS response format
{
    "batch_id": str,
    "final_pipeline": List[str],
    "analysis_summary": str
}
```

## Critical Notes

### System
- **PDM**: Always run from repo root, never from subdirectories
- **Tests**: Use `pdm run pytest-root` for correct path resolution
- **Docker logs**: Never use `--since` (timezone issues)

### Bayesian Data Interpretation
- **Rater bias**: Negative = strict, positive = generous (was backwards in original)
- **Grade scale**: F, F+, E-, E+, D-, D+, C-, C+, B, A (E, D, C don't exist standalone)
- **Anonymization**: Real names → Rater IDs via `MAP_OF_RATER_ID_AND_REAL_RATERS.csv`
- **Outlier**: JP24 (E+) only essay at that level, affects step analysis

### Redis Caching (Still Pending)
- **Cache layering**: Cache must wrap circuit breaker (outermost)
- **Error handling**: Redis failures must not block operations