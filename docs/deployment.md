# Deployment

The repository includes everything needed for 24/7 production deployment using Docker and Gunicorn.

## Production Stack

| Component | Technology |
|-----------|------------|
| **Application server** | Gunicorn (WSGI) |
| **Web framework** | Flask |
| **Container runtime** | Docker + Docker Compose |
| **Event storage** | SQLite (embedded, file-based) |

## Dockerfile

The `Dockerfile` builds a Python 3.12 slim image:

- Installs system dependencies: `libsqlite3-0` (for SQLite support) and `curl` (for health checks)
- Copies application code: `app.py`, `config.py`, `metrics.py`, `utils.py`, `services.py`, `service_registry.py`
- Runs Gunicorn with 4 workers and a 120-second timeout

```dockerfile
--8<-- "Dockerfile"
```

## Docker Compose

The `docker-compose.yml` orchestrates the container with production-grade settings:

### Key Settings

| Setting | Value | Purpose |
|---------|-------|---------|
| **Restart policy** | `always` | Auto-recover after host reboot or crash |
| **Health check** | `curl http://localhost:5000/api/health` every 30s, 3 retries | Docker restarts if unhealthy |
| **CPU limit** | 1.0 core | Prevent runaway process from starving the host |
| **Memory limit** | 512 MB | Hard cap on memory usage |
| **CPU reservation** | 0.25 cores | Guaranteed minimum CPU |
| **Memory reservation** | 128 MB | Guaranteed minimum memory |

```yaml
--8<-- "docker-compose.yml"
```

## Deploying

### Build and Start

```bash
docker compose up --build -d
```

### View Logs

```bash
docker compose logs -f
```

### Restart After Code Changes

```bash
docker compose down && docker compose up --build -d
```

### Using Makefile

```bash
make build    # docker compose build
make run      # docker compose up -d
make stop     # docker compose down
make logs     # docker compose logs -f
```

## Monitoring

Because the core registry state is in-memory, monitoring the host system is important:

| What to Monitor | How |
|----------------|-----|
| **Container uptime** | Docker health status (`docker ps`) |
| **CPU / memory** | `docker stats` or host-level metrics |
| **Downstream health** | Poll `/api/external-health` every 60s |
| **Request metrics** | Poll `/api/metrics` for total/success/failure counts |
| **Event history** | Poll `/api/history` for audit trail |

## Caveats

While this stack is production-ready for a lightweight service registry, it has limitations that may require future enhancements:

- **No async support.** Service assignment is synchronous and resolves to the first available index. No automatic fallback.
- **Hybrid state model.** Core state (registrations, assignments, health) is in-memory and ephemeral. Only event history is persisted to SQLite.
- **Single instance.** No clustering or leader election is implemented.
