# Getting Started

## Installation

### Prerequisites

- Python 3.10+
- pip
- (Optional) Docker and Docker Compose for containerized deployment

### Clone the Repository

This library is not published on PyPI, so you'll need to clone it directly:

```bash
git clone https://github.com/sodrooome/service-registry.git
cd service-registry
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

The `requirements.txt` pins four critical dependencies for the service registry:

| Package | Version | Purpose |
|---------|---------|---------|
| `Flask` | >=2.0.0 | Web framework for the REST API |
| `requests` | >=2.28.0 | HTTP client for health-check probes |
| `gunicorn` | >=21.0.0 | Production WSGI server |
| `python-dotenv` | 1.2.2 | Load `.env` files for configuration |

## Configuration

After installing dependencies, you need to tell the service registry which downstream services to monitor.

### Option A: Using a `.env` file (recommended)

Create a `.env` file in the project root. It's already ignored in `.gitignore`, so secrets stay local:

```bash
touch .env
```

Add your actual service URLs:

```bash
MAUKERJA_SERVER=https://your-api.example.com/health
V3_API_BE=https://v3-api.example.com/health
BE_CHAT_HEALTH=https://chat.example.com/health
FE_CHAT_HEALTH_NODE_PROXY=https://node-proxy.example.com/health
FE_CHAT_HEALTH_APACHE_PROXY=https://apache-proxy.example.com/health
```

These map directly to the `DOWNSTREAM_SERVICES` dictionary in [`config.py`](./configuration.md).

### Option B: Hardcoded URLs directly in `config.py`

If you prefer not to use a `.env` file, open [`config.py`](https://github.com/sodrooome/service-registry/blob/main/config.py) and replace the environment variable lookups with your actual URLs:

```python
DOWNSTREAM_SERVICES = {
    "My-Service-Name": "https://my-service.example.com/health",
    "Another-Service": "https://another-service.example.com/health",
}
```

You can add, remove, or rename services here as needed. The service name you choose will be used throughout the API or when you interact with the registry endpoints.

### Customising Assignments & Dependencies

Once your services are configured, open [`services.py`](https://github.com/sodrooome/service-registry/blob/main/services.py). This file wires everything together at startup:

1. **Service Registration**. Each service from `DOWNSTREAM_SERVICES` is registered automatically in the downstream service loop.

2. **Service Assignment**. Use assign service method from the core registry module to chain services. For example, if `Frontend-Proxy` should route to `Backend-API`:

    ```python
    registry.assign_service(
        service_name="Frontend-Proxy",
        assigned_service_name="Backend-API",
    )
    ```

    When you resolve `Frontend-Proxy` via the API, it will return `Backend-API`'s URL instead.

3. **Dependencies**. Use register dependencies method to define readiness gates. A service is only "ready" when all its dependencies are healthy:

    ```python
    registry.register_dependency(
        service_name="Frontend-Proxy",
        depends_on="Backend-API",
    )
    ```

    You can add multiple dependencies for the same service:

    ```python
    registry.register_dependency(
        service_name="Main-Backend",
        depends_on="Database-API",
    )
    registry.register_dependency(
        service_name="Main-Backend",
        depends_on="Cache-Service",
    )
    ```

!!! tip
    Edit `services.py` to reflect your actual topology. The MauKerja chat services in the file are just examples. Replace them with your own service names, assignments, and dependencies.

## Running the Server

### Development (Flask built-in server)

```bash
python app.py
```

The server starts on `http://0.0.0.0:5000` by default.

### Production (Gunicorn)

```bash
gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 120 app:app
```

## Running Standalone (Without Flask)

You can also run the service registry logic directly without the Flask API:

```bash
python service_registry.py
```

This runs the built-in demo that registers mock services from `config.py`, performs assignments, and prints live log output.

## Basic Usage

### Register a Service

```bash
curl -X POST http://localhost:5000/api/services \
  -H "Content-Type: application/json" \
  -d '{"service_name": "MyAPI", "service_url": "https://api.example.com/health"}'
```

### List All Services

```bash
curl http://localhost:5000/api/services
```

### Resolve a Service URL

```bash
curl http://localhost:5000/api/service/MyAPI
```

### Simulate a Failure

```bash
curl -X POST http://localhost:5000/api/services/MyAPI/fail
```

### Check Event History

```bash
curl http://localhost:5000/api/history
```

### View Tracing Metrics

```bash
curl http://localhost:5000/api/metrics
```

## Run with Makefile

A `Makefile` is provided for convenience to spin up the server using Docker compose stack

```bash
make build   # docker compose build
make run     # docker compose up -d
make stop    # docker compose down
make logs    # docker compose logs -f
```
