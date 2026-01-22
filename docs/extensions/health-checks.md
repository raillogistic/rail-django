# Health Checks

Rail Django exposes standard health check endpoints for load balancers and monitoring systems.

## Endpoints

If enabled in `urls.py`:

*   `/health/live`: Returns 200 OK if the app is running.
*   `/health/ready`: Returns 200 OK if the app is ready to accept traffic (DB is connected, etc.).
*   `/health/check/`: Simple status check (returns 200 or 503).
*   `/health/api/`: JSON endpoint for dashboard data.

## Setup

Add the URLs to your project's `urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    # ...
    path("health/", include("rail_django.health_urls")),
]
```

## Example Responses

### Liveness Probe (`/health/live`)
Checks if the Python process is up.

```json
{"status": "ok", "hostname": "server-1"}
```

### Readiness Probe (`/health/ready`)
Checks database connectivity and cache.

```json
{
  "status": "ok", 
  "database": "connected", 
  "cache": "connected" 
}
```

If the DB is down, it returns `503 Service Unavailable`.

```json
{
  "status": "error",
  "database": "disconnected"
}
```

## Usage with cURL

```bash
# Check if alive
curl -f http://localhost:8000/health/live

# Check if ready (e.g. in Kubernetes probe)
curl -f http://localhost:8000/health/ready
```