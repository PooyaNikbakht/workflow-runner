# Workflow Runner: product requirements

## Summary

A small web app for starting multi-step AI workflows and watching them run live. Each step is a job on a queue, executed by a separate worker process. A person can step in at a review step to approve, edit or reject what the AI produced before anything leaves the system.

It is a portfolio piece that shows how to build AI features that behave like real backend systems: async execution, retries, idempotency, persisted history and a live UI.

## Who it is for

- Startup founders and technical teams who want AI automations they can trust and inspect.
- Engineers evaluating how Pooya approaches async architecture and human-in-the-loop AI.

## Workflows (seeded)

1. **Lead outreach**
   1. Lead intake: validate and normalize the lead.
   2. Fetch company info: look the company up in a local fixture dataset (no real scraping). This step fails once on purpose in the demo to show a retry with backoff.
   3. Extract pain points: LLM call with a structured output schema.
   4. Draft outreach email: LLM call with a structured output schema.
   5. Human review: approve, edit or reject in a drawer.
   6. Send: deliver the approved email through an outgoing webhook to a local mock receiver.
2. **Support ticket triage**
   1. Ticket intake.
   2. Classify: category, priority and sentiment (LLM, structured).
   3. Suggest reply (LLM, structured).
   4. Human review.
   5. Send: post the reply through the same webhook step.

The engine is generic: a workflow is a list of step definitions, and both workflows run on the same engine, queue and worker.

## Functional requirements

- Start a run from the UI with a sample input or edited fields.
- Runs and steps are persisted. Step states: `pending`, `queued`, `running`, `needs_review`, `completed`, `failed`, `skipped`. Run states: `queued`, `running`, `needs_review`, `completed`, `failed`, `rejected`.
- Jobs go on a queue and are executed by a worker process, never inside the HTTP request.
- Transient failures are retried with exponential backoff up to a per-step limit. Permanent failures fail the run.
- Step execution is idempotent: a step that already completed is never run twice, and the webhook carries an idempotency key the receiver uses to drop duplicates.
- Live view: a stepper and a streaming log, delivered over Server-Sent Events, with resume through `Last-Event-ID`.
- Review drawer: shows the AI output, lets the reviewer edit it, approve or reject with a note. The decision resumes the run through the queue.
- Mock webhook receiver page that lists received payloads, the idempotency key and whether the HMAC signature checked out.
- Run history list with status, workflow and timings.

## AI provider layer

- Claude through the official `anthropic` Python SDK, using structured outputs validated by pydantic models. Default model `claude-opus-5-5`; public demos set `claude-haiku-5-5`.
- A deterministic offline mock used when no API key is set, and by the tests.
- `LLM_PROVIDER=anthropic|offline`; empty picks Anthropic when `ANTHROPIC_API_KEY` is present, otherwise offline.

## Non-functional requirements

- Runs locally with no cloud accounts and no extra services: SQLite holds the data and the queue.
- The queue sits behind a small `Queue` interface so Redis or SQS can replace it.
- Mobile first, keyboard accessible, visible focus, `aria-live` status updates, light and dark themes, flat design per the shared standards.
- Ports: frontend 3050, API 8050.

## Out of scope

- Authentication and multi-tenant access.
- A visual workflow editor. Workflows are defined in code.
- Real web scraping or real email delivery.

## Done when

- pytest covers queue leasing, retries and idempotency, the step state machine, workflow definitions, the SSE endpoint and the provider adapters (with a mocked Anthropic client).
- ruff, frontend lint and build pass.
- README with pitch, architecture diagram, key decisions, run instructions and `.env.example`.
- Screenshots in `docs/screenshots/`.
