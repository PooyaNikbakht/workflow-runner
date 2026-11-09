"""SQLite storage shared by the API and the worker processes.

Each process opens its own connection. WAL mode lets the API read while a worker writes, and
`BEGIN IMMEDIATE` takes the write lock up front so two workers never race on the same job.
"""

import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    workflow TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    input TEXT NOT NULL,
    error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    finished_at REAL
);
CREATE INDEX IF NOT EXISTS runs_created ON runs (created_at DESC);

CREATE TABLE IF NOT EXISTS steps (
    run_id TEXT NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    position INTEGER NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL,
    output TEXT,
    error TEXT,
    started_at REAL,
    finished_at REAL,
    next_attempt_at REAL,
    PRIMARY KEY (run_id, key)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    level TEXT NOT NULL,
    step_key TEXT,
    message TEXT NOT NULL,
    data TEXT
);
CREATE INDEX IF NOT EXISTS events_run ON events (run_id, id);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    run_at REAL NOT NULL,
    lease_owner TEXT,
    lease_token TEXT,
    lease_expires_at REAL,
    last_error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_ready ON jobs (status, run_at);

CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL UNIQUE,
    received_at REAL NOT NULL,
    last_received_at REAL NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 1,
    signature_ok INTEGER NOT NULL,
    event TEXT,
    payload TEXT NOT NULL
);
"""


def now() -> float:
    return time.time()


def dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def loads(value: str | None) -> Any:
    return None if value is None else json.loads(value)


class Database:
    """A thin wrapper around one SQLite connection with explicit write transactions."""

    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # Autocommit mode: transactions are opened explicitly with BEGIN IMMEDIATE.
        self.conn = sqlite3.connect(
            str(path), isolation_level=None, check_same_thread=False, timeout=10.0
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        # The API serves requests from a thread pool; serialize access to the connection.
        self._lock = threading.RLock()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """A write transaction. Commits on success, rolls back on any exception."""
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            self.conn.execute("COMMIT")

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(sql, params).fetchone()

    def close(self) -> None:
        self.conn.close()
