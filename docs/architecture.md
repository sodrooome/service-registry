# Service Registry Architecture

This document explains the internals of the service registry management library and the topology mesh that has been wired up within MauKerja chat services on the production environment. It covers the design decisions, data flow, and how the library simulates a service registry pattern with circuit breaker and health checking features. The document also includes API endpoints, usage examples, and future considerations for production deployment

## 1. Overview

The library implements a lightweight service registry pattern inspired by Netflix Hystrix. It provides four main building blocks:

| Feature | Purpose |
|---------|---------|
| **Service Registration** | Register a service name, URL mapping and hold it in memory |
| **Service Assignment** | Route a service to another one so the caller always hits an available instance |
| **Health Checking** | Periodically probe each registered URL and mark it `AVAILABLE`, `STARTING`, or `DOWN` |
| **Circuit Breaker** | After 3 consecutive failures, open the circuit and stop hammering the unhealthy service for 5 seconds |
| **Request Tracing** | Count total, successful, and failed requests, and measure cumulative duration |

## 2. Topology Mesh

The current implementation as per the first week of June 2026, the system is pre-registered with five downstream services which are related to the Chat services that are widely used on the MauKerja platform. Two of them are chained together via assignments, while three others are independent. Dependencies define readiness constraints:

```mermaid
graph LR
  subgraph "Assignment Chain"
    A["FE-Chat-Health-Apache-Proxy<br/>(Apache Reverse Proxy)"]
    B["FE-Chat-Health-Node-Proxy<br/>(Node.js Proxy)"]
    C["BE-Chat-Health<br/>(Backend Chat Service)"]
    A -- assigned to --> B
    B -- assigned to --> C
  end

  subgraph "Independent Services"
    D["Maukerja-Server<br/>(Main Backend API)"]
    E["V3-API-BE<br/>(V3 API Backend)"]
  end

  subgraph "Dependencies"
    D -- depends on --> E
    D -- depends on --> C
    A -- depends on --> B
    B -- depends on --> C
  end
```

### 2.1 Assignments

Assignments create a routing chain. When you ask the registry for `FE-Chat-Health-Apache-Proxy`, it transparently returns the URL of `FE-Chat-Health-Node-Proxy`. Ask for the Node proxy and you get `BE-Chat-Health`.

```mermaid
sequenceDiagram
  participant Client
  participant Registry
  participant Apache as FE-Chat-Health-Apache-Proxy
  participant Node as FE-Chat-Health-Node-Proxy
  participant Chat as BE-Chat-Health

  Client->>Registry: GET /api/service/FE-Chat-Health-Apache-Proxy
  Registry->>Apache: Resolve
  Apache-->>Registry: assigned to Node Proxy
  Registry->>Node: Resolve
  Node-->>Registry: assigned to Chat
  Registry->>Chat: Resolve
  Chat-->>Registry: Return URL
  Registry-->>Client: Chat Service URL
```

### 2.2 Dependencies

A dependency means a service will only be considered ready when all the services it depends on are healthy.

| Service | Readiness Gate |
|---------|-------------|
| `Maukerja-Server` | `V3-API-BE` AND `BE-Chat-Health` must be AVAILABLE |
| `FE-Chat-Health-Node-Proxy` | `BE-Chat-Health` must be AVAILABLE |
| `FE-Chat-Health-Apache-Proxy` | `FE-Chat-Health-Node-Proxy` must be AVAILABLE |
| `BE-Chat-Health` | No dependencies (always ready if AVAILABLE) |
| `V3-API-BE` | No dependencies (always ready if AVAILABLE) |

## 3. Health Checking

A background daemon thread wakes up every 5 seconds and probes each registered service URL. The request includes real browser headers to bypass CloudFlare bot detection such as with `user-agent` or `upgrade-insecure-requests`.

