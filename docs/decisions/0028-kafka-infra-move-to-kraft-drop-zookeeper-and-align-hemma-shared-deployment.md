---
type: decision
id: ADR-0028
status: proposed
created: '2026-02-01'
last_updated: '2026-02-01'
---
# ADR-0028: Kafka infra: move to KRaft (drop ZooKeeper) and align Hemma shared deployment

## Status

Accepted

## Context

- Hemma deployment is blocked by ZooKeeper image availability: `bitnami/zookeeper:*`
  is no longer published on Docker Hub (moved to “Bitnami Secure Images”), which
  results in `manifest unknown` when trying to pull the image.
- ZooKeeper is an operational dependency we do not need for a single-node alpha
  deployment; it increases complexity and the blast radius for upgrades.
- Apache Kafka’s KRaft mode removes ZooKeeper entirely and is the strategic direction
  of upstream Kafka.
- For Hemma, we deploy with Skriptoteket-style shared infra:
  - external network: `hule-network`
  - shared DB: `shared-postgres`
  - shared observability stack (Jaeger/Loki/Grafana/Prometheus)
  HuleEdu should not start a competing observability compose stack on Hemma.
- Developer workflow constraint: local dev is also “staging”, so infra should be as
  production-like as practical (while still supporting hot reload for app services).

## Decision

- Select infra images using these criteria (ordered):
  1. **Supported**: upstream or vendor-supported images with clear lifecycle.
  2. **Multi-arch**: runnable on both x86_64 and ARM64 where feasible.
  3. **Maintained**: active releases and security updates.
  4. **Operational fit**: minimal moving parts for a solo-maintained home server.
  5. **Prod/dev parity**: compose layering keeps Hemma close to local staging.

- Replace ZooKeeper-based Kafka with Kafka in KRaft mode.
- Standardize Kafka image to the official `apache/kafka:<version>` image for a
  maintained, multi-arch upstream source.
- Keep host tooling compatibility (`localhost:9093` bootstrap) while ensuring Hemma
  does not expose Kafka publicly by binding host ports to `127.0.0.1`.
- Introduce a Hemma-specific compose entrypoint (`docker-compose.hemma.yml`) that
  includes only `docker-compose.infrastructure.yml` and `docker-compose.services.yml`
  (no repo-owned observability stack).

## Consequences

- ✅ Kafka infra becomes pullable and starts on Hemma without ZooKeeper.
- ✅ Fewer moving parts; easier upgrades and ops for a solo maintainer.
- ✅ Clear separation between “HuleEdu app” and Hemma shared observability.
- ⚠️ Existing ZooKeeper-specific operational knowledge becomes obsolete.
- ⚠️ KRaft configuration must be kept correct (listener + controller quorum config).

## Alternatives Considered

1. **Stay on ZooKeeper (switch images)**
   - Pros: minimal behavioral change.
   - Cons: keeps ZooKeeper complexity; depends on a ZooKeeper image supply chain.
2. **Confluent `cp-kafka` + `cp-zookeeper`**
   - Pros: commonly used.
   - Cons: still ZooKeeper; heavier images; more vendor-specific config.
3. **Redpanda (Kafka API compatible)**
   - Pros: simple, single binary; fast.
   - Cons: not upstream Kafka; introduces compatibility surface area (risk) during alpha.

## References

- Apache Kafka KRaft documentation: <https://kafka.apache.org/documentation/#kraft>
- Official Apache Kafka Docker image: <https://hub.docker.com/r/apache/kafka>
- Bitnami ZooKeeper image status: <https://hub.docker.com/r/bitnami/zookeeper>
