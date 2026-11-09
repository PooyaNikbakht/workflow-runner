"""The worker process: lease a job, run the step, repeat.

Run one or more of these next to the API:

    uv run python -m app.worker

Each worker handles one job at a time. Start more processes to run more steps in parallel; the
queue's leases keep them from picking up the same job.
"""

import asyncio
import contextlib
import logging
import os
import signal
import socket

from app.db import Database
from app.engine import Engine
from app.providers import build_provider
from app.queue import LeaseLost, SqliteQueue
from app.settings import Settings, get_settings
from app.webhook import WebhookSender

logger = logging.getLogger("worker")


def build_engine(settings: Settings, db: Database) -> Engine:
    return Engine(
        db,
        SqliteQueue(db, lease_seconds=settings.lease_seconds),
        provider=build_provider(settings),
        webhook=WebhookSender(
            settings.webhook_url, settings.webhook_secret, timeout=settings.webhook_timeout_seconds
        ),
        retry_base=settings.retry_base_seconds,
        retry_max=settings.retry_max_seconds,
        step_delay=settings.step_delay_seconds,
    )


async def run_once(engine: Engine, worker_id: str) -> str | None:
    """Lease and process one job. Returns None when nothing is ready."""
    queue = engine.queue
    job = queue.lease(worker_id)
    if job is None:
        return None
    try:
        result = await engine.process(job)
    except LeaseLost:
        # Another worker took over after our lease expired; its result wins.
        logger.warning("Lost the lease on job %s, dropping our result", job.id)
        return "lease_lost"
    logger.info("job %s %s -> %s", job.id, job.payload.get("step"), result)
    return result


async def drain(engine: Engine, worker_id: str = "test", max_jobs: int = 100) -> list[str]:
    """Process ready jobs until the queue is idle. Used by tests and scripts."""
    results: list[str] = []
    for _ in range(max_jobs):
        result = await run_once(engine, worker_id)
        if result is None:
            break
        results.append(result)
    return results


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = get_settings()
    db = Database(settings.db_path)
    engine = build_engine(settings, db)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    provider = engine.provider
    logger.info(
        "Worker %s started (provider %s, model %s)",
        worker_id,
        provider.name if provider else "none",
        provider.model if provider else "none",
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    while not stop.is_set():
        try:
            result = await run_once(engine, worker_id)
        except Exception:
            logger.exception("Worker loop error")
            result = None
        if result is None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=settings.poll_interval_seconds)
    logger.info("Worker %s stopped", worker_id)
    db.close()


if __name__ == "__main__":
    asyncio.run(main())
