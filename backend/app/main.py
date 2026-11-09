"""HTTP API. Run with `uvicorn --factory app.main:create_app`.

It only reads state, writes requests to the queue and streams events.

Steps never run inside a request: `POST /api/runs` persists the run, queues the first step and
returns 202. Worker processes do the rest.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pydantic
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.db import Database, dumps, loads, now
from app.engine import Conflict, Engine, NotFound
from app.models import ReviewDecision
from app.queue import SqliteQueue
from app.settings import Settings, get_settings
from app.states import TERMINAL_RUN
from app.webhook import IDEMPOTENCY_HEADER, SIGNATURE_HEADER, verify
from app.workflows import WORKFLOWS, samples


class StartRun(pydantic.BaseModel):
    workflow: str
    input: dict[str, Any]


def sse(event: str, data: Any, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings.db_path)
    queue = SqliteQueue(db, lease_seconds=settings.lease_seconds)
    engine = Engine(db, queue)

    app = FastAPI(title="Workflow Runner API", version="0.1.0")
    app.state.db = db
    app.state.engine = engine
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "queue": queue.stats()}

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        offline = settings.provider == "offline"
        return {
            "provider": settings.provider,
            "model": "offline-mock" if offline else settings.anthropic_model,
            "demo_mode": offline,
            "webhook_url": settings.webhook_url,
        }

    @app.get("/api/workflows")
    def workflows() -> list[dict[str, Any]]:
        return [
            {
                "key": wf.key,
                "name": wf.name,
                "description": wf.description,
                "steps": [
                    {"key": s.key, "title": s.title, "kind": s.kind, "description": s.description}
                    for s in wf.steps
                ],
                "samples": samples().get(wf.key, []),
            }
            for wf in WORKFLOWS.values()
        ]

    @app.post("/api/runs", status_code=202)
    def start_run(body: StartRun) -> dict[str, Any]:
        if body.workflow not in WORKFLOWS:
            raise HTTPException(404, "Unknown workflow.")
        try:
            run_id = engine.start_run(body.workflow, body.input)
        except pydantic.ValidationError as exc:
            errors = [
                {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
                for e in exc.errors()
            ]
            return JSONResponse({"detail": "Check the highlighted fields.", "errors": errors}, 422)
        return {"id": run_id, "status": "queued"}

    @app.get("/api/runs")
    def list_runs(limit: int = 50) -> list[dict[str, Any]]:
        return engine.list_runs(min(max(limit, 1), 200))

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        try:
            return engine.get_run(run_id)
        except NotFound:
            raise HTTPException(404, "Run not found.") from None

    @app.post("/api/runs/{run_id}/review")
    def review(run_id: str, decision: ReviewDecision) -> dict[str, Any]:
        try:
            return engine.submit_review(run_id, decision)
        except NotFound:
            raise HTTPException(404, "Run not found.") from None
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str, request: Request) -> StreamingResponse:
        """Server-Sent Events: a run snapshot, then every log event, until the run ends.

        The worker is another process, so the stream polls SQLite for new events. Reconnecting
        clients send Last-Event-ID and pick up where they left off.
        """
        if engine.run_status(run_id) is None:
            raise HTTPException(404, "Run not found.")
        header = request.headers.get("last-event-id") or request.query_params.get("after")
        try:
            last_id = int(header) if header else 0
        except ValueError:
            last_id = 0

        async def stream() -> AsyncIterator[str]:
            nonlocal last_id
            yield "retry: 2000\n\n"
            yield sse("run", engine.get_run(run_id))
            idle = 0.0
            while True:
                batch = engine.events_after(run_id, last_id)
                for ev in batch:
                    last_id = ev["id"]
                    yield sse("log", ev, ev["id"])
                if any(ev["kind"] == "state" for ev in batch):
                    yield sse("run", engine.get_run(run_id))
                if not batch and engine.run_status(run_id) in TERMINAL_RUN:
                    yield sse("end", {"status": engine.run_status(run_id)})
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(settings.sse_poll_seconds)
                idle = 0.0 if batch else idle + settings.sse_poll_seconds
                if idle >= settings.sse_keepalive_seconds:
                    idle = 0.0
                    yield ": keepalive\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Mock webhook receiver ------------------------------------------------------------------
    # Stands in for the system on the other end (a CRM, an email service, a help desk).

    @app.post("/api/receiver/hooks")
    async def receive(request: Request) -> dict[str, Any]:
        body = await request.body()
        key = request.headers.get(IDEMPOTENCY_HEADER)
        if not key:
            raise HTTPException(400, "Missing Idempotency-Key header.")
        signature_ok = verify(settings.webhook_secret, body, request.headers.get(SIGNATURE_HEADER))
        try:
            payload = json.loads(body)
        except ValueError:
            raise HTTPException(400, "Body must be JSON.") from None
        t = now()
        with db.tx() as tx:
            existing = tx.execute(
                "SELECT id FROM deliveries WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if existing:
                tx.execute(
                    "UPDATE deliveries SET attempts = attempts + 1, last_received_at = ? "
                    "WHERE id = ?",
                    (t, existing["id"]),
                )
                return {"status": "duplicate", "id": existing["id"]}
            cur = tx.execute(
                "INSERT INTO deliveries (idempotency_key, received_at, last_received_at, "
                "signature_ok, event, payload) VALUES (?, ?, ?, ?, ?, ?)",
                (key, t, t, int(signature_ok), payload.get("event"), dumps(payload)),
            )
        return {"status": "received", "id": cur.lastrowid, "signature_ok": signature_ok}

    @app.get("/api/receiver/deliveries")
    def deliveries(limit: int = 50) -> list[dict[str, Any]]:
        rows = db.query(
            "SELECT * FROM deliveries ORDER BY id DESC LIMIT ?", (min(max(limit, 1), 200),)
        )
        return [
            {
                "id": r["id"],
                "idempotency_key": r["idempotency_key"],
                "received_at": r["received_at"],
                "last_received_at": r["last_received_at"],
                "attempts": r["attempts"],
                "signature_ok": bool(r["signature_ok"]),
                "event": r["event"],
                "payload": loads(r["payload"]),
            }
            for r in rows
        ]

    return app
