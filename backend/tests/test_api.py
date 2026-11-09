import json

from app.models import ReviewDecision
from app.webhook import sign
from app.worker import drain
from tests.conftest import sample


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        ev: dict = {}
        for line in block.splitlines():
            if line.startswith(":") or line.startswith("retry:"):
                continue
            field, _, value = line.partition(": ")
            ev[field] = value
        if "event" in ev:
            ev["data"] = json.loads(ev["data"])
            events.append(ev)
    return events


def test_config_reports_offline_mode(client):
    body = client.get("/api/config").json()
    assert body["provider"] == "offline" and body["demo_mode"] is True


def test_lists_workflows_with_steps_and_samples(client):
    body = client.get("/api/workflows").json()
    assert [w["key"] for w in body] == ["lead_outreach", "ticket_triage"]
    assert [s["key"] for s in body[0]["steps"]][-2:] == ["review", "send"]
    assert body[1]["samples"][0]["input"]["plan"] == "business"


def test_start_run_returns_202_and_does_no_work_in_the_request(client):
    res = client.post(
        "/api/runs", json={"workflow": "lead_outreach", "input": sample("lead_outreach")}
    )
    assert res.status_code == 202
    run = client.get(f"/api/runs/{res.json()['id']}").json()
    assert run["status"] == "queued"
    assert all(s["attempts"] == 0 for s in run["steps"])
    assert client.get("/api/runs").json()[0]["id"] == run["id"]


def test_start_run_validates_input(client):
    bad = {**sample("lead_outreach"), "email": "not-an-email"}
    res = client.post("/api/runs", json={"workflow": "lead_outreach", "input": bad})
    assert res.status_code == 422
    assert res.json()["errors"][0]["field"] == "email"
    assert client.post("/api/runs", json={"workflow": "nope", "input": {}}).status_code == 404


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/missing").status_code == 404
    assert client.get("/api/runs/missing/events").status_code == 404


async def test_review_endpoint(client, engine):
    run_id = engine.start_run("ticket_triage", sample("ticket_triage"))
    assert (
        client.post(f"/api/runs/{run_id}/review", json={"decision": "approve"}).status_code == 409
    )
    await drain(engine)
    res = client.post(f"/api/runs/{run_id}/review", json={"decision": "approve"})
    assert res.status_code == 200 and res.json() == {"status": "running"}
    assert (
        client.post(f"/api/runs/{run_id}/review", json={"decision": "approve"}).status_code == 409
    )


async def test_sse_streams_snapshot_logs_and_end(client, engine):
    run_id = engine.start_run("ticket_triage", sample("ticket_triage"))
    await drain(engine)
    engine.submit_review(run_id, ReviewDecision(decision="approve"))
    await drain(engine)

    with client.stream("GET", f"/api/runs/{run_id}/events") as res:
        assert res.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(res.read().decode())

    assert events[0]["event"] == "run"
    assert events[-1] == {"event": "end", "data": {"status": "completed"}}
    logs = [e for e in events if e["event"] == "log"]
    ids = [int(e["id"]) for e in logs]
    assert ids == sorted(ids) and len(ids) == len(set(ids))
    assert logs[0]["data"]["message"].startswith("Run created")
    assert any(e["data"]["message"] == "Run completed" for e in logs)
    # A state change is followed by a fresh run snapshot.
    assert events[-2]["event"] == "run" and events[-2]["data"]["status"] == "completed"

    # Reconnect with Last-Event-ID: only newer events come back.
    cut = ids[len(ids) // 2]
    with client.stream(
        "GET", f"/api/runs/{run_id}/events", headers={"Last-Event-ID": str(cut)}
    ) as res:
        resumed = [e for e in parse_sse(res.read().decode()) if e["event"] == "log"]
    assert [int(e["id"]) for e in resumed] == [i for i in ids if i > cut]


def test_receiver_checks_signature_and_dedupes(client, settings):
    body = json.dumps({"event": "x", "data": {}}).encode()
    good = {"Idempotency-Key": "k1", "X-Runner-Signature": sign(settings.webhook_secret, body)}
    first = client.post("/api/receiver/hooks", content=body, headers=good).json()
    assert first["status"] == "received" and first["signature_ok"] is True
    assert (
        client.post("/api/receiver/hooks", content=body, headers=good).json()["status"]
        == "duplicate"
    )

    forged = {"Idempotency-Key": "k2", "X-Runner-Signature": "sha256=nope"}
    assert (
        client.post("/api/receiver/hooks", content=body, headers=forged).json()["signature_ok"]
        is False
    )
    assert client.post("/api/receiver/hooks", content=body).status_code == 400

    rows = client.get("/api/receiver/deliveries").json()
    assert [(r["idempotency_key"], r["attempts"], r["signature_ok"]) for r in rows] == [
        ("k2", 1, False),
        ("k1", 2, True),
    ]
