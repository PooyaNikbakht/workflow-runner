import threading

import pytest

import app.queue as queue_module
from app.db import Database
from app.queue import LeaseLost, SqliteQueue


def test_enqueue_is_idempotent_by_key(queue):
    assert queue.enqueue("step", {"n": 1}, key="run1:intake") is True
    assert queue.enqueue("step", {"n": 2}, key="run1:intake") is False
    job = queue.lease("w1")
    assert job is not None and job.payload == {"n": 1}
    assert queue.lease("w1") is None


def test_lease_skips_jobs_scheduled_in_the_future(queue):
    queue.enqueue("step", {}, key="later", delay=60)
    assert queue.lease("w1") is None


def test_jobs_are_leased_in_order(queue):
    for i in range(3):
        queue.enqueue("step", {"i": i}, key=f"k{i}")
    assert [queue.lease("w").payload["i"] for _ in range(3)] == [0, 1, 2]


def test_expired_lease_is_taken_over_and_old_owner_is_fenced(queue, monkeypatch):
    queue.enqueue("step", {}, key="k")
    first = queue.lease("w1")
    assert queue.lease("w2") is None  # still leased

    real_now = queue_module.now
    monkeypatch.setattr(queue_module, "now", lambda: real_now() + 31)
    second = queue.lease("w2")
    assert second is not None and second.id == first.id
    assert second.attempts == 2 and second.lease_token != first.lease_token

    with pytest.raises(LeaseLost):
        queue.complete(first)
    queue.complete(second)
    assert queue.stats() == {"done": 1}


def test_retry_puts_the_job_back_after_the_delay(queue, monkeypatch):
    queue.enqueue("step", {}, key="k")
    job = queue.lease("w1")
    queue.retry(job, delay=4, error="timeout")
    assert queue.lease("w1") is None

    real_now = queue_module.now
    monkeypatch.setattr(queue_module, "now", lambda: real_now() + 5)
    again = queue.lease("w1")
    assert again is not None and again.attempts == 2
    row = queue.db.one("SELECT last_error FROM jobs WHERE id = ?", (job.id,))
    assert row["last_error"] == "timeout"


def test_bury_marks_the_job_dead(queue):
    queue.enqueue("step", {}, key="k")
    job = queue.lease("w1")
    queue.bury(job, error="boom")
    assert queue.stats() == {"dead": 1}
    with pytest.raises(LeaseLost):
        queue.complete(job)


def test_enqueue_joins_the_callers_transaction(queue, db):
    with pytest.raises(RuntimeError), db.tx() as tx:
        queue.enqueue("step", {}, key="k", tx=tx)
        raise RuntimeError("roll back")
    assert queue.lease("w1") is None


def test_two_workers_never_lease_the_same_job(settings):
    # Two connections to the same file, like two worker processes.
    setup = Database(settings.db_path)
    q = SqliteQueue(setup)
    for i in range(60):
        q.enqueue("step", {"i": i}, key=f"k{i}")

    leased: dict[str, list[int]] = {"a": [], "b": []}

    def work(name: str) -> None:
        conn = Database(settings.db_path)
        worker_queue = SqliteQueue(conn)
        while (job := worker_queue.lease(name)) is not None:
            leased[name].append(job.id)
            worker_queue.complete(job)
        conn.close()

    threads = [threading.Thread(target=work, args=(n,)) for n in leased]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    all_ids = leased["a"] + leased["b"]
    assert len(all_ids) == 60
    assert len(set(all_ids)) == 60
    assert q.stats() == {"done": 60}
    setup.close()
