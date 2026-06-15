"""
Lightweight SQLite store for service registry management events

This is intended separating between service registry which used in-memory state and Flask's service
- core service registry stays in-memory since it's fast, ephemeral and reset friendly
- while this module will persist a history of what have happened regarding failures/success metrics
"""

import sqlite3
import threading
import time
from contextlib import contextmanager

# by default set this name
DB_PATH = "metrics_history.db"
DB_SCHEMA = """CREATE TABLE IF NOT EXISTS service_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    service_name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT
);
 
CREATE INDEX IF NOT EXISTS idx_service_events_service_name
    ON service_events (service_name);
 
CREATE INDEX IF NOT EXISTS idx_service_events_event_type
    ON service_events (event_type);
 
CREATE INDEX IF NOT EXISTS idx_service_events_timestamp
    ON service_events (timestamp);
"""

# allow concurrent reads but only single writes
_write_lock = threading.Lock()


@contextmanager
def _init_connection():
    conection = sqlite3.connect(DB_PATH, timeout=10)
    try:
        # enables WAL mode so it can performed concurrently
        conection.execute("PRAGMA journal_mode=WAL")
        yield conection
    finally:
        conection.close()


def init_database() -> None:
    with _write_lock, _init_connection() as conn:
        conn.executescript(DB_SCHEMA)
        conn.commit()


init_database()


def record_event(service_name: str, event_type: str, detail: str) -> None:
    with _write_lock, _init_connection() as conn:
        conn.execute(
            "INSERT INTO service_events (timestamp, service_name, event_type, detail) "
            "VALUES (?, ?, ?, ?)",
            (time.time(), service_name, event_type, detail),
        )
        conn.commit()


def get_events(service_name: str, event_type: str, limit: int = 100) -> list:
    """Read events based on the recent first"""
    query = "SELECT timestamp, service_name, event_type, detail FROM service_events"
    conditions = []
    params = []

    if service_name:
        conditions.append("service_name = ?")
        params.append(service_name)

    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with _init_connection() as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

    events = []
    for row in rows:
        events.append(
            {
                "timestamp": row[0],
                "service_name": row[1],
                "event_type": row[2],
                "detail": row[3],
            }
        )
    return events