```mermaid
flowchart TD
  A[Start Health Check Thread] --> B{Is there a registered service?}
  B -->|Yes| C[Pick next service]
  C --> D[HTTP GET /health with browser headers]
  D --> E{Status Code 200?}
  E -->|Yes| F[Mark AVAILABLE + healthy=True]
  E -->|No| G[Mark DOWN + healthy=False]
  G --> H[Increment failure_requests]
  F --> I{More services?}
  G --> I
  I -->|Yes| C
  I -->|No| J[Sleep 5 seconds]
  J --> B
  B -->|No| K[Wait...]
```

## 3.1 Thread Safety

Because the health check runs on a background daemon thread while API handlers run on Flask's request threads, shared mutable state needs protection from concurrent access. Every `ServiceRegistry` instance holds a single `threading.Lock` from context manager that guards:

- `registered_services`: all reads, writes, and existence checks acquire the lock
- `service_tracing`: counter updates for total, success, and failure requests

The lock is acquired via the `with self._lock` context manager so it's always released, even when an exception propagates. Every public method that reads or mutates registry state follows this pattern. Apart from that, there are critical sections that required recent fixes, those are:

- Look up, health check, and return now all happen inside a single critical section. Previously the return sat outside the lock, creating a race where a concurrent `deregister_service` could delete the key between the check and the access
- The existence guard and the state mutation (`availability`, `healthy`, `failure_requests`) are now covered by the same lock. Previously only the guard was locked, leaving a race window for the mutation

The `CircuitBreaker` class uses a separate dedicated lock to guard the circuit state transitions of circuit breaker alongside `failure_counts`. This is intentionally split from the registry lock to avoid unnecessary contention such as when circuit state and registry state are independent concerns

## 4. Circuit Breaker

Every health check call is wrapped in a circuit breaker with:

- **Threshold:** 3 consecutive failures before opening the circuit
- **Timeout:** 5 seconds in OPEN state before trying again (`HALF_OPEN`)

```mermaid
stateDiagram-v2
  [*] --> CLOSED
  CLOSED --> OPEN : 3 failures
  OPEN --> HALF_OPEN : after 5s timeout
  HALF_OPEN --> CLOSED : 1 success
  HALF_OPEN --> OPEN : failure
  CLOSED --> CLOSED : success
```

When the circuit is **OPEN**, any further request returns `None` immediately without touching the network. This prevents cascading overload on an already failing downstream.

## 5. Request Tracing

When you simulate a call with `POST /api/services/<name>/call`, the registry increments global counters:

- `total_requests`
- `successful_requests` (always true for simulation)
- `failure_requests`
- `duration` (cumulative)

```mermaid
flowchart LR
  A[Client] -->|POST /call| B[Service Registry]
  B --> C[Trace Service Request]
  C --> D[total_requests += 1]
  C --> E[successful_requests += 1]
  C --> F[duration += 0.5s]
  B -->|200 OK| G[Metrics Updated]
```

## 6. Event History (SQLite Persistence)

The registry keeps runtime state in memory for speed, but that state vanishes on restart. To preserve an audit trail of what happened, every meaningful operation now calls `record_event()` in `metrics.py`, which writes to a local SQLite database (`metrics_history.db`).

### How It Works

Each public operation that mutates or queries registry state triggers a single `INSERT` into the `service_events` table. The row stores a Unix epoch timestamp, the service name, an event type, and a free-text detail string. Because SQLite is embedded, there is no separate server process, thus the database file lives alongside the application

### Transaction Safety

SQLite itself is thread-safe for reads, but concurrent writes can deadlock or corrupt the journal if multiple threads commit at the exact same moment. To avoid this, all write paths acquire a dedicated `threading.Lock` before opening a connection. This serialises inserts so only one thread can commit at a single time

The database is opened in **WAL (Write-Ahead Logging) mode**. WAL allows readers to proceed while a writer is appending to the log, so the `GET /api/history` endpoint never blocks on an active `record_event()` call.

### Event Types

