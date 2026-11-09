"""The workflow engine: creates runs, executes step jobs and records human review decisions.

The API process uses it to start runs and submit reviews. Worker processes use it to execute
the jobs they lease. Each state change, the log event that describes it, the job ack and the
enqueue of the next step are written in one SQLite transaction, so a crash at any point leaves
the run in a state the next worker can pick up from.
"""

import logging
import sqlite3
import uuid
from typing import Any

import pydantic

from app.db import Database, dumps, loads, now
from app.errors import PermanentError, StepError, TransientError
from app.models import ReviewDecision
from app.providers.base import LLM, ProviderError
from app.queue import Job, Queue
from app.states import DONE_STEP, TERMINAL_RUN, check_run, check_step
from app.webhook import WebhookSender
from app.workflows import WORKFLOWS, StepContext, WorkflowDef

logger = logging.getLogger(__name__)

STEP_JOB = "step"


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def backoff(attempt: int, base: float, cap: float) -> float:
    """Exponential backoff: base, 2x base, 4x base... capped."""
    return min(cap, base * (2 ** (attempt - 1)))


def job_key(run_id: str, step: str) -> str:
    return f"{run_id}:{step}"


class Engine:
    def __init__(
        self,
        db: Database,
        queue: Queue,
        *,
        provider: LLM | None = None,
        webhook: WebhookSender | None = None,
        retry_base: float = 2.0,
        retry_max: float = 60.0,
        step_delay: float = 0.0,
    ) -> None:
        self.db = db
        self.queue = queue
        self.provider = provider
        self.webhook = webhook
        self.retry_base = retry_base
        self.retry_max = retry_max
        self.step_delay = step_delay

    # Writes ---------------------------------------------------------------------------------

    def _event(
        self,
        tx: sqlite3.Connection,
        run_id: str,
        message: str,
        *,
        kind: str = "log",
        level: str = "info",
        step: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        tx.execute(
            "INSERT INTO events (run_id, ts, kind, level, step_key, message, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, now(), kind, level, step, message, None if data is None else dumps(data)),
        )

    def _set_step(
        self, tx: sqlite3.Connection, run_id: str, key: str, new: str, **fields: Any
    ) -> None:
        row = tx.execute(
            "SELECT status FROM steps WHERE run_id = ? AND key = ?", (run_id, key)
        ).fetchone()
        check_step(row["status"], new)
        fields["status"] = new
        if "output" in fields:
            fields["output"] = None if fields["output"] is None else dumps(fields["output"])
        sets = ", ".join(f"{k} = ?" for k in fields)
        tx.execute(
            f"UPDATE steps SET {sets} WHERE run_id = ? AND key = ?",
            (*fields.values(), run_id, key),
        )

    def _set_run(self, tx: sqlite3.Connection, run_id: str, new: str, **fields: Any) -> None:
        row = tx.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row["status"] != new:
            check_run(row["status"], new)
        fields.update(status=new, updated_at=now())
        if new in TERMINAL_RUN:
            fields["finished_at"] = now()
        sets = ", ".join(f"{k} = ?" for k in fields)
        tx.execute(f"UPDATE runs SET {sets} WHERE id = ?", (*fields.values(), run_id))

    def _touch(self, tx: sqlite3.Connection, run_id: str) -> None:
        tx.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (now(), run_id))

    def _queue_step(self, tx: sqlite3.Connection, run_id: str, key: str) -> None:
        self._set_step(tx, run_id, key, "queued")
        self.queue.enqueue(
            STEP_JOB, {"run_id": run_id, "step": key}, key=job_key(run_id, key), tx=tx
        )

    def _skip_rest(self, tx: sqlite3.Connection, run_id: str) -> None:
        tx.execute(
            "UPDATE steps SET status = 'skipped' "
            "WHERE run_id = ? AND status IN ('pending', 'queued')",
            (run_id,),
        )

    # Runs -----------------------------------------------------------------------------------

    def start_run(self, workflow_key: str, raw_input: dict[str, Any]) -> str:
        """Validate the input, persist the run and its steps, and queue the first step.

        Raises KeyError for an unknown workflow and pydantic.ValidationError for bad input.
        """
        wf = WORKFLOWS[workflow_key]
        data = wf.input_model.model_validate(raw_input)
        run_id = uuid.uuid4().hex[:12]
        t = now()
        with self.db.tx() as tx:
            tx.execute(
                "INSERT INTO runs (id, workflow, title, status, input, created_at, updated_at) "
                "VALUES (?, ?, ?, 'queued', ?, ?, ?)",
                (run_id, wf.key, wf.title(data), dumps(data.model_dump()), t, t),
            )
            for i, step in enumerate(wf.steps):
                tx.execute(
                    "INSERT INTO steps (run_id, key, position, status, max_attempts) "
                    "VALUES (?, ?, ?, 'pending', ?)",
                    (run_id, step.key, i, step.max_attempts),
                )
            self._event(tx, run_id, f"Run created for workflow {wf.name}", kind="state")
            first = wf.steps[0]
            self._queue_step(tx, run_id, first.key)
            self._event(tx, run_id, f"Queued {first.title}", kind="state", step=first.key)
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any]:
        row = self.db.one("SELECT * FROM runs WHERE id = ?", (run_id,))
        if row is None:
            raise NotFound(run_id)
        wf = WORKFLOWS[row["workflow"]]
        steps = self.db.query("SELECT * FROM steps WHERE run_id = ? ORDER BY position", (run_id,))
        last = self.db.one("SELECT MAX(id) AS id FROM events WHERE run_id = ?", (run_id,))
        return {
            "id": row["id"],
            "workflow": wf.key,
            "workflow_name": wf.name,
            "title": row["title"],
            "status": row["status"],
            "input": loads(row["input"]),
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "finished_at": row["finished_at"],
            "last_event_id": last["id"] if last else None,
            "steps": [
                {
                    "key": s["key"],
                    "title": wf.step(s["key"]).title,
                    "kind": wf.step(s["key"]).kind,
                    "description": wf.step(s["key"]).description,
                    "status": s["status"],
                    "attempts": s["attempts"],
                    "max_attempts": s["max_attempts"],
                    "output": loads(s["output"]),
                    "error": s["error"],
                    "started_at": s["started_at"],
                    "finished_at": s["finished_at"],
                    "next_attempt_at": s["next_attempt_at"],
                }
                for s in steps
            ],
        }

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.query(
            """SELECT r.id, r.workflow, r.title, r.status, r.created_at, r.finished_at,
                      (SELECT COUNT(*) FROM steps s WHERE s.run_id = r.id
                         AND s.status = 'completed') AS steps_done,
                      (SELECT COUNT(*) FROM steps s WHERE s.run_id = r.id) AS steps_total,
                      (SELECT COALESCE(SUM(MAX(s.attempts - 1, 0)), 0) FROM steps s
                         WHERE s.run_id = r.id) AS retries
               FROM runs r ORDER BY r.created_at DESC LIMIT ?""",
            (limit,),
        )
        return [
            {**dict(r), "workflow_name": WORKFLOWS[r["workflow"]].name}
            for r in rows
            if r["workflow"] in WORKFLOWS
        ]

    def events_after(self, run_id: str, after_id: int, limit: int = 500) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM events WHERE run_id = ? AND id > ? ORDER BY id LIMIT ?",
            (run_id, after_id, limit),
        )
        return [
            {
                "id": r["id"],
                "ts": r["ts"],
                "kind": r["kind"],
                "level": r["level"],
                "step": r["step_key"],
                "message": r["message"],
                "data": loads(r["data"]),
            }
            for r in rows
        ]

    def run_status(self, run_id: str) -> str | None:
        row = self.db.one("SELECT status FROM runs WHERE id = ?", (run_id,))
        return row["status"] if row else None

    # Review ---------------------------------------------------------------------------------

    def submit_review(self, run_id: str, decision: ReviewDecision) -> dict[str, Any]:
        with self.db.tx() as tx:
            run = tx.execute("SELECT workflow, status FROM runs WHERE id = ?", (run_id,)).fetchone()
            if run is None:
                raise NotFound(run_id)
            step = tx.execute(
                "SELECT key, output FROM steps WHERE run_id = ? AND status = 'needs_review'",
                (run_id,),
            ).fetchone()
            if step is None:
                # Already decided (a double click, a second tab): nothing to do.
                raise Conflict("This run isn't waiting for a review.")
            wf = WORKFLOWS[run["workflow"]]
            key = step["key"]
            proposal = loads(step["output"])["proposal"]

            if decision.decision == "reject":
                output = {"decision": "reject", "note": decision.note, "proposal": proposal}
                self._set_step(tx, run_id, key, "completed", output=output, finished_at=now())
                self._skip_rest(tx, run_id)
                self._set_run(tx, run_id, "rejected", error=None)
                note = f": {decision.note}" if decision.note else ""
                self._event(
                    tx, run_id, f"Rejected by reviewer{note}", kind="state", step=key, level="warn"
                )
                return {"status": "rejected"}

            if decision.decision == "edit":
                if decision.edits is None:
                    raise Conflict("Edits are required to save an edited version.")
                final = decision.edits.model_dump()
            else:
                final = {"subject": proposal["subject"], "body": proposal["body"]}
            edited = final["subject"] != proposal["subject"] or final["body"] != proposal["body"]
            output = {
                "decision": decision.decision,
                "edited": edited,
                "note": decision.note,
                "final": final,
                "proposal": proposal,
            }
            self._set_step(tx, run_id, key, "completed", output=output, finished_at=now())
            verb = "Approved with edits" if edited else "Approved"
            self._event(tx, run_id, f"{verb} by reviewer", kind="state", step=key)
            nxt = wf.next_step(key)
            if nxt is None:
                self._set_run(tx, run_id, "completed")
                self._event(tx, run_id, "Run completed", kind="state")
                return {"status": "completed"}
            self._set_run(tx, run_id, "running")
            self._queue_step(tx, run_id, nxt.key)
            self._event(tx, run_id, f"Queued {nxt.title}", kind="state", step=nxt.key)
            return {"status": "running"}

    # Worker side ----------------------------------------------------------------------------

    def _outputs(self, run_id: str) -> dict[str, Any]:
        rows = self.db.query(
            "SELECT key, output FROM steps WHERE run_id = ? AND status = 'completed'", (run_id,)
        )
        return {r["key"]: loads(r["output"]) for r in rows}

    def _log_now(self, run_id: str, step: str) -> Any:
        def log(message: str, *, level: str = "info", data: dict[str, Any] | None = None) -> None:
            with self.db.tx() as tx:
                self._event(tx, run_id, message, level=level, step=step, data=data)

        return log

    async def process(self, job: Job) -> str:
        """Execute one step job. Returns what happened, for logs and tests."""
        run_id, key = job.payload["run_id"], job.payload["step"]
        run = self.db.one("SELECT workflow, status, input FROM runs WHERE id = ?", (run_id,))
        step = self.db.one(
            "SELECT status, attempts, max_attempts FROM steps WHERE run_id = ? AND key = ?",
            (run_id, key),
        )
        if run is None or step is None:
            self.queue.bury(job, error="run or step not found")
            return "missing"
        # Idempotency: a redelivered job for a step that's already done is acknowledged, not rerun.
        if (
            step["status"] in DONE_STEP
            or step["status"] == "needs_review"
            or run["status"] in TERMINAL_RUN
        ):
            self.queue.complete(job)
            return "duplicate"

        wf = WORKFLOWS[run["workflow"]]
        sdef = wf.step(key)
        attempt = step["attempts"] + 1
        with self.db.tx() as tx:
            self._set_step(
                tx, run_id, key, "running", attempts=attempt, started_at=now(), next_attempt_at=None
            )
            self._set_run(tx, run_id, "running")
            suffix = f" (attempt {attempt} of {step['max_attempts']})" if attempt > 1 else ""
            self._event(tx, run_id, f"Started {sdef.title}{suffix}", kind="state", step=key)

        outputs = self._outputs(run_id)
        if sdef.kind == "review":
            proposal = outputs[sdef.review_source or ""]
            with self.db.tx() as tx:
                self._set_step(tx, run_id, key, "needs_review", output={"proposal": proposal})
                self._set_run(tx, run_id, "needs_review")
                self._event(
                    tx,
                    run_id,
                    "Waiting for a person to approve, edit or reject",
                    kind="state",
                    step=key,
                    level="warn",
                )
                self.queue.complete(job, tx=tx)
            return "needs_review"

        assert self.provider is not None and self.webhook is not None and sdef.handler
        ctx = StepContext(
            run_id=run_id,
            input=loads(run["input"]),
            outputs=outputs,
            attempt=attempt,
            provider=self.provider,
            webhook=self.webhook,
            log=self._log_now(run_id, key),
            delay=self.step_delay,
        )
        try:
            output = await sdef.handler(ctx)
        except Exception as exc:
            return self._handle_failure(job, wf, key, attempt, step["max_attempts"], exc)

        with self.db.tx() as tx:
            self._set_step(
                tx, run_id, key, "completed", output=output, finished_at=now(), error=None
            )
            self._event(tx, run_id, f"Completed {sdef.title}", kind="state", step=key)
            nxt = wf.next_step(key)
            if nxt is None:
                self._set_run(tx, run_id, "completed")
                self._event(tx, run_id, "Run completed", kind="state")
            else:
                self._queue_step(tx, run_id, nxt.key)
                self._touch(tx, run_id)
            self.queue.complete(job, tx=tx)
        return "completed"

    def _handle_failure(
        self, job: Job, wf: WorkflowDef, key: str, attempt: int, max_attempts: int, exc: Exception
    ) -> str:
        run_id = job.payload["run_id"]
        title = wf.step(key).title
        if isinstance(exc, ProviderError):
            retryable, message = exc.retryable, exc.message
        elif isinstance(exc, pydantic.ValidationError):
            retryable, message = True, "Output didn't match the expected schema."
        elif isinstance(exc, StepError):
            retryable, message = isinstance(exc, TransientError), exc.message
        else:
            logger.exception("Unexpected error in step %s of run %s", key, run_id)
            retryable, message = False, f"Unexpected error: {type(exc).__name__}."
        if isinstance(exc, PermanentError):
            retryable = False

        if retryable and attempt < max_attempts:
            delay = backoff(attempt, self.retry_base, self.retry_max)
            with self.db.tx() as tx:
                self._set_step(
                    tx, run_id, key, "queued", error=message, next_attempt_at=now() + delay
                )
                self._touch(tx, run_id)
                self._event(
                    tx,
                    run_id,
                    f"{title} failed: {message} Retrying in {delay:g}s "
                    f"(attempt {attempt + 1} of {max_attempts}).",
                    kind="state",
                    level="warn",
                    step=key,
                    data={"retry_in": delay, "attempt": attempt},
                )
                self.queue.retry(job, delay=delay, error=message, tx=tx)
            return "retry"

        with self.db.tx() as tx:
            self._set_step(tx, run_id, key, "failed", error=message, finished_at=now())
            self._skip_rest(tx, run_id)
            self._set_run(tx, run_id, "failed", error=f"{title}: {message}")
            reason = "no retries left" if retryable else "not retryable"
            self._event(
                tx,
                run_id,
                f"{title} failed ({reason}): {message}",
                kind="state",
                level="error",
                step=key,
            )
            self.queue.bury(job, error=message, tx=tx)
        return "failed"
