"""The job queue: a small interface and a SQLite implementation with leases.

Delivery is at-least-once. A worker leases a job for `lease_seconds`; if it crashes, the lease
expires and another worker picks the job up. Every state change on a job checks the lease token
(a fencing token), so a worker that lost its lease can't complete or retry a job it no longer owns.

Swapping in Redis or SQS means writing another class with these five methods. See the README.
"""

import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from app.db import Database, dumps, loads, now


class LeaseLost(Exception):
    """The job's lease expired and was taken by another worker."""


@dataclass(frozen=True)
class Job:
    id: int
    kind: str
    payload: dict[str, Any]
    idempotency_key: str
    attempts: int
    lease_token: str


class Queue(Protocol):
    def enqueue(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        key: str,
        delay: float = 0.0,
        tx: sqlite3.Connection | None = None,
    ) -> bool:
        """Add a job. Returns False when a job with the same key already exists."""
        ...

    def lease(self, worker_id: str) -> Job | None:
        """Take the next ready job, or None when the queue is idle."""
        ...

    def complete(self, job: Job, *, tx: sqlite3.Connection | None = None) -> None: ...

    def retry(
        self, job: Job, *, delay: float, error: str, tx: sqlite3.Connection | None = None
    ) -> None: ...

    def bury(self, job: Job, *, error: str, tx: sqlite3.Connection | None = None) -> None:
        """Give up on a job (dead letter)."""
        ...


class SqliteQueue:
    def __init__(self, db: Database, *, lease_seconds: float = 30.0) -> None:
        self.db = db
        self.lease_seconds = lease_seconds

    def _write(self, tx: sqlite3.Connection | None, sql: str, params: tuple[Any, ...]) -> int:
        if tx is not None:
            return tx.execute(sql, params).rowcount
        with self.db.tx() as conn:
            return conn.execute(sql, params).rowcount

    def enqueue(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        key: str,
        delay: float = 0.0,
        tx: sqlite3.Connection | None = None,
    ) -> bool:
        t = now()
        inserted = self._write(
            tx,
            """INSERT INTO jobs (kind, payload, idempotency_key, status, run_at, created_at,
                                 updated_at)
               VALUES (?, ?, ?, 'queued', ?, ?, ?)
               ON CONFLICT (idempotency_key) DO NOTHING""",
            (kind, dumps(payload), key, t + delay, t, t),
        )
        return inserted == 1

    def lease(self, worker_id: str) -> Job | None:
        t = now()
        token = uuid.uuid4().hex
        with self.db.tx() as conn:
            row = conn.execute(
                """UPDATE jobs
                   SET status = 'leased', lease_owner = ?, lease_token = ?,
                       lease_expires_at = ?, attempts = attempts + 1, updated_at = ?
                   WHERE id = (
                       SELECT id FROM jobs
                       WHERE (status = 'queued' AND run_at <= ?)
                          OR (status = 'leased' AND lease_expires_at < ?)
                       ORDER BY run_at, id
                       LIMIT 1
                   )
                   RETURNING id, kind, payload, idempotency_key, attempts, lease_token""",
                (worker_id, token, t + self.lease_seconds, t, t, t),
            ).fetchone()
        if row is None:
            return None
        return Job(
            id=row["id"],
            kind=row["kind"],
            payload=loads(row["payload"]),
            idempotency_key=row["idempotency_key"],
            attempts=row["attempts"],
            lease_token=row["lease_token"],
        )

    def _fenced(self, tx: sqlite3.Connection | None, job: Job, set_sql: str, *args: Any) -> None:
        changed = self._write(
            tx,
            f"UPDATE jobs SET {set_sql}, lease_owner = NULL, lease_token = NULL, "
            "lease_expires_at = NULL, updated_at = ? "
            "WHERE id = ? AND status = 'leased' AND lease_token = ?",
            (*args, now(), job.id, job.lease_token),
        )
        if changed != 1:
            raise LeaseLost(f"job {job.id} is no longer leased by this worker")

    def complete(self, job: Job, *, tx: sqlite3.Connection | None = None) -> None:
        self._fenced(tx, job, "status = 'done'")

    def retry(
        self, job: Job, *, delay: float, error: str, tx: sqlite3.Connection | None = None
    ) -> None:
        self._fenced(tx, job, "status = 'queued', run_at = ?, last_error = ?", now() + delay, error)

    def bury(self, job: Job, *, error: str, tx: sqlite3.Connection | None = None) -> None:
        self._fenced(tx, job, "status = 'dead', last_error = ?", error)

    def stats(self) -> dict[str, int]:
        rows = self.db.query("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")
        return {r["status"]: r["n"] for r in rows}
