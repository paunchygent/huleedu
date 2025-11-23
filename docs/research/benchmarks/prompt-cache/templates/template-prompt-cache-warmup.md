# Prompt Cache Warmup Benchmark (TEMPLATE)

- Timestamp: <timestamp>
- Fixture: <smoke|full|custom>
- Requests: <total> (seeds: <seed_count>)
- Hit rate (post-warm): <value>
- Post-seed miss rate: <value>
- Tokens saved (read): <value>
- Tokens written (seed cost): <value>
- TTL violations: <count>
- 429/rate-limit errors: <count>
- Latency p50/p95 (ms): <p50> / <p95>
- Grafana dashboard: <grafana-link>
- JSON artefact: <json-path>

## Cache Hashes
- <cache-hash-1>: hits=<h>, misses=<m>, post-seed-miss-rate=<rate>
- <cache-hash-2>: hits=<h>, misses=<m>, post-seed-miss-rate=<rate>
