from app.db import now
from app.retention import prune
from app.worker import drain
from tests.conftest import sample


async def test_prune_forgets_old_finished_runs_and_deliveries(engine, db):
    run_id = engine.start_run("ticket_triage", sample("ticket_triage"))
    await drain(engine)
    assert db.one("SELECT status FROM runs WHERE id = ?", (run_id,))["status"] == "needs_review"

    # Nothing is older than an hour yet.
    assert prune(db, 3600) == {"runs": 0, "jobs": 0, "deliveries": 0}

    removed = prune(db, 3600, at=now() + 7200)
    assert removed["runs"] == 1 and removed["jobs"] > 0
    assert db.one("SELECT COUNT(*) AS n FROM runs")["n"] == 0
    assert db.one("SELECT COUNT(*) AS n FROM steps")["n"] == 0  # cascades with the run
    assert db.one("SELECT COUNT(*) AS n FROM events")["n"] == 0


def test_prune_keeps_a_run_whose_job_is_still_queued(engine, db):
    run_id = engine.start_run("lead_outreach", sample("lead_outreach"))
    removed = prune(db, 3600, at=now() + 7200)
    assert removed["runs"] == 0
    assert db.one("SELECT id FROM runs WHERE id = ?", (run_id,)) is not None
