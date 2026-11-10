"""Housekeeping for the public demo: runs and webhook deliveries are forgotten after a while.

Every visitor sees the same run history, so old runs (and whatever names or notes people typed)
shouldn't pile up. Off unless `demo_retention_minutes` is set.
"""

from app.db import Database, now
from app.states import TERMINAL_RUN

# Runs paused for review hold no queued job, so they can go too.
PRUNABLE = (*sorted(TERMINAL_RUN), "needs_review")


def prune(db: Database, max_age_seconds: float, at: float | None = None) -> dict[str, int]:
    """Deletes finished runs, settled jobs and deliveries older than `max_age_seconds`."""
    cutoff = (now() if at is None else at) - max_age_seconds
    marks = ",".join("?" * len(PRUNABLE))
    with db.tx() as tx:
        # A run with a job still queued or leased is left alone, so the worker never loses its run.
        runs = tx.execute(
            f"""DELETE FROM runs WHERE created_at < ? AND status IN ({marks})
                AND id NOT IN (SELECT json_extract(payload, '$.run_id') FROM jobs
                               WHERE status IN ('queued', 'leased'))""",
            (cutoff, *PRUNABLE),
        ).rowcount
        jobs = tx.execute(
            "DELETE FROM jobs WHERE status IN ('done', 'dead') AND updated_at < ?", (cutoff,)
        ).rowcount
        deliveries = tx.execute(
            "DELETE FROM deliveries WHERE last_received_at < ?", (cutoff,)
        ).rowcount
    return {"runs": runs, "jobs": jobs, "deliveries": deliveries}
