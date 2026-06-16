# Background & History

## Origin (2023)

This library was initially built as part of the research and development team's effort to implement distributed tracing, alongside tools like Jaeger and OpenTelemetry. Development began in 2023 as an internal exploration into service mesh patterns and self-healing architectures.

At the time, the broader platform was evaluating observability tooling:

- **2021:** Jaeger and OpenTelemetry were discussed but not adopted
- **2023:** Both tracing systems were eventually adopted across the platform
- **2023:** This experimental library was shelved as the platform moved to production-grade tracing solutions

## Resurrection (2026)

Fast forward to June 2026. The chat services needed to become fully independent and required their own lightweight monitoring system, something more targeted than the full OpenTelemetry stack for a focused use case.

The library resurfaced when:

- The **Backend** and **Frontend** teams needed a dedicated health-check and service-assignment layer for the chat infrastructure
- The existing tracing infrastructure was too heavy for the chat team's requirements
- A lightweight, in-process registry could run alongside the chat services without additional infrastructure

The original codebase was revived, extended with real downstream services, and wired into production chat infrastructure.

## Architecture Considerations

The library follows a deliberately **lightweight** approach:

### Why In-Memory?

The core registry state is kept in memory for speed:

- **No database round-trips** for registration lookups and health checks
- **No schema migrations** to manage
- **Instant restart** just re-register services and resume operations

### Why SQLite for Store Events?

Events need to survive restarts for audit and debugging purposes:

- **Embedded**: no separate database server to maintain
- **Zero-configuration**: the database file is created automatically
- **WAL mode**: readers never block writers, writers never block readers
- **Thread-safe**: dedicated lock serialises writes, indexes speed up queries

### Why Not a Full Service Mesh?

Not every distributed system needs Istio or Linkerd. For our cases, teams that need:

- A single focused feature (health checking with circuit breaking)
- Minimal operational overhead (one container, one process)
- Fast iteration (no CRD definitions, no sidecar injection, no control plane)

...this library provides the essential patterns without the complexity overhead of a full service mesh. It is not meant to replace those tools but to serve as a lightweight alternative for specific use cases

## Inspiration

The design is heavily inspired by:

- **[Netflix Hystrix](https://github.com/Netflix/Hystrix)** — Circuit breaker patterns and fault isolation
- **[Microservices Patterns](https://microservices.io/patterns/index.html)** — Service registry, circuit breaker, and health check patterns from Chris Richardson's catalog

## Current Status

The library is running as a **live experiment** in production for the chat infrastructure as of June 2026. It is intentionally kept small and focused, with the understanding that it may be replaced by more robust infrastructure as requirements grow.

## Future Considerations

This library is intentionally lightweight, but several enhancements would make it production-grade for a larger mesh. Especially, the targeted environment possibly grows larger since we also need to opt-in the Chat services for other platforms

| Improvement | Rationale |
|-------------|-----------|
| **Persistent state (partially addressed)** | Event history is now persisted via SQLite. Future work could extend persistence to service registrations and assignments using SQLite, Redis, or an external database |
| **Async health checks** | `asyncio` or `aiohttp` to avoid blocking the GIL during slow probes |
| **Clustering** | Multiple instances with a shared backend (for example, Consul or etcd) for high availability |
| **Authentication** | API key or mTLS on the registry endpoints to prevent unauthorized deregistration |
| **Prometheus metrics** | Export counters and histograms in `/metrics` format for scraping |
| **Load balancing strategies** | Round-robin or least-latency instead of first-available assignment |
| **Custom health thresholds** | Per-service timeout and failure-threshold configuration |
| **Graceful shutdown** | Drain in-flight requests before stopping the health check thread |
| **TLS termination** | Run Gunicorn with certificates instead of handling TLS inside Flask |