# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

# Prevent Python from writing .pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system runtime libraries (libsqlite3-0 for Python's built-in sqlite3 module)
RUN apt-get update && apt-get install -y --no-install-recommends libsqlite3-0 curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py config.py metrics.py utils.py services.py service_registry.py ./

# Expose Flask port
EXPOSE 5000

# Use gunicorn for production-grade 24/7 operation
# --bind 0.0.0.0:5000     -> listen on all interfaces inside container
# --workers 4             -> 4 worker processes (adjust based on CPU cores)
# --timeout 120           -> 2 min timeout for long health checks
# --access-logfile        -> log to stdout
# --error-logfile         -> log errors to stdout
# --capture-output        -> capture stdout/stderr from workers
# --enable-stdio-inheritance -> forward worker logs
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "--capture-output", "--enable-stdio-inheritance", "app:app"]