| Event Type | Triggered By | Detail Example |
|---|---|---|
| `service_registered` | `register_services()` | URL of the registered service |
| `service_deregistered` | `deregister_service()` | Name of the deregistered service |
| `service_assigned` | `assign_service()` | `"ServiceA assigned to ServiceB"` |
| `service_failure` | `simulate_service_is_unhealthy()` | `"simulated failure"` (only on state transition) |
| `request_traced` | `trace_service_request()` | Name of the traced service |
| `dependency_registered` | `register_dependency()` | `"ServiceA depends on ServiceB"` |
| `health_check_healthy` | `_simulate_health_check()` | `"state changed to AVAILABLE"` (only on transition) |
| `health_check_unhealthy` | `_simulate_health_check()` | `"state changed to DOWN"` (only on transition) |

### Sequence Diagram

```mermaid
sequenceDiagram
    participant Client as HTTP Client
    participant Flask as Flask API
    participant Registry as ServiceRegistry
    participant Metrics as metrics.py (SQLite)
    participant DB as metrics_history.db

    Client->>Flask: POST /api/services (register)
    Flask->>Registry: register_services()
    Registry->>Metrics: record_event("service_registered")
    Metrics->>DB: INSERT with WAL mode
    DB-->>Metrics: OK
    Metrics-->>Registry: done
    Registry-->>Flask: return
    Flask-->>Client: 201 Created

    Client->>Flask: GET /api/history
    Flask->>Metrics: get_events(service_name, event_type, limit)
    Metrics->>DB: SELECT with filters
    DB-->>Metrics: rows
    Metrics-->>Flask: events list
    Flask-->>Client: JSON array
```

## 7. Simulating Failures

You can force a service into the `DOWN` state with `POST /api/services/<name>/fail`. This is quite straightforward and pretty useful for testing how upstream services react when a downstream dependency disappears. Since, the main sources of the Chat services were invoked through different party

```mermaid
sequenceDiagram
  participant Client
  participant Registry
  participant Downstream

  Client->>Registry: POST /api/services/Maukerja-Server/fail
  Registry->>Registry: Mark as DOWN + healthy=False
  Registry-->>Client: 200 OK
  Client->>Registry: GET /api/services/Maukerja-Server/ready
  Registry->>Registry: Check dependencies
  Registry-->>Client: 503 Not Ready
```

## 8. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Registry self-health |
| `GET` | `/api/external-health` | Health of all downstream services |
| `POST` | `/api/services` | Register a new service |
| `GET` | `/api/services` | List all registered services |
| `GET` | `/api/service/:name` | Resolve a service URL (follows assignments) |
| `POST` | `/api/services/assign` | Assign one service to another |
| `POST` | `/api/services/:name/fail` | Mark a service as unhealthy |
| `POST` | `/api/services/:name/call` | Trace a request to a service |
| `GET` | `/api/services/:name/ready` | Check if service is ready (deps healthy) |
| `POST` | `/api/dependencies` | Register a dependency |
| `GET` | `/api/metrics` | Read request tracing counters |
| `GET` | `/api/history` | Query event history (params: `service_name`, `event_type`, `limit`) |
| `DELETE` | `/api/services/:name` | Deregister a service |

## 9. Data Flow Summary

```mermaid
flowchart TB
  subgraph "Application"
    A[Flask App]
    B[ServiceRegistryManagement]
    C[Health Check Thread]
    E[Metrics (SQLite)]
  end

  subgraph "Downstream Services"
    D1["Maukerja-Server"]
    D2["V3-API-BE"]
    D3["BE-Chat-Health"]
    D4["FE-Chat-Health-Node-Proxy"]
    D5["FE-Chat-Health-Apache-Proxy"]
  end

  A -->|Register / Assign / Depend| B
  C -->|HTTP GET every 5s| D1
  C -->|HTTP GET every 5s| D2
  C -->|HTTP GET every 5s| D3
  C -->|HTTP GET every 5s| D4
  C -->|HTTP GET every 5s| D5
  B -->|Metrics| A
  B -->|Event History| E
  A -->|Query| E
```

