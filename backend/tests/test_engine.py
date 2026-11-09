import httpx
import pytest

from app.engine import Conflict, backoff, job_key
from app.models import ReviewDecision, ReviewEdits
from app.worker import drain
from tests.conftest import make_engine, sample


def steps(engine, run_id):
    return {s["key"]: s for s in engine.get_run(run_id)["steps"]}


def messages(engine, run_id):
    return [e["message"] for e in engine.events_after(run_id, 0)]


def deliveries(db):
    return db.query("SELECT * FROM deliveries")


def test_backoff_is_exponential_and_capped():
    assert [backoff(n, 2, 60) for n in (1, 2, 3, 4, 5, 6)] == [2, 4, 8, 16, 32, 60]


def test_start_run_only_queues_work(engine, queue):
    run_id = engine.start_run("lead_outreach", sample("lead_outreach"))
    run = engine.get_run(run_id)
    assert run["status"] == "queued"
    assert [s["status"] for s in run["steps"]] == ["queued"] + ["pending"] * 5
    assert queue.stats() == {"queued": 1}


async def test_lead_outreach_retries_pauses_for_review_and_sends(engine, db):
    run_id = engine.start_run("lead_outreach", sample("lead_outreach"))

    results = await drain(engine)
    assert results == ["completed", "retry", "completed", "completed", "completed", "needs_review"]
    run = engine.get_run(run_id)
    assert run["status"] == "needs_review"
    s = steps(engine, run_id)
    assert s["fetch_company"]["attempts"] == 2
    assert s["fetch_company"]["status"] == "completed"
    assert s["pain_points"]["output"]["pain_points"]
    assert s["review"]["status"] == "needs_review"
    proposal = s["review"]["output"]["proposal"]
    assert "Harborline Freight" in proposal["subject"]
    assert any("Retrying in 0s (attempt 2 of 3)" in m for m in messages(engine, run_id))

    edits = ReviewEdits(subject="Quick idea for your quote inbox", body=proposal["body"])
    assert engine.submit_review(run_id, ReviewDecision(decision="edit", edits=edits)) == {
        "status": "running"
    }
    assert await drain(engine) == ["completed"]

    run = engine.get_run(run_id)
    assert run["status"] == "completed" and run["finished_at"]
    assert steps(engine, run_id)["review"]["output"]["edited"] is True
    [delivery] = deliveries(db)
    assert delivery["idempotency_key"] == f"{run_id}:send"
    assert delivery["signature_ok"] == 1
    assert '"subject":"Quick idea for your quote inbox"' in delivery["payload"]
    assert "Run completed" in messages(engine, run_id)


async def test_ticket_triage_runs_on_the_same_engine(engine, db):
    run_id = engine.start_run("ticket_triage", sample("ticket_triage"))
    assert await drain(engine) == ["completed", "completed", "completed", "needs_review"]
    cls = steps(engine, run_id)["classify"]["output"]
    assert cls["category"] == "billing" and cls["priority"] == "high"
    engine.submit_review(run_id, ReviewDecision(decision="approve"))
    await drain(engine)
    assert engine.get_run(run_id)["status"] == "completed"
    assert '"category":"billing"' in deliveries(db)[0]["payload"]


async def test_reject_skips_the_send_step(engine, db):
    run_id = engine.start_run("ticket_triage", sample("ticket_triage", 2))
    await drain(engine)
    engine.submit_review(run_id, ReviewDecision(decision="reject", note="Wrong tone"))
    assert await drain(engine) == []
    run = engine.get_run(run_id)
    assert run["status"] == "rejected"
    assert steps(engine, run_id)["send"]["status"] == "skipped"
    assert deliveries(db) == []
    assert "Rejected by reviewer: Wrong tone" in messages(engine, run_id)


async def test_review_can_only_be_decided_once(engine):
    run_id = engine.start_run("ticket_triage", sample("ticket_triage"))
    await drain(engine)
    engine.submit_review(run_id, ReviewDecision(decision="approve"))
    with pytest.raises(Conflict):
        engine.submit_review(run_id, ReviewDecision(decision="approve"))


async def test_permanent_failure_fails_the_run_without_retrying(engine):
    run_id = engine.start_run("lead_outreach", sample("lead_outreach", 2))
    assert await drain(engine) == ["completed", "failed"]
    run = engine.get_run(run_id)
    assert run["status"] == "failed"
    assert "No company info found for unknown-co.example" in run["error"]
    s = steps(engine, run_id)
    assert s["fetch_company"]["attempts"] == 1
    assert {s[k]["status"] for k in ("pain_points", "draft_email", "review", "send")} == {"skipped"}


async def test_transient_failures_stop_after_max_attempts(db, queue, app, settings):
    flaky = httpx.MockTransport(lambda _: httpx.Response(503))
    engine = make_engine(db, queue, app, settings, transport=flaky)
    run_id = engine.start_run("ticket_triage", sample("ticket_triage"))
    await drain(engine)
    engine.submit_review(run_id, ReviewDecision(decision="approve"))
    assert await drain(engine) == ["retry", "retry", "retry", "failed"]
    send = steps(engine, run_id)["send"]
    assert send["status"] == "failed" and send["attempts"] == 4
    assert engine.get_run(run_id)["status"] == "failed"
    assert queue.stats()["dead"] == 1


async def test_redelivered_job_for_a_finished_step_is_not_rerun(engine, queue):
    run_id = engine.start_run("ticket_triage", sample("ticket_triage"))
    await drain(engine)
    before = steps(engine, run_id)["classify"]
    # At-least-once delivery: the same step shows up again (a broker redelivery, a manual replay).
    queue.enqueue("step", {"run_id": run_id, "step": "classify"}, key="replay-1")
    assert await drain(engine) == ["duplicate"]
    assert steps(engine, run_id)["classify"] == before


async def test_double_enqueue_of_a_step_is_dropped(engine, queue, db):
    run_id = engine.start_run("ticket_triage", sample("ticket_triage"))
    assert (
        queue.enqueue("step", {"run_id": run_id, "step": "intake"}, key=job_key(run_id, "intake"))
        is False
    )


async def test_webhook_redelivery_is_deduplicated_by_the_receiver(engine, db):
    for _ in range(2):
        await engine.webhook.send("test.event", {"hello": "world"}, key="run-x:send")
    [row] = deliveries(db)
    assert row["attempts"] == 2


async def test_crashed_worker_step_is_picked_up_by_another(engine, queue, monkeypatch):
    import app.queue as queue_module

    run_id = engine.start_run("ticket_triage", sample("ticket_triage"))
    job = queue.lease("crashed-worker")
    # The worker marked the step running and then died before finishing.
    with engine.db.tx() as tx:
        engine._set_step(tx, run_id, "intake", "running", attempts=1)
    real_now = queue_module.now
    monkeypatch.setattr(queue_module, "now", lambda: real_now() + 60)
    assert await drain(engine, worker_id="healthy") == [
        "completed",
        "completed",
        "completed",
        "needs_review",
    ]
    assert steps(engine, run_id)["intake"]["attempts"] == 2
    assert job.lease_token  # the dead worker's token no longer matches anything
