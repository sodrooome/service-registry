# Configuration

The service registry is configured through a combination of environment variables and a `config.py` module.

## Environment Variables (`.env`)

The application loads configuration from a `.env` file via `python-dotenv`. Each variable is the URL of a downstream service that the registry will pre-register and monitor. As for example just like in the [architecture](architecture.md) documentation, the registry will monitor the health of the main MauKerja chat service and such, so the required environment variables are:

### Required Variables

| Variable | Description |
|----------|-------------|
| `MAUKERJA_SERVER` | URL of the main MauKerja backend API health endpoint |
| `V3_API_BE` | URL of the V3 API backend health endpoint |
| `BE_CHAT_HEALTH` | URL of the backend chat service health endpoint |
| `FE_CHAT_HEALTH_NODE_PROXY` | URL of the Node.js proxy health endpoint |
| `FE_CHAT_HEALTH_APACHE_PROXY` | URL of the Apache reverse proxy health endpoint |

### Example configuration in `.env`

```bash
MAUKERJA_SERVER=https://maukerja.example.com/health
V3_API_BE=https://v3-api.example.com/health
BE_CHAT_HEALTH=https://chat.example.com/health
FE_CHAT_HEALTH_NODE_PROXY=https://node-proxy.example.com/health
FE_CHAT_HEALTH_APACHE_PROXY=https://apache-proxy.example.com/health
```

!!! warning
    Make sure to replace the example URLs with the actual service endpoints you want to monitor. The registry will attempt to register these services on startup and perform health checks against them.

## `config.py`

The `config.py` module loads the environment variables and defines two key exports:

### `DEFAULT_HEADERS`

A dictionary of HTTP headers used for health-check requests. These mimic a real browser to bypass CloudFlare bot protection:

```python
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) ...",
    "Accept": "text/html,application/xhtml+xml,...",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}
```

!!! tip
    If your downstream services use a different protection mechanism, you can modify these headers in `config.py` or pass custom headers via the `check_downstream_health()` utility function.

### `DOWNSTREAM_SERVICES`

A dictionary mapping service names to their URLs, populated from environment variables:

```python
DOWNSTREAM_SERVICES = {
    "Maukerja-Server": os.getenv("MAUKERJA_SERVER"),
    "V3-API-BE": os.getenv("V3_API_BE"),
    "BE-Chat-Health": os.getenv("BE_CHAT_HEALTH"),
    "FE-Chat-Health-Node-Proxy": os.getenv("FE_CHAT_HEALTH_NODE_PROXY"),
    "FE-Chat-Health-Apache-Proxy": os.getenv("FE_CHAT_HEALTH_APACHE_PROXY"),
}
```

## Runtime Configuration

### Health Check Interval

The background health-check thread runs every **5 seconds** by default. This is defined in `ServiceRegistry.health_check_interval` and can be changed at runtime:

```python
registry.health_check_interval = 10  # every 10 seconds
```

### Circuit Breaker Settings

The `CircuitBreaker` class accepts two parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `threshold` | 3 | Consecutive failures before the circuit opens |
| `timeout` | 5 | Seconds to stay in OPEN state before transitioning to HALF_OPEN |

These thresholds are applied per-service via the `@circuit_breaker` decorator in `_simulate_health_check()`.

### SQLite Database

The event history is stored in a local SQLite database:

| Setting | Value |
|---------|-------|
| **File path** | `metrics_history.db` (in the working directory) |
| **Journal mode** | WAL (Write-Ahead Logging) |
| **Write lock** | `threading.Lock` for serialised inserts |
| **Table** | `service_events` |

The database file is created automatically on first import of `metrics.py`. You can change the path by modifying the `DB_PATH` variable in `metrics.py`.
