# API Reference

The service registry exposes a REST API via Flask. All endpoints are prefixed with `/api`.

## Endpoint Quick Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Registry self-health check |
| `GET` | `/api/external-health` | Health of all downstream services |
| `POST` | `/api/services` | Register a new service |
| `GET` | `/api/services` | List all registered services |
| `GET` | `/api/service/{name}` | Resolve a service URL (follows assignments) |
| `POST` | `/api/services/assign` | Assign one service to another |
| `POST` | `/api/services/{name}/fail` | Mark a service as unhealthy |
| `POST` | `/api/services/{name}/call` | Simulate and trace a request |
| `GET` | `/api/services/{name}/ready` | Check if a service is ready |
| `POST` | `/api/dependencies` | Register a dependency between services |
| `GET` | `/api/metrics` | Read request tracing counters |
| `GET` | `/api/history` | Query event history from SQLite |
| `DELETE` | `/api/services/{name}` | Deregister a service |

---

## Registry Health

### `GET /api/health`

Returns the registry's own health status. Used by Docker health checks.

**Response `200 OK`:**

```json
{
  "status": "OK"
}
```

---

## Downstream Health

### `GET /api/external-health`

Probes every registered downstream service URL with browser-grade headers and returns per-service status.

**Response `200 OK`:**

```json
{
  "status": "healthy",
  "timestamp": 1718000000000,
  "services": [
    {
      "name": "Maukerja-Server",
      "url": "https://maukerja.example.com/health",
      "status_code": 200,
      "healthy": true,
      "response": { ... }
    }
  ]
}
```

The `status` field is one of:

| Value | Meaning |
|-------|---------|
| `healthy` | All services returned 200 |
| `degraded` | At least one service returned 200 |
| `unhealthy` | No services returned 200 |

---

## Service Registration

### `POST /api/services`

Register a new downstream service.

**Request body:**

```json
{
  "service_name": "MyAPI",
  "service_url": "https://api.example.com/health"
}
```

**Response `201 Created`:**

```json
{
  "message": "service registered"
}
```

**Response `400 Bad Request`:**

```json
{
  "error": "Service already registered, please use another service name"
}
```

---

### `GET /api/services`

List all registered services with their current state.

**Response `200 OK`:**

```json
{
  "MyAPI": {
    "url": "https://api.example.com/health",
    "assigned": false,
    "assigned_service": null,
    "availability": "AVAILABLE"
  }
}
```

---

### `GET /api/service/{name}`

Resolve the URL for a given service. Follows assignment chains transparently — if `ServiceA` is assigned to `ServiceB`, this returns `ServiceB`'s URL.

**Response `200 OK`:**

```json
{
  "service_name": "MyAPI",
  "url": "https://api.example.com/health"
}
```

**Response `404 Not Found`:**

```json
{
  "error": "There's no available service"
}
```

---

### `DELETE /api/services/{name}`

Deregister a service and remove its circuit breaker state.

**Response `200 OK`:**

```json
{
  "message": "service deregistered"
}
```

**Response `404 Not Found`:**

```json
{
  "error": "Service name is not registered in the list of service register"
}
```

---

## Service Assignment

### `POST /api/services/assign`

Assign one service to another. When the source service is looked up, the registry returns the assigned service's URL instead.

**Request body:**

```json
{
  "service_name": "MyAPI",
  "assigned_service": "V3-API-BE"
}
```

**Response `200 OK`:**

```json
{
  "message": "Successfully assigned particular service"
}
```

---

## Failure Simulation

### `POST /api/services/{name}/fail`

Force a service into the `DOWN` state. Useful for testing how upstream services react when a downstream dependency disappears.

**Response `200 OK`:**

```json
{
  "message": "marked this service is unhealthy"
}
```

---

## Request Tracing

### `POST /api/services/{name}/call`

Simulate a request to a service. Records the trace in in-memory counters and persists an event to SQLite.

**Response `200 OK`:**

```json
{
  "message": "Request traced successfully"
}
```

---

## Readiness Check

### `GET /api/services/{name}/ready`

Check if a service is ready based on its dependency graph. A service is ready only when all services it depends on are `AVAILABLE`.

**Response `200 OK`:**

```json
{
  "message": "Service is ready"
}
```

**Response `503 Service Unavailable`:**

```json
{
  "message": "Service is not ready"
}
```

---

## Dependencies

### `POST /api/dependencies`

Register a dependency between services. Once registered, the dependent service's readiness is gated on its dependencies being healthy.

**Request body:**

```json
{
  "service_name": "MyAPI",
  "depends_on": "V3-API-BE"
}
```

**Response `201 Created`:**

```json
{
  "message": "Dependency registered successfully"
}
```

---

## Metrics

### `GET /api/metrics`

Read the in-memory request tracing counters aggregated across all services.

**Response `200 OK`:**

```json
{
  "total_requests": 42,
  "successful_requests": 40,
  "failure_requests": 2,
  "duration": 21.5
}
```

---

## Event History

### `GET /api/history`

Query the SQLite-persisted event history. Supports optional filters.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `service_name` | string | — | Filter by service name |
| `event_type` | string | — | Filter by event type |
| `limit` | integer | 100 | Maximum number of events to return |

**Example requests:**

```bash
# All events
curl http://localhost:5000/api/history

# Events for a specific service
curl "http://localhost:5000/api/history?service_name=MyAPI"

# Events of a specific type
curl "http://localhost:5000/api/history?event_type=service_failure"

# Last 5 events
curl "http://localhost:5000/api/history?limit=5"
```

**Response `200 OK`:**

```json
[
  {
    "timestamp": 1718000000.123,
    "service_name": "MyAPI",
    "event_type": "service_registered",
    "detail": "https://api.example.com/health"
  },
  {
    "timestamp": 1718000010.456,
    "service_name": "MyAPI",
    "event_type": "health_check_healthy",
    "detail": "state changed to AVAILABLE"
  }
]
```

### Event Types

| Event Type | Trigger | Detail |
|---|---|---|
| `service_registered` | Service registration | URL of the registered service |
| `service_deregistered` | Service deregistration | Name of the deregistered service |
| `service_assigned` | Service assignment | `"ServiceA assigned to ServiceB"` |
| `service_failure` | Simulated failure | `"simulated failure"` |
| `request_traced` | Request simulation | Name of the traced service |
| `dependency_registered` | Dependency registration | `"ServiceA depends on ServiceB"` |
| `health_check_healthy` | Health check → AVAILABLE | `"state changed to AVAILABLE"` |
| `health_check_unhealthy` | Health check → DOWN | `"state changed to DOWN"` |

---

## Error Responses

All endpoints return standard HTTP status codes:

| Code | Meaning |
|------|---------|
| `200` | Success |
| `201` | Created |
| `400` | Bad request (missing or invalid parameters) |
| `404` | Service not found |
| `503` | Service not ready (dependencies unhealthy) |