## 10. Caveats

At the moment, there were a few items that needed to be addressed before they were going to be adopted or at least made as production-grade ready. Those are:

- **No async support**. By all means, the service assignment is synchronous and resolves to the first available index. If that service is also unhealthy, no fallback will be attempted automatically
- **Hybrid state model**. The core registry (service registrations, assignments, health status) remains in-memory for performance and it's ephemeral. However, event history is persisted to a local SQLite database that survives restarts. The two layers are intentionally separated: fast in-memory state for runtime operations, durable SQLite storage for audit and observability
- **Single instance**. No clustering or leader election is implemented

## 11. Getting Started

```bash
# Start the server
python app.py

# Register a new downstream service
curl -X POST http://localhost:5000/api/services \
  -H "Content-Type: application/json" \
  -d '{"service_name": "MyAPI", "service_url": "https://api.example.com/health"}'

# Assign it to a fallback
curl -X POST http://localhost:5000/api/services/assign \
  -H "Content-Type: application/json" \
  -d '{"service_name": "MyAPI", "assigned_service": "V3-API-BE"}'

# Trace a request
curl -X POST http://localhost:5000/api/services/MyAPI/call

# See metrics
curl http://localhost:5000/api/metrics
```

## 12. History & Origin

This library was initially built as part of the research and development team's effort to implement distributed tracing, alongside tools like Jaeger and OpenTelemetry. Development began in 2023 by myself as an internal exploration into service mesh patterns and self-healing architectures.

Initially, the team did not adopt Jaeger or OpenTelemetry back in 2021. However, by the end of 2023, both tracing systems were eventually adopted across the broader platform, and this experimental library was gradually shelved and postponed

Fast forward to 2026: the chat services needed to become fully independent and required their own lightweight monitoring system. In June 2026, this library resurfaced. The Backend and Frontend teams decided to run live experiments with it as a dedicated health-check and service-assignment layer for the chat infrastructure, reviving the original codebase and extending it with real downstream services

## 13. Production Deployment (24/7)

The repository includes a Docker Compose setup designed for continuous operation.

### 13.1 Docker Compose Stack

| File | Purpose |
|------|---------|
| `Dockerfile` | Python 3.12 slim image with Gunicorn as the WSGI server. Copies `app.py`, `config.py`, `metrics.py`, `utils.py`, `services.py`, and `service_registry.py`. Installs `libsqlite3-0` as a system dependency for SQLite support |
| `docker-compose.yml` | Orchestrates the container with restart policy and health checks |
| `requirements.txt` | Pins Flask, Requests, and Gunicorn versions |
| `.dockerignore` | Keeps the image lean |

### 13.2 Key Production Settings

- **Gunicorn** runs with 4 workers and a 120-second timeout to handle slow downstream responses.
- **Restart policy** is set to `always` so the container recovers automatically after a host reboot or crash.
- **Health check** pings `/api/health` every 30 seconds; Docker restarts the container if it fails 3 times in a row.
- **Resource limits** are capped at 1 CPU and 512 MB RAM to prevent a runaway process from starving the host.
- **Flask** runs with `debug=False` and `threaded=True` for safe concurrent request handling.

### 13.3 Deploy

```bash
# Build and start
docker compose up --build -d

# View logs
docker compose logs -f

# Restart after code changes
docker compose down && docker compose up --build -d
```

### 13.4 Monitoring

Because the library is in-memory, you should monitor the host itself:

- **Container uptime** via Docker health status
- **CPU / memory** via `docker stats` or host metrics
- **Downstream health** via the `/api/external-health` endpoint (poll every 60s)
- **Request metrics** via `/api/metrics` (total, success, failure counts)

## 14. Future Considerations

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